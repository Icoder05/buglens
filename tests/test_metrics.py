import pytest

from buglens.eval.metrics import acc_at_k, instance_metrics, recall_at_k, reciprocal_rank
from buglens.schemas import Candidate, GoldLabels, RankedResult


def test_acc_at_k():
    assert acc_at_k(["a", "b", "c"], ["c"], 3) == 1.0
    assert acc_at_k(["a", "b", "c"], ["c"], 2) == 0.0


def test_no_hit_and_empty_lists():
    assert acc_at_k([], ["a"], 5) == 0.0
    assert acc_at_k(["a"], [], 5) == 0.0
    assert reciprocal_rank([], ["a"]) == 0.0
    assert reciprocal_rank(["x", "y"], ["a"]) == 0.0
    assert recall_at_k(["a"], [], 10) == 0.0
    assert recall_at_k([], ["a"], 10) == 0.0


def test_mrr_and_recall():
    assert reciprocal_rank(["x", "a", "b"], ["b", "a"]) == pytest.approx(0.5)
    assert recall_at_k(["a", "x", "b"], ["a", "b", "c", "d"], 2) == pytest.approx(0.25)
    assert recall_at_k(["a", "a"], ["a"], 10) == 1.0


def test_instance_metrics_uses_candidate_rank():
    cands = [Candidate(chunk_id="f.py::g", path="f.py", scores={}, rank=2),
             Candidate(chunk_id="e.py::h", path="e.py", scores={}, rank=1)]
    result = RankedResult(instance_id="i", system="S1", functions=cands,
                          files=["e.py", "f.py"], seconds=0.0)
    labels = GoldLabels(instance_id="i", files=["f.py"], functions=["f.py::g"])
    m = instance_metrics(result, labels)
    assert m["file_acc@1"] == 0.0 and m["file_acc@3"] == 1.0
    assert m["file_mrr"] == pytest.approx(0.5)
    assert m["func_mrr"] == pytest.approx(0.5)
    assert m["func_recall@10"] == 1.0
