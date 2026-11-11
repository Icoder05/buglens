import pytest

from buglens.config import load_config
from buglens.data.swebench import assert_no_leakage


def test_disjoint_repos_pass():
    assert_no_leakage({"numpy/numpy", "pypa/pip"}, {"django/django", "sympy/sympy"})


def test_overlap_raises_with_overlap_listed():
    with pytest.raises(ValueError, match=r"django/django"):
        assert_no_leakage({"django/django", "pypa/pip"}, {"django/django", "sympy/sympy"})


def test_real_splits_are_disjoint_if_cached():
    """Uses the cached SWE-bench splits when `buglens data` has been run."""
    cfg = load_config()
    cache = cfg.path("cache") / "instances"
    if not (cache / "train.jsonl").exists() or not (cache / "test.jsonl").exists():
        pytest.skip("SWE-bench splits not cached yet")
    from buglens.data.swebench import load_split, repos_of

    train = set(repos_of(load_split(cfg, "train")))
    test = set(repos_of(load_split(cfg, "test")))
    assert_no_leakage(train, test)
