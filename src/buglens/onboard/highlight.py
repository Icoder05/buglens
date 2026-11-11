"""Overlay Localize predictions on the architecture block diagram — FR-V5.

Concept: this joins the two modes. A ranked list of functions is hard to judge
without context; colouring the packages that contain the top-5 predictions
(with their ranks) shows *where in the architecture* the system thinks the bug
lives, and — in evaluation mode — whether the gold fix's package (red double
outline) was among them. Only node styles change, so the diagram still passes
`verify_diagram`.
"""

from __future__ import annotations

from buglens.analysis.code_graph import CodeGraphs
from buglens.analysis.repo_analysis import analyze_commit
from buglens.config import Config
from buglens.onboard.diagrams import DiagramSpec, block_diagram, render_svg, to_mermaid
from buglens.onboard.diagrams import verify_diagram as _verify
from buglens.schemas import GoldLabels, RankedResult


def highlight_map(spec: DiagramSpec, g: CodeGraphs, result: RankedResult,
                  gold: GoldLabels | None = None, top: int = 5) -> dict[str, dict]:
    path_to_module = {p: m for m, p in g.module_path.items()}
    module_to_node = {m: nid for nid, n in spec.nodes.items() for m in n.members}
    marks: dict[str, dict] = {}
    for cand in sorted(result.functions, key=lambda c: c.rank)[:top]:
        node = module_to_node.get(path_to_module.get(cand.path, ""))
        if node:
            marks.setdefault(node, {"ranks": [], "gold": False})["ranks"].append(cand.rank)
    if gold:
        for path in gold.files:
            node = module_to_node.get(path_to_module.get(path, ""))
            if node:
                marks.setdefault(node, {"ranks": [], "gold": False})["gold"] = True
    return marks


def highlighted_block(cfg: Config, repo: str, commit: str, result: RankedResult,
                      gold: GoldLabels | None = None) -> tuple[str, str, dict]:
    """(svg, mermaid, marks) for the block diagram at `commit` with predictions overlaid."""
    a = analyze_commit(cfg, repo, commit)
    spec = block_diagram(a.graphs, cfg.analysis.pkg_depth, cfg.analysis.max_nodes,
                         cfg.diagrams.max_label_chars)
    report = _verify(spec, a.graphs)
    if not report["ok"]:
        raise ValueError(f"block diagram failed verification: {report['problems'][:5]}")
    marks = highlight_map(spec, a.graphs, result, gold)
    return render_svg(spec, marks), to_mermaid(spec, marks), marks
