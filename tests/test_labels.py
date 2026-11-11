from buglens.data.labels import gold_files, label_instance, original_lines
from buglens.schemas import Instance


def _instance(patch: str) -> Instance:
    return Instance(instance_id="fake__repo-1", repo="fake/repo", base_commit="0" * 40,
                    problem_statement="Item.total ignores RATE", patch=patch, split="test")


def test_gold_files_exclude_tests(fixture_patch):
    assert gold_files(fixture_patch) == ["shop/models.py", "shop/core.py"]


def test_original_lines(fixture_patch):
    lines = original_lines(fixture_patch)
    assert lines["shop/models.py"] == [12]       # removed line
    assert lines["shop/core.py"] == [3, 7]       # removed constant + insertion after line 7
    assert "tests/test_core.py" not in lines


def test_label_instance_maps_to_innermost_chunks(fixture_patch, fixture_sources):
    labels, problems = label_instance(_instance(fixture_patch), fixture_sources)
    assert problems == []
    assert labels.files == ["shop/models.py", "shop/core.py"]
    assert labels.functions == [
        "shop/models.py::Item.total",   # method body change
        "shop/core.py::<module>",       # module-level constant change
        "shop/core.py::helper",         # pure addition inside a function
    ]


def test_missing_file_is_reported(fixture_patch):
    labels, problems = label_instance(_instance(fixture_patch), {})
    assert labels.functions == []
    assert any("missing" in p for p in problems)


def test_added_file_not_gold():
    patch = "\n".join([
        "diff --git a/pkg/new.py b/pkg/new.py",
        "new file mode 100644",
        "--- /dev/null",
        "+++ b/pkg/new.py",
        "@@ -0,0 +1,1 @@",
        "+x = 1",
        "",
    ])
    assert gold_files(patch) == []
