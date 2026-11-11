"""Diagrams from static-analysis graphs only: Graphviz SVG + Mermaid — FR-V1..V7.

Concept: a diagram is a *view* of a graph, so it can be checked. Every diagram
is first built as a `DiagramSpec` whose nodes record which underlying graph
nodes they stand for (`members`: modules, classes or functions) and whose
edges carry the number of underlying edges they summarise. `verify_diagram`
re-derives each node and edge from the analysis graphs and must report 100%
before anything is rendered — this is the guarantee that no box or arrow was
invented (no LLM ever touches a diagram). Rendering is deterministic: nodes
and edges are emitted sorted by id, so SVGs are stable across runs.
"""

from __future__ import annotations

import os
import re
import shutil
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import graphviz
import networkx as nx

from buglens.analysis.code_graph import MODULE_NODE, CodeGraphs
from buglens.analysis.packages import OTHER, module_to_package, package_of

GREY = "#9e9e9e"
PALETTE = {"node": "#e8eef7", "border": "#4c6a92", "entry": "#1b3a5c", "other": "#eeeeee",
           "highlight": "#ffd54f", "gold": "#c62828"}


@dataclass
class DNode:
    id: str
    label: str
    members: list[str]
    kind: str  # package | module | external | class | function | other | unresolved
    attrs: dict = field(default_factory=dict)
    lines: list[str] = field(default_factory=list)  # extra rows (class methods)


@dataclass
class DEdge:
    src: str
    dst: str
    weight: int | None = None
    dashed: bool = False


@dataclass
class DiagramSpec:
    kind: str           # block | package | class | callflow | neighbourhood
    title: str
    source: str         # imports | inheritance | calls
    nodes: dict[str, DNode] = field(default_factory=dict)
    edges: list[DEdge] = field(default_factory=list)
    legend: str = ""
    unresolved_count: int = 0

    def add(self, node: DNode) -> None:
        self.nodes[node.id] = node


def truncate(label: str, n: int = 30) -> str:
    return label if len(label) <= n else label[: n - 1] + "…"


def ensure_dot() -> None:
    """Make the Graphviz `dot` binary findable on Windows default install paths."""
    if shutil.which("dot"):
        return
    for d in (r"C:\Program Files\Graphviz\bin", r"C:\Program Files (x86)\Graphviz\bin"):
        if Path(d, "dot.exe").exists():
            os.environ["PATH"] = d + os.pathsep + os.environ.get("PATH", "")
            return


# ------------------------------------------------------------------ builders
def block_diagram(g: CodeGraphs, depth: int = 2, max_nodes: int = 15, label_chars: int = 30
                  ) -> DiagramSpec:
    """FR-V1: packages as boxes, import counts on edges, entry packages bold."""
    mapping = module_to_package(g, depth, max_nodes)
    spec = DiagramSpec("block", "Architecture: packages and their imports", "imports",
                       legend="Box = package (module count). Arrow A→B = A imports B; "
                              "label = number of module imports (unlabelled = 1). Bold border = "
                              "contains an entry point. Grey 'other' = remaining packages merged.")
    for pkg in sorted(set(mapping.values())):
        mods = sorted(m for m, p in mapping.items() if p == pkg)
        is_entry = any(m in g.entry_modules for m in mods)
        kind = "other" if pkg == OTHER else "package"
        spec.add(DNode(pkg, f"{truncate(pkg, label_chars)} ({len(mods)})", mods, kind,
                       {"entry": is_entry}))
    weights: dict[tuple[str, str], int] = {}
    for a, b in g.imports.edges:
        pa, pb = mapping[a], mapping[b]
        if pa != pb:
            weights[(pa, pb)] = weights.get((pa, pb), 0) + 1
    spec.edges = [DEdge(a, b, w) for (a, b), w in sorted(weights.items())]
    return spec


