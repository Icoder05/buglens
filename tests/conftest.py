from pathlib import Path

import pytest

FIXTURE_REPO = Path(__file__).parent / "fixtures" / "fakerepo"


def _read_fixture() -> dict[str, str]:
    return {
        p.relative_to(FIXTURE_REPO).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(FIXTURE_REPO.rglob("*.py"))
    }


@pytest.fixture
def fixture_sources() -> dict[str, str]:
    """{posix path: source} for the tiny fake repo (2 packages, 6 modules)."""
    return _read_fixture()


@pytest.fixture
def fixture_pyproject() -> str:
    return (FIXTURE_REPO / "pyproject.toml").read_text(encoding="utf-8")


# Tiny patch against the fixture repo: a method body change (models.py:12), a
# module-level constant change (core.py:3), a pure addition inside a function
# (after core.py:7, inside `helper`) and a test-file change that must be ignored.
FIXTURE_PATCH = "\n".join([
    "diff --git a/shop/models.py b/shop/models.py",
    "--- a/shop/models.py",
    "+++ b/shop/models.py",
    "@@ -11,3 +11,3 @@ class Item(Base):",
    "     def total(self, qty):",
    "-        return helper(qty) * self.price",
    "+        return helper(qty) * self.price * core.RATE",
    " ",
    "diff --git a/shop/core.py b/shop/core.py",
    "--- a/shop/core.py",
    "+++ b/shop/core.py",
    "@@ -1,8 +1,9 @@",
    ' """Core utilities used everywhere."""',
    " ",
    "-RATE = 3",
    "+RATE = 4",
    " ",
    " ",
    " def helper(x):",
    '     """Double a value."""',
    "+    x = int(x)",
    "     return x * 2",
    "diff --git a/tests/test_core.py b/tests/test_core.py",
    "--- a/tests/test_core.py",
    "+++ b/tests/test_core.py",
    "@@ -1,1 +1,2 @@",
    " import shop",
    "+import billing",
    "",
])


@pytest.fixture
def fixture_patch() -> str:
    return FIXTURE_PATCH
