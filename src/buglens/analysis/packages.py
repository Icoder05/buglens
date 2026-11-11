"""Aggregate modules into packages for the architecture block diagram — FR-G3.

Concept: a 3,000-module import graph is unreadable; an architecture diagram
needs ~15 boxes. We collapse modules into "packages" = the first `pkg_depth`
components of the module path (`django/db/models/query.py` -> `django/db`;
a top-level module like `flask/app.py` stays `flask/app`). An edge A -> B
counts the module-to-module imports from A's modules into B's modules. Only the
top `max_nodes` packages by summed PageRank are kept; the rest merge into one
`other` node so the diagram stays honest (nothing is silently dropped).
"""

from __future__ import annotations

import networkx as nx

from buglens.analysis.code_graph import CodeGraphs

OTHER = "other"


def package_of(module: str, depth: int) -> str:
    parts = [p for p in module.split(".") if p]
    return "/".join(parts[:depth]) if parts else "(root)"


def module_to_package(g: CodeGraphs, depth: int, max_nodes: int) -> dict[str, str]:
    """Module -> displayed package (top-N packages, everything else -> 'other')."""
    raw = {m: package_of(m, depth) for m in g.imports.nodes}
    pr_sum: dict[str, float] = {}
    for m, pkg in raw.items():
        pr_sum[pkg] = pr_sum.get(pkg, 0.0) + g.pagerank.get(m, 0.0)
    ranked = sorted(pr_sum, key=lambda p: (-pr_sum[p], p))
    keep = set(ranked[:max_nodes])
    return {m: (pkg if pkg in keep else OTHER) for m, pkg in raw.items()}


def package_graph(g: CodeGraphs, depth: int = 2, max_nodes: int = 15) -> nx.DiGraph:
    mapping = module_to_package(g, depth, max_nodes)
    pg = nx.DiGraph()
    for pkg in sorted(set(mapping.values())):
        mods = sorted(m for m, p in mapping.items() if p == pkg)
        pg.add_node(pkg, modules=mods, module_count=len(mods),
                    pagerank=sum(g.pagerank.get(m, 0.0) for m in mods),
                    is_entry=any(m in g.entry_modules for m in mods))
    for a, b in sorted(g.imports.edges):
        pa, pb = mapping[a], mapping[b]
        if pa == pb:
            continue  # FR-G3: drop self-loops
        if pg.has_edge(pa, pb):
            pg[pa][pb]["weight"] += 1
        else:
            pg.add_edge(pa, pb, weight=1)
    return pg


def top_packages(pg: nx.DiGraph, n: int = 10) -> list[str]:
    nodes = [p for p in pg.nodes if p != OTHER]
    return sorted(nodes, key=lambda p: (-pg.nodes[p]["pagerank"], p))[:n]