def package_diagram(g: CodeGraphs, package: str, depth: int = 2, max_nodes: int = 15,
                    max_modules: int = 25, label_chars: int = 30) -> DiagramSpec:
    """FR-V2: modules inside one package + grey nodes for other packages it touches."""
    raw = {m: package_of(m, depth) for m in g.imports.nodes}
    display = module_to_package(g, depth, max_nodes)
    inside = sorted((m for m, p in raw.items() if p == package),
                    key=lambda m: (-g.pagerank.get(m, 0.0), m))
    if not inside:
        raise ValueError(f"package {package!r} has no modules")
    shown, rest = inside[:max_modules], inside[max_modules:]
    spec = DiagramSpec("package", f"Package {package}: modules and imports", "imports",
                       legend="Box = module. Grey = other package. Label = import count "
                              "(unlabelled = 1).")
    node_of: dict[str, str] = {}
    for m in shown:
        spec.add(DNode(m, truncate(m.rsplit(".", 1)[-1] if "." in m else m, label_chars),
                       [m], "module", {"entry": m in g.entry_modules}))
        node_of[m] = m
    if rest:
        oid = f"{package}::other"
        spec.add(DNode(oid, f"other ({len(rest)} modules)", rest, "other"))
        for m in rest:
            node_of[m] = oid
    weights: dict[tuple[str, str], int] = {}
    for a, b in g.imports.edges:
        a_in, b_in = a in node_of, b in node_of
        if not (a_in or b_in):
            continue
        src = node_of[a] if a_in else f"ext::{display[a]}"
        dst = node_of[b] if b_in else f"ext::{display[b]}"
        if src == dst:
            continue
        for nid, inside_flag, mod in ((src, a_in, a), (dst, b_in, b)):
            if not inside_flag and nid not in spec.nodes:
                pkg = display[mod]
                members = sorted(m for m, p in display.items() if p == pkg and m not in node_of)
                spec.add(DNode(nid, truncate(pkg, label_chars), members, "external"))
        weights[(src, dst)] = weights.get((src, dst), 0) + 1
    spec.edges = [DEdge(a, b, w) for (a, b), w in sorted(weights.items())]
    return spec


def class_diagram(g: CodeGraphs, module: str, facts_classes: list[dict],
                  max_methods: int = 8, label_chars: int = 30) -> DiagramSpec:
    """FR-V3: classes of one module with methods; in-repo bases elsewhere in grey."""
    spec = DiagramSpec("class", f"Classes in {module}", "inheritance",
                       legend="Arrow child→base = inherits. Grey = base class in another module.")
    for c in sorted(facts_classes, key=lambda c: c["name"]):
        cid = f"{module}.{c['name']}"
        names = [m["name"] for m in c["methods"]]
        rows = [truncate(n, label_chars) + "()" for n in names[:max_methods]]
        if len(names) > max_methods:
            rows.append(f"… +{len(names) - max_methods} more")
        spec.add(DNode(cid, truncate(c["name"], label_chars), [cid], "class", lines=rows))
    for cid in sorted(list(spec.nodes)):
        for base in sorted(g.inheritance.successors(cid)) if cid in g.inheritance else []:
            if base not in spec.nodes:
                spec.add(DNode(base, truncate(base.rsplit(".", 1)[-1], label_chars), [base],
                               "external"))
            spec.edges.append(DEdge(cid, base))
    return spec


