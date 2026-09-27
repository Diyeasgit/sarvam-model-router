"""Quality-probability estimator: P(model passes | request features).

Starts from a hand-set prior (a rough skill score for each model) and is then
calibrated on a separate calibration set: every model runs every calibration
prompt, and pass/fail is counted per (model, task, language, difficulty)
cell. Sparse cells are shrunk towards their parents
(model -> model+lang -> model+task -> model+task+lang -> full cell), so a cell
with 2 observations barely moves the estimate and a cell with 40 dominates it.

This is deliberately a lookup table rather than a neural router: every
routing decision can be traced to "this model passed 11 of 12 Hindi
summarisation calls of this difficulty during calibration".
"""
import json
import math
from collections import defaultdict

from .features import diff_bucket

# Prior skill on a 1-5 difficulty scale, plus language adjustments. These are
# guesses before calibration and are intentionally coarse.
PRIOR_SKILL = {"llama-3.1-8b": 2.3, "sarvam-indic": 3.0, "llama-3.3-70b": 3.6, "frontier": 4.8}
PRIOR_LANG = {
    "llama-3.1-8b": {"indic": -1.0, "mixed": -0.6},
    "sarvam-indic": {"indic": 0.6, "mixed": 0.4},
    "llama-3.3-70b": {"indic": -0.5, "mixed": -0.2},
    "frontier": {"indic": -0.2},
}


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x))


class QualityEstimator:
    def __init__(self, k=4.0):
        self.k = k  # pseudo-count: how many observations a parent estimate is "worth"
        self.counts = defaultdict(lambda: [0, 0])  # key -> [passes, n]

    @staticmethod
    def _levels(model, f):
        t, l, d = f["task"], f["lang_bucket"], diff_bucket(f["difficulty"])
        return [(model,), (model, l), (model, t), (model, t, l), (model, t, l, d)]

    def prior(self, model, f):
        skill = PRIOR_SKILL[model] + PRIOR_LANG.get(model, {}).get(f["lang_bucket"], 0.0)
        return _sigmoid(1.6 * (skill - f["difficulty"] + 0.5))

    def p(self, model, f):
        """Return (probability, support) where support = observations in the finest cell."""
        p = self.prior(model, f)
        n_cell = 0
        for key in self._levels(model, f):
            s, n = self.counts.get("|".join(key), (0, 0))
            p = (s + self.k * p) / (n + self.k)
            n_cell = n
        return p, n_cell

    def observe(self, model, f, passed):
        for key in self._levels(model, f):
            c = self.counts["|".join(key)]
            c[0] += int(passed)
            c[1] += 1

    def save(self, path):
        with open(path, "w") as fh:
            json.dump({"k": self.k, "counts": dict(self.counts)}, fh, indent=1, sort_keys=True)

    @classmethod
    def load(cls, path):
        with open(path) as fh:
            data = json.load(fh)
        est = cls(k=data["k"])
        for key, v in data["counts"].items():
            est.counts[key] = list(v)
        return est
