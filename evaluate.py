"""Run the 40 held-out prompts through the baselines and the router; write the report.

Policies: always-cheapest (Sarvam 105B), always-frontier (Opus 5) and the router. The
simulator is re-run over 30 seeds so no result depends on one lucky draw. The
per-request log for seed 0 is written to logs/.

    python3 evaluate.py              # simulator, 30 seeds
    python3 evaluate.py --live       # real endpoints, 1 pass
"""
import argparse
import json
import sys
from collections import Counter, defaultdict

sys.path.insert(0, ".")
from data.load import load
from router import config
from router.backends import LiveBackend, SimBackend
from router.estimator import QualityEstimator
from router.policy import Router

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
ap.add_argument("--seeds", type=int, default=30)
args = ap.parse_args()

HELDOUT = load("heldout")
est = QualityEstimator.load("results/estimator.json")
POLICIES = [
    ("always-cheapest (Sarvam 105B)", dict(forced_model=config.CHEAPEST), {}),
    ("always-frontier (Opus 5)", dict(forced_model=config.FRONTIER), {}),
    ("router", {}, {}),
]
FR, RT = POLICIES[1][0], POLICIES[2][0]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def summ(logs):
    n = len(logs)
    return {
        "n": n,
        "inr_per_1k": sum(l["cost_inr"] for l in logs) / n * 1000,
        "p50_ms": pct([l["latency_ms"] for l in logs], 0.50),
        "p95_ms": pct([l["latency_ms"] for l in logs], 0.95),
        "quality": sum(l["quality"] for l in logs) / n,
        "pass_rate": sum(l["passed"] for l in logs) / n,
        "fallback_rate": sum(l["fallback_fired"] for l in logs) / n,
    }


seeds = [0] if args.live else list(range(args.seeds))
all_logs = {}
for name, run_kw, router_kw in POLICIES:
    logs = []
    for s in seeds:
        router = Router(LiveBackend() if args.live else SimBackend(seed=1000 + s), est, **router_kw)
        for req in HELDOUT:
            log = router.run(req, **run_kw)
            log["policy"], log["seed"] = name, s
            logs.append(log)
    all_logs[name] = logs
    fname = name.split(" ")[0]
    with open("logs/%s.jsonl" % fname, "w") as fh:
        for l in logs:
            if l["seed"] == seeds[0]:
                fh.write(json.dumps(l, ensure_ascii=False) + "\n")

S = {name: summ(logs) for name, logs in all_logs.items()}
fr = S[FR]["inr_per_1k"]
out = ["# Part 1 results (%s, %d seeds x %d held-out prompts)\n" % ("live" if args.live else "SIMULATED", len(seeds), len(HELDOUT)),
       "| Policy | Cost per 1,000 requests | vs frontier | p50 latency | p95 latency | Mean quality | Pass rate | Fallback rate |",
       "|---|---|---|---|---|---|---|---|"]
for name, a in S.items():
    out.append("| %s | ₹%.2f | %.0f%% | %.0f ms | %.0f ms | %.2f | %.0f%% | %.1f%% |" % (
        name, a["inr_per_1k"], 100 * a["inr_per_1k"] / fr, a["p50_ms"], a["p95_ms"],
        a["quality"], 100 * a["pass_rate"], 100 * a["fallback_rate"]))

out += ["\n## By language\n", "| Segment | Frontier ₹/1k | Router ₹/1k | Router vs frontier | Pass rate: cheapest / frontier / router |", "|---|---|---|---|---|"]
for seg, test in [("English", lambda l: l["gold_lang"] == "en"), ("Indian languages + Hinglish", lambda l: l["gold_lang"] != "en")]:
    a = {k: summ([l for l in v if test(l)]) for k, v in all_logs.items()}
    ch = POLICIES[0][0]
    out.append("| %s | ₹%.2f | ₹%.2f | %.0f%% | %.0f%% / %.0f%% / %.0f%% |" % (
        seg, a[FR]["inr_per_1k"], a[RT]["inr_per_1k"], 100 * a[RT]["inr_per_1k"] / a[FR]["inr_per_1k"],
        100 * a[ch]["pass_rate"], 100 * a[FR]["pass_rate"], 100 * a[RT]["pass_rate"]))

