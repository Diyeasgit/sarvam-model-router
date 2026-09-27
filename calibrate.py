"""Fit the quality-probability table on the CALIBRATION set (never the held-out set).

Every model answers every calibration prompt; pass/fail is recorded against
the router's own view of the request (its estimated task/language/difficulty),
because that is all the router can see when it has to decide.

    python3 calibrate.py            # simulator, 8 repetitions per prompt
    python3 calibrate.py --live     # real endpoints (see README for env vars)
"""
import argparse
import sys

sys.path.insert(0, ".")
from data.prompts import CALIBRATION
from router import config
from router.backends import LiveBackend, SimBackend
from router.estimator import QualityEstimator
from router.policy import Router

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true")
ap.add_argument("--reps", type=int, default=8)
args = ap.parse_args()

backend = LiveBackend() if args.live else SimBackend(seed=12345)
reps = 1 if args.live else args.reps
est = QualityEstimator()
router = Router(backend, est)

for r in range(reps):
    for req in CALIBRATION:
        f, _, _ = router.classify(req)
        for model in config.MODELS:
            log = router.run(req, forced_model=model)
            est.observe(model, f, log["passed"])

est.save("results/estimator.json")
print("calibrated on %d prompts x %d models x %d reps -> results/estimator.json"
      % (len(CALIBRATION), len(config.MODELS), reps))
for model in config.MODELS:
    for lang in ("en", "mixed", "indic"):
        s, n = est.counts.get("%s|%s" % (model, lang), (0, 0))
        if n:
            print("  %-14s %-6s pass rate %.2f (n=%d)" % (model, lang, s / n, n))