def callflow_diagram(g: CodeGraphs, start: str, depth: int = 3, max_nodes: int = 20,
                     label_chars: int = 30) -> DiagramSpec:
    """FR-V4: BFS over resolved calls from `start`; unresolved calls -> one dashed node."""
    if start not in g.calls:
        raise ValueError(f"{start!r} is not a node of the call graph")
    seen = [start]
    queue = deque([(start, 0)])
    while queue and len(seen) < max_nodes:
        node, d = queue.popleft()
        if d >= depth:
            continue
        for nxt in sorted(g.calls.successors(node)):
            if nxt not in seen and len(seen) < max_nodes:
                seen.append(nxt)
                queue.append((nxt, d + 1))
    spec = DiagramSpec("callflow", f"Call flow from {start} (static approximation)", "calls",
                       legend="Solid = resolved static call. Dashed = calls that static "
                              "analysis could not resolve (dynamic dispatch, locals, externals).")
    for n in seen:
        data = g.calls.nodes[n]
        short = n[len(data["module"]) + 1:] if n.startswith(data["module"] + ".") else n
        if short == MODULE_NODE:
            short = f"{data['module']} (module)"
        spec.add(DNode(n, truncate(short, label_chars), [n], "function",
                       {"entry": n == start}))
    included = set(seen)
    spec.edges = [DEdge(a, b) for a, b in sorted(g.calls.subgraph(included).edges)]
    unresolved = sum(g.calls.nodes[n]["unresolved"] for n in seen)
    if unresolved:
        uid = "__unresolved__"
        spec.add(DNode(uid, f"unresolved ({unresolved})", [], "unresolved"))
        spec.unresolved_count = unresolved
        spec.edges += [DEdge(n, uid, dashed=True) for n in sorted(seen)
                       if g.calls.nodes[n]["unresolved"]]
    return spec


def neighbourhood_diagram(g: CodeGraphs, module: str, max_nodes: int = 20,
                          label_chars: int = 30) -> DiagramSpec:
    """FR-Q3: radius-1 import neighbourhood of a module."""
    if module not in g.imports:
        raise ValueError(f"{module!r} not in import graph")
    neigh = set(g.imports.successors(module)) | set(g.imports.predecessors(module))
    keep = sorted(neigh, key=lambda m: (-g.pagerank.get(m, 0.0), m))[: max_nodes - 1]
    spec = DiagramSpec("neighbourhood", f"Import neighbourhood of {module}", "imports",
                       legend="Arrow A→B = A imports B.")
    for m in sorted([module, *keep]):
        spec.add(DNode(m, truncate(m, label_chars), [m], "module", {"entry": m == module}))
    spec.edges = [DEdge(a, b, 1) for a, b in sorted(g.imports.subgraph(spec.nodes).edges)]
    return spec


# ------------------------------------------------------------------ verification
def verify_diagram(spec: DiagramSpec, graphs: CodeGraphs) -> dict:
    """FR-V6: every node and edge must exist in the underlying graph (with exact counts)."""
    graph: nx.DiGraph = {"imports": graphs.imports, "inheritance": graphs.inheritance,
                         "calls": graphs.calls}[spec.source]
    problems = []
    node_ok = 0
    for n in spec.nodes.values():
        if n.kind == "unresolved":
            members = [e.src for e in spec.edges if e.dst == n.id]
            expected = sum(graph.nodes[m]["unresolved"] for e in spec.edges if e.dst == n.id
                           for m in spec.nodes[e.src].members)
            ok = expected == spec.unresolved_count and expected > 0 and bool(members)
        else:
            ok = bool(n.members) and all(m in graph for m in n.members)
        node_ok += ok
        if not ok:
            problems.append(f"node {n.id}")
    edge_ok = 0
    for e in spec.edges:
        if e.dst not in spec.nodes or e.src not in spec.nodes:
            problems.append(f"edge {e.src}->{e.dst}: dangling")
            continue
        if spec.nodes[e.dst].kind == "unresolved":
            ok = all(graph.nodes[m]["unresolved"] > 0 for m in spec.nodes[e.src].members)
        else:
            src_m, dst_m = spec.nodes[e.src].members, set(spec.nodes[e.dst].members)
            count = sum(1 for a in src_m if a in graph for b in graph.successors(a)
                        if b in dst_m)
            ok = count > 0 and (e.weight is None or spec.kind in ("neighbourhood",)
                                or e.weight == count)
        edge_ok += ok
        if not ok:
            problems.append(f"edge {e.src}->{e.dst}")
    total_n, total_e = len(spec.nodes), len(spec.edges)
    pct = 100.0 * (node_ok + edge_ok) / max(total_n + total_e, 1)
    return {"kind": spec.kind, "title": spec.title, "nodes": total_n, "edges": total_e,
            "nodes_verified": node_ok, "edges_verified": edge_ok, "verified_pct": pct,
            "ok": not problems, "problems": problems}


