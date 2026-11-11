"""Import, inheritance and call graphs + PageRank — FR-G1, FR-G2.

Concept: a codebase is a graph. Modules point to the modules they import;
classes point to their base classes; functions point to the functions they
call. PageRank on the import graph (alpha = 0.85: a random walker follows an
import with prob. 0.85, jumps anywhere with 0.15) gives high scores to modules
that many important modules depend on — the "core" a newcomer should read
first, and (as reranker feature `import_pagerank`) a prior on where bugs
surface. All graphs come only from `FileFacts`; nothing is guessed by an LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import networkx as nx

from buglens.schemas import FileFacts

MODULE_NODE = "<module>"


@dataclass
class CodeGraphs:
    imports: nx.DiGraph
    inheritance: nx.DiGraph
    calls: nx.DiGraph
    pagerank: dict[str, float]
    module_path: dict[str, str]
    entry_modules: set[str] = field(default_factory=set)


def build_graphs(facts: dict[str, FileFacts], alpha: float = 0.85) -> CodeGraphs:
    imports = nx.DiGraph()
    inheritance = nx.DiGraph()
    calls = nx.DiGraph()
    module_path = {f.module: f.path for f in facts.values()}

    for path in sorted(facts):
        f = facts[path]
        imports.add_node(f.module, path=path, is_entry=f.is_entry_point)
    for path in sorted(facts):
        f = facts[path]
        for target in f.imports:
            if target in module_path:
                imports.add_edge(f.module, target)

    for path in sorted(facts):
        f = facts[path]
        for c in f.classes:
            inheritance.add_node(f"{f.module}.{c['name']}", path=path, line=c["start_line"],
                                 module=f.module, name=c["name"])
    for path in sorted(facts):
        f = facts[path]
        for c in f.classes:
            child = f"{f.module}.{c['name']}"
            for base in c.get("bases_resolved", []):
                if base in inheritance:
                    inheritance.add_edge(child, base)

    for path in sorted(facts):
        f = facts[path]
        calls.add_node(f"{f.module}.{MODULE_NODE}", path=path, line=1, module=f.module,
                       kind="module", unresolved=0)
        for fn in f.functions:
            calls.add_node(f"{f.module}.{fn['name']}", path=path, line=fn["start_line"],
                           module=f.module, kind="function", unresolved=0)
        for c in f.classes:
            calls.add_node(f"{f.module}.{c['name']}", path=path, line=c["start_line"],
                           module=f.module, kind="class", unresolved=0)
            for m in c["methods"]:
                calls.add_node(f"{f.module}.{c['name']}.{m['name']}", path=path,
                               line=m["start_line"], module=f.module, kind="method",
                               unresolved=0)
    for path in sorted(facts):
        f = facts[path]
        for call in f.calls:
            caller = f"{f.module}.{call['caller_qualname']}"
            if caller not in calls:
                continue
            target = call["resolved"]
            if target and target in calls:
                if calls.has_edge(caller, target):
                    calls[caller][target]["count"] += 1
                else:
                    calls.add_edge(caller, target, count=1)
            else:
                calls.nodes[caller]["unresolved"] += 1

    pagerank = nx.pagerank(imports, alpha=alpha) if imports.number_of_nodes() else {}
    entry_modules = {f.module for f in facts.values() if f.is_entry_point}
    return CodeGraphs(imports, inheritance, calls, pagerank, module_path, entry_modules)


def unresolved_total(g: CodeGraphs) -> int:
    return sum(d["unresolved"] for _, d in g.calls.nodes(data=True))


def pagerank_of_path(g: CodeGraphs) -> dict[str, float]:
    return {g.module_path[m]: pr for m, pr in g.pagerank.items() if m in g.module_path}
