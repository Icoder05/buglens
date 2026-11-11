from buglens.analysis.code_graph import build_graphs, unresolved_total
from buglens.analysis.entry_points import console_scripts, find_entry_points
from buglens.analysis.facts import extract_raw, facts_from_sources, module_name, source_roots
from buglens.analysis.packages import OTHER, package_graph, package_of


def _analysis(sources, pyproject):
    facts = facts_from_sources(sources, main_targets={"shop.cli"})
    graphs = build_graphs(facts)
    raw = {p: extract_raw(p, s) for p, s in sources.items()}
    eps = find_entry_points(facts, raw, {"pyproject.toml": pyproject})
    return facts, graphs, eps


def test_module_names_and_src_layout():
    assert module_name("shop/__init__.py", []) == "shop"
    assert module_name("shop/core.py", []) == "shop.core"
    paths = ["src/flask/__init__.py", "src/flask/app.py", "docs/conf.py"]
    roots = source_roots(paths)
    assert roots == ["src"]
    assert module_name("src/flask/app.py", roots) == "flask.app"


def test_exact_import_edges_including_relative(fixture_sources, fixture_pyproject):
    _, g, _ = _analysis(fixture_sources, fixture_pyproject)
    assert set(g.imports.edges) == {
        ("shop", "shop.core"),              # from .core import Base (package __init__)
        ("shop.models", "shop.core"),       # from . import core / from .core import ...
        ("shop.cli", "shop.core"),          # import shop.core as sc
        ("shop.cli", "shop.models"),        # from shop.models import Item
        ("billing.invoice", "shop.core"),   # from shop.core import Base, helper
        ("billing.invoice", "shop.models"), # from shop import models (submodule)
    }


def test_inheritance_edges(fixture_sources, fixture_pyproject):
    _, g, _ = _analysis(fixture_sources, fixture_pyproject)
    assert set(g.inheritance.edges) == {
        ("shop.models.Item", "shop.core.Base"),
        ("billing.invoice.Invoice", "shop.models.Item"),   # via module alias models.Item
        ("billing.invoice.Receipt", "shop.core.Base"),
    }


def test_call_resolution_counts(fixture_sources, fixture_pyproject):
    facts, g, _ = _analysis(fixture_sources, fixture_pyproject)
    assert set(g.calls.edges) == {
        ("shop.core.Base.save", "shop.core.helper"),
        ("shop.models.Item.total", "shop.core.helper"),
        ("shop.models.Item.describe", "shop.models.Item.total"),   # self.total
        ("shop.models.Item.describe", "shop.core.helper"),         # core.helper (alias)
        ("shop.cli.main", "shop.models.Item"),                     # constructor
        ("shop.cli.main", "shop.core.helper"),                     # sc.helper
        ("shop.cli.<module>", "shop.cli.main"),
        ("billing.invoice.Invoice.amount", "shop.models.Item.total"),  # self via base
        ("billing.invoice.Invoice.amount", "shop.core.helper"),
    }
    resolved = sum(1 for f in facts.values() for c in f.calls if c["resolved"])
    unresolved = sum(1 for f in facts.values() for c in f.calls if not c["resolved"])
    assert (resolved, unresolved) == (9, 2)  # unknown_func(), item.total(); print skipped
    assert unresolved_total(g) == 2
    assert g.calls.nodes["shop.models.Item.describe"]["unresolved"] == 1


def test_package_aggregation(fixture_sources, fixture_pyproject):
    _, g, _ = _analysis(fixture_sources, fixture_pyproject)
    assert package_of("django.db.models.query", 2) == "django/db"
    pg = package_graph(g, depth=1, max_nodes=15)
    assert set(pg.nodes) == {"shop", "billing"}
    assert pg.nodes["shop"]["module_count"] == 4
    assert list(pg.edges(data="weight")) == [("billing", "shop", 2)]
    capped = package_graph(g, depth=2, max_nodes=3)
    assert OTHER in capped.nodes and len(capped.nodes) == 4
    assert not any(a == b for a, b in capped.edges)


def test_hub_module_ranked_first(fixture_sources, fixture_pyproject):
    _, g, _ = _analysis(fixture_sources, fixture_pyproject)
    ranked = sorted(g.pagerank, key=lambda m: -g.pagerank[m])
    assert ranked[0] == "shop.core"


def test_entry_points(fixture_sources, fixture_pyproject):
    facts, _, eps = _analysis(fixture_sources, fixture_pyproject)
    assert console_scripts({"pyproject.toml": fixture_pyproject}) == [
        ("shop", "shop.cli", "main")]
    kinds = {(e["kind"], e["path"], e["line"]) for e in eps}
    assert ("__main__", "shop/cli.py", 13) in kinds
    assert ("console_script", "shop/cli.py", 6) in kinds
    assert facts["shop/cli.py"].is_entry_point
    assert not facts["shop/core.py"].is_entry_point


def test_parse_failure_never_crashes():
    facts = facts_from_sources({"bad.py": "print 'py2'\n", "ok.py": "x = 1\n"})
    assert facts["bad.py"].parse_ok is False
    assert facts["ok.py"].parse_ok is True


def test_deeply_nested_expression_never_crashes():
    # Parses fine, but the tree is deeper than the recursion limit (seen in sympy).
    deep = "x = f(1" + " + 1" * 20000 + ")\n"
    facts = facts_from_sources({"deep.py": deep, "ok.py": "y = 2\n"})
    assert facts["ok.py"].parse_ok is True
    assert facts["deep.py"].parse_ok in (True, False)  # either way: no exception
