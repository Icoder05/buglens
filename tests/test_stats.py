import numpy as np
import pytest

from buglens.eval.stats import bootstrap_ci, mcnemar, paired_bootstrap


def test_bootstrap_ci_brackets_mean_and_is_deterministic():
    v = [1, 0, 1, 1, 0, 1, 0, 1, 1, 1]
    m, lo, hi = bootstrap_ci(v)
    assert m == pytest.approx(0.7)
    assert lo <= m <= hi
    assert bootstrap_ci(v) == (m, lo, hi)


def test_paired_bootstrap_detects_clear_difference():
    a = np.ones(100)
    b = np.r_[np.ones(50), np.zeros(50)]
    r = paired_bootstrap(a, b)
    assert r["diff"] == pytest.approx(0.5) and r["low"] > 0 and r["p"] < 0.05


def test_mcnemar_counts_and_null():
    r = mcnemar([1, 1, 0, 0, 1], [1, 0, 1, 0, 0])
    assert (r["a_only"], r["b_only"]) == (2, 1)
    assert mcnemar([1, 0], [1, 0])["p"] == 1.0
