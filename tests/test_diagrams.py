import re
import shutil

import pytest

from buglens.analysis.code_graph import build_graphs
from buglens.analysis.facts import facts_from_sources
from buglens.onboard.diagrams import (
    DEdge,
    block_diagram,
    callflow_diagram,
    class_diagram,
    ensure_dot,
    mermaid_escape,
    neighbourhood_diagram,
    package_diagram,
    render_svg,
    to_mermaid,
    verify_diagram,
)
from buglens.onboard.highlight import highlight_map
from buglens.schemas import Candidate, GoldLabels, RankedResult


@pytest.fixture
def graphs(fixture_sources):
    facts = facts_from_sources(fixture_sources, main_targets={"shop.cli"})
    return build_graphs(facts), facts


def test_block_diagram_nodes_and_edges(graphs):
    g, _ = graphs
    spec = block_diagram(g, depth=1, max_nodes=15)
    assert set(spec.nodes) == {"shop", "billing"}
    assert [(e.src, e.dst, e.weight) for e in spec.edges] == [("billing", "shop", 2)]
    assert spec.nodes["shop"].label == "shop (4)"
    assert spec.nodes["shop"].attrs["entry"] is True       # shop/cli.py has __main__
    assert spec.nodes["billing"].attrs["entry"] is False
    report = verify_diagram(spec, g)
    assert report["ok"] and report["verified_pct"] == 100.0


def test_max_nodes_cap_produces_other(graphs):
    g, _ = graphs
    spec = block_diagram(g, depth=2, max_nodes=3)
    assert "other" in spec.nodes and len(spec.nodes) == 4
    assert verify_diagram(spec, g)["verified_pct"] == 100.0


def test_all_diagram_kinds_verify_100(graphs):
    g, facts = graphs
    specs = [
        package_diagram(g, "shop", depth=1),
        class_diagram(g, "shop.models", facts["shop/models.py"].classes),
        class_diagram(g, "billing.invoice", facts["billing/invoice.py"].classes),
        callflow_diagram(g, "shop.cli.<module>"),
        neighbourhood_diagram(g, "shop.core"),
    ]
    for spec in specs:
        report = verify_diagram(spec, g)
        assert report["verified_pct"] == 100.0, (spec.kind, report["problems"])


def test_class_diagram_shows_external_base_grey(graphs):
    g, facts = graphs
    spec = class_diagram(g, "shop.models", facts["shop/models.py"].classes)
    assert spec.nodes["shop.core.Base"].kind == "external"
    assert [(e.src, e.dst) for e in spec.edges] == [("shop.models.Item", "shop.core.Base")]
    assert spec.nodes["shop.models.Item"].lines == ["total()", "describe()"]


def test_callflow_unresolved_node(graphs):
    g, _ = graphs
    spec = callflow_diagram(g, "shop.cli.<module>")
    assert {"shop.cli.main", "shop.models.Item", "shop.core.helper"} <= set(spec.nodes)
    assert spec.nodes["__unresolved__"].label == "unresolved (1)"
    assert "static approximation" in spec.title


def test_invented_edge_fails_verification(graphs):
    g, _ = graphs
    spec = block_diagram(g, depth=1)
    spec.edges.append(DEdge("shop", "billing", 1))
    report = verify_diagram(spec, g)
    assert not report["ok"] and report["verified_pct"] < 100.0


def test_wrong_weight_fails_verification(graphs):
    g, _ = graphs
    spec = block_diagram(g, depth=1)
    spec.edges[0].weight = 5
    assert not verify_diagram(spec, g)["ok"]


def test_mermaid_has_no_unescaped_special_characters(graphs):
    g, _ = graphs
    spec = block_diagram(g, depth=2)
    spec.nodes["shop/core"].label = 'we"ird <label> [x] {y} |z|'
    text = to_mermaid(spec)
    labels = re.findall(r'"([^"]*)"', text)
    assert labels
    for label in labels:
        stripped = re.sub(r"#\d+;", "", label)
        assert not re.search(r'["<>\[\]{}|]', stripped), label
    assert mermaid_escape('a"b') == "a#34;b"
    assert text.startswith("flowchart LR")
    ids = re.findall(r"^\s+(n_\w+)\[", text, flags=re.M)
    assert all(re.fullmatch(r"n_[A-Za-z0-9_]+", i) for i in ids)


def test_highlight_marks_predicted_and_gold_packages(graphs):
    g, _ = graphs
    spec = block_diagram(g, depth=1)
    cands = [Candidate(chunk_id="billing/invoice.py::Invoice.amount", path="billing/invoice.py",
                       scores={}, rank=1),
             Candidate(chunk_id="shop/core.py::helper", path="shop/core.py", scores={}, rank=2)]
    res = RankedResult(instance_id="x", system="S6", functions=cands,
                       files=["billing/invoice.py", "shop/core.py"], seconds=0.0)
    gold = GoldLabels(instance_id="x", files=["shop/models.py"], functions=[])
    marks = highlight_map(spec, g, res, gold)
    assert marks == {"billing": {"ranks": [1], "gold": False},
                     "shop": {"ranks": [2], "gold": True}}


def test_svg_renders_deterministically(graphs):
    ensure_dot()
    if not shutil.which("dot"):
        pytest.skip("Graphviz dot not installed")
    g, _ = graphs
    spec = block_diagram(g, depth=1)
    a, b = render_svg(spec), render_svg(spec)
    assert a == b and "<svg" in a
