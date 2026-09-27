"""Run the HELD-OUT set through the baselines and the router, and write the report.

Policies: always-cheapest, always-frontier, router (with fallback), and
router-without-fallback (an ablation that shows what the fallback adds).
The simulator is re-run over many seeds so no result depends on one lucky
draw; the per-request log for seed 0 is written to logs/.

    python3 evaluate.py              # simulator, 30 seeds
    python3 evaluate.py --live       # real endpoints, 1 pass
"""
import argparse
import json
import sys
from collections import Counter

sys.path.insert(0, ".")
from data.prompts import HELDOUT
from router import config
from router.backends import LiveBackend, SimBackend
from router.estimator import QualityEstimator
from router.policy import Router

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
ap.add_argument("--seeds", type=int, default=30)
args = ap.parse_args()

est = QualityEstimator.load("results/estimator.json")
POLICIES = [
    ("always-cheapest", dict(forced_model=config.CHEAPEST), {}),
    ("always-frontier", dict(forced_model=config.FRONTIER), {}),
    ("router", {}, {}),
    ("router-no-fallback", {}, dict(use_fallback=False)),
]


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def summarise(logs, n_runs):
    n = len(logs)
    return {
        "requests": n // n_runs,
        "cost_usd_per_run": sum(l["cost_usd"] for l in logs) / n_runs,
        "cost_usd_per_1k_req": sum(l["cost_usd"] for l in logs) / n * 1000,
        "router_overhead_usd_per_1k": sum(l["router_cost_usd"] for l in logs) / n * 1000,
        "p50_ms": pct([l["latency_ms"] for l in logs], 0.50),
        "p95_ms": pct([l["latency_ms"] for l in logs], 0.95),
        "mean_quality": sum(l["quality"] for l in logs) / n,
        "pass_rate": sum(l["passed"] for l in logs) / n,
        "fallback_rate": sum(l["fallback_fired"] for l in logs) / n,
        "unresolved_issue_rate": sum(1 for l in logs if l["final_issue"]) / n,
        "final_model_mix": {k: round(v / n, 3) for k, v in Counter(l["final_model"] for l in logs).items()},
    }


seeds = [0] if args.live else list(range(args.seeds))
all_logs = {}
for name, run_kw, router_kw in POLICIES:
    logs = []
    for s in seeds:
        backend = LiveBackend() if args.live else SimBackend(seed=1000 + s)
        router = Router(backend, est, **router_kw)
        for req in HELDOUT:
            log = router.run(req, **run_kw)
            log["policy"], log["seed"] = name, s
            logs.append(log)
    all_logs[name] = logs
    with open("logs/%s.jsonl" % name, "w") as fh:
        for l in logs:
            if l["seed"] == seeds[0]:
                fh.write(json.dumps(l, ensure_ascii=False) + "\n")

report = {"mode": "live" if args.live else "simulated", "seeds": len(seeds), "policies": {}}
for name, logs in all_logs.items():
    report["policies"][name] = {
        "all": summarise(logs, len(seeds)),
        "english": summarise([l for l in logs if l["gold_lang"] == "en"], len(seeds)),
        "indic_or_mixed": summarise([l for l in logs if l["gold_lang"] != "en"], len(seeds)),
    }
# seed-to-seed spread of router cost & pass rate (stability check)
per_seed = {}
for name, logs in all_logs.items():
    rows = []
    for s in seeds:
        sl = [l for l in logs if l["seed"] == s]
        rows.append((sum(l["cost_usd"] for l in sl), sum(l["passed"] for l in sl) / len(sl)))
    per_seed[name] = {"cost_min": min(r[0] for r in rows), "cost_max": max(r[0] for r in rows),
                      "pass_min": min(r[1] for r in rows), "pass_max": max(r[1] for r in rows)}
report["per_seed_range"] = per_seed
json.dump(report, open("results/summary.json", "w"), indent=1)

# ----------------------------------------------------------------- markdown
fr = report["policies"]["always-frontier"]["all"]["cost_usd_per_1k_req"]
out = ["# Results (%s, %d seeds x %d held-out prompts)\n" % (report["mode"], len(seeds), len(HELDOUT)),
       "| Policy | Cost / 1k req (USD) | Cost / 1k req (INR) | vs frontier | p50 latency | p95 latency | Mean quality | Pass rate | Fallback rate |",
       "|---|---|---|---|---|---|---|---|---|"]
for name in all_logs:
    a = report["policies"][name]["all"]
    out.append("| %s | $%.4f | ₹%.2f | %.0f%% | %.0f ms | %.0f ms | %.3f | %.1f%% | %.1f%% |" % (
        name, a["cost_usd_per_1k_req"], a["cost_usd_per_1k_req"] * config.FX_INR_PER_USD,
        100 * a["cost_usd_per_1k_req"] / fr, a["p50_ms"], a["p95_ms"], a["mean_quality"],
        100 * a["pass_rate"], 100 * a["fallback_rate"]))
out.append("\n## By language segment\n")
out.append("| Policy | Segment | Cost / 1k req | p95 | Pass rate |\n|---|---|---|---|---|")
for name in all_logs:
    for seg in ("english", "indic_or_mixed"):
        a = report["policies"][name][seg]
        out.append("| %s | %s | $%.4f | %.0f ms | %.1f%% |" % (name, seg, a["cost_usd_per_1k_req"], a["p95_ms"], 100 * a["pass_rate"]))
r = report["policies"]["router"]["all"]
out.append("\n## Router details\n")
out.append("- Final-model mix: " + ", ".join("%s %.0f%%" % (k, 100 * v) for k, v in sorted(r["final_model_mix"].items(), key=lambda kv: -kv[1])))
out.append("- Router overhead (LLM classifier calls), included above: $%.5f per 1k requests" % r["router_overhead_usd_per_1k"])
out.append("- Requests ending with an unresolved issue (timeout/refusal after all fallbacks): %.1f%%" % (100 * r["unresolved_issue_rate"]))
out.append("\n## Seed-to-seed range (cost per 40-prompt run, pass rate)\n")
for name, v in per_seed.items():
    out.append("- %s: $%.4f-$%.4f, pass %.0f%%-%.0f%%" % (name, v["cost_min"], v["cost_max"], 100 * v["pass_min"], 100 * v["pass_max"]))
open("results/summary.md", "w").write("\n".join(out) + "\n")
print("\n".join(out))
