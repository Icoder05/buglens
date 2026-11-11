from buglens.llm.patch import apply_edits, unified_diff
from buglens.llm.rerank import parse_ranking


def test_apply_edits_exact_once():
    files = {"a.py": "def f():\n    return 1\n"}
    new, problems = apply_edits(files, [{"path": "a.py", "original": "return 1",
                                         "replacement": "return 2"}])
    assert problems == [] and new["a.py"] == "def f():\n    return 2\n"


def test_apply_edits_rejects_ambiguous_or_missing():
    files = {"a.py": "x = 1\nx = 1\n"}
    _, problems = apply_edits(files, [{"path": "a.py", "original": "x = 1", "replacement": "y"},
                                      {"path": "b.py", "original": "x", "replacement": "y"},
                                      {"path": "a.py", "original": "zzz", "replacement": "y"}])
    assert len(problems) == 3


def test_unified_diff_is_git_style():
    d = unified_diff("pkg/a.py", "a\nb\n", "a\nc\n")
    assert d.startswith("diff --git a/pkg/a.py b/pkg/a.py\n--- a/pkg/a.py\n+++ b/pkg/a.py\n")
    assert "-b\n+c\n" in d
    assert unified_diff("x.py", "same\n", "same\n") == ""


def test_parse_ranking_filters_invalid_ids():
    ids = ["a::f", "b::g", "c::h"]
    assert parse_ranking({"ranking": ["b::g", "zzz", "b::g", "a::f"]}, ids) == ["b::g", "a::f"]
    assert parse_ranking({"ranking": ["zzz"]}, ids) is None
    assert parse_ranking(None, ids) is None
