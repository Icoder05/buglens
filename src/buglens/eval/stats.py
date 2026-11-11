"""Uncertainty and significance for per-instance metrics — FR-E2.

Concept: 300 issues is a small sample, so every number needs an error bar.
- Bootstrap CI: resample the 300 instances with replacement 1,000 times,
  recompute the mean each time; the 2.5th/97.5th percentiles bound the mean.
- Paired bootstrap: two systems are scored on the *same* instances, so we
  resample instance indices once and compare both means on each resample;
  the CI of the difference (and how often it crosses 0) is the evidence.
- McNemar's test: for a binary metric (hit / miss) only discordant instances
  matter — b = A hit & B miss, c = A miss & B hit. Under "no difference" b ~
  Binomial(b + c, 0.5); we use the exact binomial test.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import binomtest


def bootstrap_ci(values, n_resamples: int = 1000, seed: int = 42, ci: float = 0.95
                 ) -> tuple[float, float, float]:
    v = np.asarray(values, dtype=float)
    if len(v) == 0:
        return float("nan"), float("nan"), float("nan")
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(v), size=(n_resamples, len(v)))
    means = v[idx].mean(axis=1)
    alpha = (1 - ci) / 2
    return float(v.mean()), float(np.quantile(means, alpha)), float(np.quantile(means, 1 - alpha))


def paired_bootstrap(a, b, n_resamples: int = 1000, seed: int = 42, ci: float = 0.95) -> dict:
    """Difference mean(a) - mean(b) with CI and a two-sided bootstrap p-value."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    assert a.shape == b.shape, "paired samples must align"
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(a), size=(n_resamples, len(a)))
    diffs = a[idx].mean(axis=1) - b[idx].mean(axis=1)
    alpha = (1 - ci) / 2
    p = 2 * min((diffs <= 0).mean(), (diffs >= 0).mean())
    return {"diff": float(a.mean() - b.mean()), "low": float(np.quantile(diffs, alpha)),
            "high": float(np.quantile(diffs, 1 - alpha)), "p": float(min(p, 1.0))}


def mcnemar(a, b) -> dict:
    """Exact McNemar test on binary outcomes (1 = hit)."""
    a = np.asarray(a).astype(bool)
    b = np.asarray(b).astype(bool)
    n01 = int((a & ~b).sum())  # a hit, b miss
    n10 = int((~a & b).sum())  # a miss, b hit
    n = n01 + n10
    p = 1.0 if n == 0 else float(binomtest(n01, n, 0.5).pvalue)
    return {"a_only": n01, "b_only": n10, "p": p}
