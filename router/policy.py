"""The router: classify -> pick the cheapest model that clears the bar -> fall back on trouble.

Policy in one paragraph: extract features from the request (task, language,
structure, difficulty) and ask a small LLM classifier when the heuristics are
unsure. For every model that fits the context window and latency budget,
estimate P(pass) from calibration data. Send the request to the CHEAPEST
model whose P(pass) clears the task's quality bar (the SLA threshold). If
none clears it, use the model with the highest P(pass). After the call, if
the response times out, refuses, returns unparseable JSON or answers in the
wrong script, retry on the cheapest stronger model (at most 2 hops). The
router's own classifier cost and latency are added to every request.
"""
import time

from . import config
from .features import extract, est_tokens
from .quality import detect_issue, score


class Router:
    def __init__(self, backend, estimator, use_fallback=True, use_llm_classifier=True):
        self.backend = backend
        self.est = estimator
        self.use_fallback = use_fallback
        self.use_llm_classifier = use_llm_classifier

    # ------------------------------------------------------------------ step 1
    def classify(self, req):
        t0 = time.perf_counter()
        f = extract(req["messages"], req.get("tools"), req.get("meta"))
        cost, lat = 0.0, (time.perf_counter() - t0) * 1000
        if self.use_llm_classifier and f["task_confidence"] < config.LLM_CLASSIFIER_CONFIDENCE:
            task, diff, resp = self.backend.classify(req)
            cost += config.price(config.CLASSIFIER_MODEL, resp.tokens_in, resp.tokens_out)
            lat += resp.latency_ms
            if task in config.DEFAULT_SLA:
                f["heuristic_guess"] = (f["task"], f["difficulty"])
                f["task"], f["classifier"] = task, "llm"
                # keep the more cautious difficulty of the two estimates
                f["difficulty"] = max(diff, f["difficulty"]) if diff else f["difficulty"]
        return f, cost, lat

    # ------------------------------------------------------------------ step 2
    def estimate(self, model, f, prompt_text):
        m = config.MODELS[model]
        tin = est_tokens(prompt_text, model)
        out = config.EXPECTED_OUT_TOKENS[f["task"]]
        if f.get("out_script") not in (None, "latin"):
            out = int(out * 4 / m["cpt_indic"])
        cost = config.price(model, tin, out)
        p95_ms = m["ttft_ms"] * 1.8 + out / m["tps"] * 1000 * 1.4 + tin / 20
        return tin, out, cost, p95_ms

    def candidates(self, f, prompt_text):
        rows = []
        for model, m in config.MODELS.items():
            tin, out, cost, p95 = self.estimate(model, f, prompt_text)
            p, support = self.est.p(model, f)
            row = {"model": model, "p": round(p, 3), "support": support,
                   "est_cost": cost, "est_p95_ms": round(p95)}
            if tin + out > m["ctx"]:
                row["excluded"] = "context"
            elif f.get("latency_budget_ms") and p95 > f["latency_budget_ms"]:
                row["excluded"] = "latency_budget"
            rows.append(row)
        return sorted(rows, key=lambda r: r["est_cost"])

    def decide(self, f, rows):
        tau = f.get("sla") or config.DEFAULT_SLA[f["task"]]
        ok = [r for r in rows if "excluded" not in r]
        if not ok:  # nothing fits the budget: take the fastest model and say so
            ok = sorted(rows, key=lambda r: r["est_p95_ms"])[:1]
        why = []
        for r in ok:
            if r["p"] >= tau:
                why.append("%s p=%.2f>=%.2f cheapest-sufficient" % (r["model"], r["p"], tau))
                return r, tau, "; ".join(why)
            why.append("%s p=%.2f<%.2f" % (r["model"], r["p"], tau))
        best = max(ok, key=lambda r: r["p"])
        why.append("none clears bar -> highest p: %s" % best["model"])
        return best, tau, "; ".join(why)

    def next_model(self, rows, tried, current_p, tau):
        stronger = [r for r in rows if "excluded" not in r and r["model"] not in tried and r["p"] > current_p]
        for r in stronger:  # rows are cost-sorted: cheapest stronger model that clears the bar
            if r["p"] >= tau:
                return r
        return max(stronger, key=lambda r: r["p"]) if stronger else None

    # ------------------------------------------------------------------ run
    def run(self, req, forced_model=None):
        prompt_text = "\n".join(m["content"] for m in req["messages"])
        if forced_model:  # baseline: no classifier, no fallback
            f = extract(req["messages"], req.get("tools"), req.get("meta"))
            rcost, rlat = 0.0, 0.0
            rows = self.candidates(f, prompt_text)
            chosen = next(r for r in rows if r["model"] == forced_model)
            tau, reason = config.DEFAULT_SLA[f["task"]], "baseline: always %s" % forced_model
            fallback_allowed = False
        else:
            f, rcost, rlat = self.classify(req)
            rows = self.candidates(f, prompt_text)
            chosen, tau, reason = self.decide(f, rows)
            fallback_allowed = self.use_fallback

        budget = f.get("latency_budget_ms")
        attempts, tried, elapsed = [], set(), rlat
        current, final_resp, fallback_reason = chosen, None, None
        while current:
            model = current["model"]
            tried.add(model)
            if budget:
                # keep part of the budget in reserve for a fallback, but only if one is allowed
                frac = config.VOICE_ATTEMPT_FRACTION if (fallback_allowed and not attempts) else 1.0
                timeout = max(200, (budget - elapsed) * frac)
            else:
                timeout = config.DEFAULT_TIMEOUT_MS
            resp = self.backend.complete(model, req, timeout)
            elapsed += resp.latency_ms
            issue = detect_issue(resp, f)
            cost = config.price(model, resp.tokens_in, resp.tokens_out)
            attempts.append({"model": model, "status": resp.status, "issue": issue,
                             "tokens_in": resp.tokens_in, "tokens_out": resp.tokens_out,
                             "cost_usd": cost, "latency_ms": round(resp.latency_ms, 1)})
            final_resp = resp
            if not issue or not fallback_allowed or len(attempts) > config.MAX_FALLBACKS:
                break
            nxt = self.next_model(rows, tried, current["p"], tau)
            if nxt and budget and nxt["est_p95_ms"] > budget - elapsed:
                attempts[-1]["note"] = "no time left in latency budget for a fallback; degraded answer"
                nxt = None
            fallback_reason = fallback_reason or issue
            current = nxt

        q = score(final_resp, req["gold"]) if "gold" in req else None
        total_cost = rcost + sum(a["cost_usd"] for a in attempts)
        return {
            "id": req.get("id"),
            "task": f["task"], "lang": f["lang_bucket"], "difficulty": f["difficulty"],
            "classifier": f["classifier"], "threshold": tau,
            "route": chosen["model"], "reason": reason,
            "candidates": [{k: r[k] for k in ("model", "p", "support", "est_cost", "excluded") if k in r}
                           for r in rows],
            "final_model": attempts[-1]["model"],
            "fallback_fired": len(attempts) > 1, "fallback_reason": fallback_reason,
            "final_issue": attempts[-1]["issue"],
            "attempts": attempts,
            "tokens_in": sum(a["tokens_in"] for a in attempts),
            "tokens_out": sum(a["tokens_out"] for a in attempts),
            "router_cost_usd": rcost, "router_latency_ms": round(rlat, 2),
            "cost_usd": total_cost, "latency_ms": round(elapsed, 1),
            "quality": q, "passed": (q is not None and q >= config.PASS_THRESHOLD),
            "gold_lang": req.get("gold", {}).get("lang_bucket"),
        }
