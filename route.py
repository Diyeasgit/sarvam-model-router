"""Explain a routing decision for one prompt (no model call).

    python3 route.py "mera card block karo, last 4 digits 4421"
    python3 route.py --voice "मेरा बैलेंस कितना है?"
"""
import argparse
import sys

sys.path.insert(0, ".")
from router import config as router_config
from router.backends import SimBackend
from router.estimator import QualityEstimator
from router.policy import Router, bar_for

ap = argparse.ArgumentParser()
ap.add_argument("prompt")
ap.add_argument("--voice", action="store_true")
ap.add_argument("--sla", type=float)
ap.add_argument("--use-case", help="e.g. call_summary, kyc_extraction, disposition_tagging")
args = ap.parse_args()

meta = {"channel": "voice", "latency_budget_ms": 1500} if args.voice else {}
if args.use_case:
    meta["use_case"] = args.use_case
if args.sla:
    meta["sla"] = args.sla
req = {"messages": [{"role": "user", "content": args.prompt}], "meta": meta}
router = Router(SimBackend(), QualityEstimator.load("results/estimator.json"), use_llm_classifier=False)
f, _, _ = router.classify(req)
rows = router.candidates(f, args.prompt)
chosen, tau, reason = router.decide(f, rows)
pin = (router_config.USE_CASES.get(args.use_case or "") or {}).get("pin")
if pin:
    chosen, reason = next(r for r in rows if r["model"] == pin), "pinned by contract rule"
print("task=%s (confidence %.2f)  language=%s  difficulty=%d  [%s]" % (
    f["task"], f["task_confidence"], f["lang_bucket"], f["difficulty"], ", ".join(f["difficulty_reasons"])))
print("quality bar = %.2f" % tau)
for r in rows:
    print("  %-12s P(pass)=%.2f  est cost Rs %.4f  est p95 %5d ms  %s" % (
        r["model"], r["p"], r["est_cost"], r["est_p95_ms"], r.get("excluded", "")))
print("-> %s   because: %s" % (chosen["model"], reason))
