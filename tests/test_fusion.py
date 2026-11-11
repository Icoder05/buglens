import numpy as np
import pytest

from buglens.retrieval.fusion import files_from_chunks, order_by_score, ranks_from_scores, rrf


def test_rrf_hand_computed():
    # k = 60. a: 1/61 + 1/63 ; b: 1/62 + 1/61 ; c: 1/63 ; d: 1/62
    bm25 = ["a", "b", "c"]
    dense = ["b", "d", "a"]
    fused = dict(rrf([bm25, dense], k=60))
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 63)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 63)
    assert fused["d"] == pytest.approx(1 / 62)
    assert [d for d, _ in rrf([bm25, dense], k=60)] == ["b", "a", "d", "c"]


def test_rrf_ties_broken_by_id():
    fused = rrf([["z", "y"], ["y", "z"]], k=60)
    assert [d for d, _ in fused] == ["y", "z"]


def test_order_and_ranks_tie_by_index():
    s = np.array([0.5, 0.9, 0.5, 0.1])
    assert list(order_by_score(s)) == [1, 0, 2, 3]
    assert list(ranks_from_scores(s)) == [2, 1, 3, 4]


def test_files_first_occurrence():
    assert files_from_chunks(["b.py", "a.py", "b.py", "c.py"]) == ["b.py", "a.py", "c.py"]