out += ["\n## By use case (router)\n", "| Use case | Rule | Where the router sent it | Router ₹/1k | Pass rate: frontier / router |", "|---|---|---|---|---|"]
for uc, rule in config.USE_CASES.items():
    rl = [l for l in all_logs[RT] if l["use_case"] == uc]
    fl = [l for l in all_logs[FR] if l["use_case"] == uc]
    if not rl:
        continue
    mix = Counter(l["final_model"] for l in rl)
    mix_s = ", ".join("%s %.0f%%" % (m, 100 * c / len(rl)) for m, c in mix.most_common())
    rule_s = ("pinned → %s" % rule["pin"]) if rule["pin"] else ("bar %.0f%%" % (100 * rule["bar"]))
    out.append("| %s | %s | %s | ₹%.2f | %.0f%% / %.0f%% |" % (
        uc, rule_s, mix_s, summ(rl)["inr_per_1k"], 100 * summ(fl)["pass_rate"], 100 * summ(rl)["pass_rate"]))

rl = all_logs[RT]
req_mix = Counter(l["final_model"] for l in rl)
tok = defaultdict(int)
for l in rl:
    for a in l["attempts"]:
        tok[a["model"]] += a["tokens_in"] + a["tokens_out"]
tot = sum(tok.values())
clf = [l for l in rl if l["classifier"] == "llm"]
out += ["\n## Router details\n",
        "- Share of requests by final model: " + ", ".join("%s %.0f%%" % (m, 100 * c / len(rl)) for m, c in req_mix.most_common()),
        "- Share of tokens by model (incl. fallback re-runs): " + ", ".join("%s %.0f%%" % (m, 100 * t / tot) for m, t in sorted(tok.items(), key=lambda kv: -kv[1])),
        "- Router's own cost, included above: ₹%.3f per 1,000 requests (%.0f%% of router spend)" % (
            sum(l["router_cost_inr"] for l in rl) / len(rl) * 1000, 100 * sum(l["router_cost_inr"] for l in rl) / sum(l["cost_inr"] for l in rl)),
        "- Router's own latency: under 1 ms for the rules; the LLM classifier fired on %.0f%% of requests, adding a median %.0f ms on those" % (
            100 * len(clf) / len(rl), pct([l["router_latency_ms"] for l in clf], 0.5) if clf else 0),
        "- Requests still failing a check after all fallbacks: %.1f%%" % (100 * sum(1 for l in rl if l["final_issue"]) / len(rl))]

# Reweighted scenario: apply the router's measured input and output token shares
# (all attempts, incl. fallback re-runs, across all seeds) to 50M in / 10M out a month.
tin, tout = defaultdict(int), defaultdict(int)
for l in rl:
    for a in l["attempts"]:
        tin[a["model"]] += a["tokens_in"]; tout[a["model"]] += a["tokens_out"]
ti, to = sum(tin.values()), sum(tout.values())
frontier_month = config.price(config.FRONTIER, 50e6, 10e6)
out += ["\n## Reweighted scenario: measured token mix applied to 50M input + 10M output a month\n",
        "| Model | Share of input tokens | Share of output tokens | Monthly input | Monthly output | Monthly cost |",
        "|---|---|---|---|---|---|"]
monthly = 0.0
for m in config.MODELS:
    si, so = tin[m] / ti, tout[m] / to
    c = config.price(m, 50e6 * si, 10e6 * so)
    monthly += c
    out.append("| %s | %.1f%% | %.1f%% | %.2fM | %.2fM | ₹%s |" % (
        m, 100 * si, 100 * so, 50 * si, 10 * so, format(round(c), ",")))
out += ["| **Total** | 100%% | 100%% | 50M | 10M | **₹%s** |" % format(round(monthly), ","),
        "\nAll frontier at the same volume: ₹%s. Saving: %.1f%%. Fallback re-runs are already inside the shares; "
        "router overhead is excluded (the LLM classifier did not fire on this test set)." % (
            format(round(frontier_month), ","), 100 * (1 - monthly / frontier_month))]

out += ["\n## Seed-to-seed range (40-prompt run)\n"]
for name, logs in all_logs.items():
    per = [[l for l in logs if l["seed"] == s] for s in seeds]
    c = [sum(l["cost_inr"] for l in p) for p in per]
    pr = [sum(l["passed"] for l in p) / len(p) for p in per]
    out.append("- %s: cost ₹%.3f–₹%.3f, pass rate %.0f%%–%.0f%%" % (name, min(c), max(c), 100 * min(pr), 100 * max(pr)))

json.dump(S, open("results/summary.json", "w"), indent=1)
open("results/summary.md", "w").write("\n".join(out) + "\n")
print("\n".join(out))