# ------------------------------------------------------------------ rendering
def _gv_id(i: int) -> str:
    return f"n{i}"


def to_graphviz(spec: DiagramSpec, highlight: dict[str, dict] | None = None) -> graphviz.Digraph:
    highlight = highlight or {}
    dot = graphviz.Digraph(spec.kind, format="svg")
    dot.attr(rankdir="LR" if spec.kind != "class" else "BT", fontname="Helvetica",
             label=f"{spec.title}\n{spec.legend}", labelloc="b", fontsize="10",
             nodesep="0.35", ranksep="0.6")
    dot.attr("node", shape="box", style="rounded,filled", fontname="Helvetica", fontsize="11",
             fillcolor=PALETTE["node"], color=PALETTE["border"])
    dot.attr("edge", color="#607d8b", fontname="Helvetica", fontsize="9", arrowsize="0.7")
    ids = {nid: _gv_id(i) for i, nid in enumerate(sorted(spec.nodes))}
    for nid in sorted(spec.nodes):
        n = spec.nodes[nid]
        attrs: dict[str, str] = {"tooltip": nid}
        label = n.label
        if n.kind == "class":
            body = "\\l".join(_rec(r) for r in n.lines) + ("\\l" if n.lines else "")
            attrs.update(shape="record", style="filled", label="{" + _rec(n.label) + "|" +
                         body + "}")
        elif n.kind in ("external", "other"):
            attrs.update(fillcolor=PALETTE["other"], color=GREY, fontcolor="#616161")
        elif n.kind == "unresolved":
            attrs.update(shape="ellipse", style="dashed", color=GREY, fontcolor="#616161",
                         fillcolor="white")
        if n.attrs.get("entry"):
            attrs.update(penwidth="2.5", color=PALETTE["entry"])
        if nid in highlight:
            h = highlight[nid]
            if h.get("ranks"):
                label += "\n★ predicted #" + ",#".join(str(r) for r in h["ranks"])
                attrs.update(fillcolor=PALETTE["highlight"])
            if h.get("gold"):
                attrs.update(color=PALETTE["gold"], penwidth="3", peripheries="2")
                label += "\n(gold fix)"
        if n.kind == "class":
            dot.node(ids[nid], **attrs)
        else:
            dot.node(ids[nid], label=label, **attrs)
    for e in sorted(spec.edges, key=lambda e: (e.src, e.dst)):
        attrs = {}
        if e.weight is not None and spec.kind in ("block", "package"):
            if e.weight > 1:  # unlabelled arrow = 1 import (stated in the legend)
                attrs["label"] = str(e.weight)
            attrs["penwidth"] = str(min(1 + e.weight / 10, 4))
        if e.dashed:
            attrs.update(style="dashed", color=GREY)
        if spec.kind == "class":
            attrs.update(arrowhead="empty")
        dot.edge(ids[e.src], ids[e.dst], **attrs)
    return dot


def _rec(text: str) -> str:
    """Escape Graphviz record-label special characters."""
    return re.sub(r"([{}|<>\"\\])", r"\\\1", text)


def render_svg(spec: DiagramSpec, highlight: dict[str, dict] | None = None) -> str:
    ensure_dot()
    return to_graphviz(spec, highlight).pipe(format="svg", encoding="utf-8")


_MERMAID_SAFE = re.compile(r"[A-Za-z0-9 _.,:/()+=*\-…★]")


def mermaid_escape(text: str) -> str:
    """FR-V7: anything outside a safe set becomes a numeric entity (#NN;)."""
    return "".join(ch if _MERMAID_SAFE.fullmatch(ch) else f"#{ord(ch)};" for ch in text)


def mermaid_ids(spec: DiagramSpec) -> dict[str, str]:
    out, used = {}, set()
    for nid in sorted(spec.nodes):
        slug = "n_" + re.sub(r"[^A-Za-z0-9_]", "_", nid)[:60]
        base, k = slug, 2
        while slug in used:
            slug = f"{base}_{k}"
            k += 1
        used.add(slug)
        out[nid] = slug
    return out


def to_mermaid(spec: DiagramSpec, highlight: dict[str, dict] | None = None) -> str:
    highlight = highlight or {}
    ids = mermaid_ids(spec)
    if spec.kind == "class":
        lines = ["classDiagram", f"  %% {mermaid_escape(spec.title)}"]
        for nid in sorted(spec.nodes):
            n = spec.nodes[nid]
            lines.append(f'  class {ids[nid]}["{mermaid_escape(n.label)}"] {{')
            for row in n.lines:
                lines.append(f"    +{re.sub(r'[^A-Za-z0-9_().… +]', '_', row)}")
            lines.append("  }")
        for e in sorted(spec.edges, key=lambda e: (e.src, e.dst)):
            lines.append(f"  {ids[e.dst]} <|-- {ids[e.src]}")
        return "\n".join(lines) + "\n"
    lines = ["flowchart LR", f"  %% {mermaid_escape(spec.title)}"]
    for nid in sorted(spec.nodes):
        n = spec.nodes[nid]
        label = n.label
        if nid in highlight and highlight[nid].get("ranks"):
            label += " ★ #" + ",#".join(str(r) for r in highlight[nid]["ranks"])
        shape = ("([", "])") if n.kind == "unresolved" else ("[", "]")
        lines.append(f'  {ids[nid]}{shape[0]}"{mermaid_escape(label)}"{shape[1]}')
    for e in sorted(spec.edges, key=lambda e: (e.src, e.dst)):
        arrow = "-.->" if e.dashed else "-->"
        if e.weight is not None and spec.kind in ("block", "package"):
            lines.append(f'  {ids[e.src]} {arrow}|"{e.weight}"| {ids[e.dst]}')
        else:
            lines.append(f"  {ids[e.src]} {arrow} {ids[e.dst]}")
    grey = [ids[n] for n in sorted(spec.nodes)
            if spec.nodes[n].kind in ("external", "other", "unresolved")]
    entry = [ids[n] for n in sorted(spec.nodes) if spec.nodes[n].attrs.get("entry")]
    hl = [ids[n] for n in sorted(highlight) if n in ids and highlight[n].get("ranks")]
    gold = [ids[n] for n in sorted(highlight) if n in ids and highlight[n].get("gold")]
    for cls, members, style in (("grey", grey, "fill:#eeeeee,stroke:#9e9e9e,color:#616161"),
                                ("entry", entry, "stroke:#1b3a5c,stroke-width:3px"),
                                ("pred", hl, "fill:#ffd54f"),
                                ("gold", gold, "stroke:#c62828,stroke-width:4px")):
        if members:
            lines.append(f"  classDef {cls} {style}")
            lines.append(f"  class {','.join(members)} {cls}")
    return "\n".join(lines) + "\n"


def write_diagram(spec: DiagramSpec, graphs: CodeGraphs, out_base: Path,
                  highlight: dict[str, dict] | None = None) -> dict:
    """Verify, then write <base>.svg, <base>.mmd and <base>.dot. Refuses unverified diagrams."""
    report = verify_diagram(spec, graphs)
    if not report["ok"]:
        raise ValueError(f"diagram failed verification: {report['problems'][:5]}")
    out_base.parent.mkdir(parents=True, exist_ok=True)
    dot = to_graphviz(spec, highlight)
    out_base.with_suffix(".dot").write_text(dot.source, encoding="utf-8")
    out_base.with_suffix(".svg").write_text(render_svg(spec, highlight), encoding="utf-8")
    out_base.with_suffix(".mmd").write_text(to_mermaid(spec, highlight), encoding="utf-8")
    return report


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text).strip("_") or "root"
