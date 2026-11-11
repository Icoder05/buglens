"""Onboarding pipeline: analyze -> diagrams -> summarize -> guide -> bundle.

Concept: each stage writes files under `onboarding/<owner>__<repo>/`, so the
demo and the guide read only artifacts, and any stage can be rerun alone. The
bundle (`bundle.json`) indexes every artifact; `meta.json` pins the config and
code version that produced them (reproducibility NFR).
"""

from __future__ import annotations

import json
from pathlib import Path

from buglens.analysis.code_graph import MODULE_NODE, unresolved_total
from buglens.analysis.repo_analysis import RepoAnalysis, analyze_commit
from buglens.config import Config, write_meta
from buglens.data.repos import ensure_clone
from buglens.onboard.diagrams import (
    block_diagram,
    callflow_diagram,
    class_diagram,
    package_diagram,
    slug,
    write_diagram,
)
from buglens.onboard.guide import build_guide, key_classes, write_json
from buglens.onboard.summarize import (
    load_summaries,
    onboarding_commit,
    onboarding_dir,
    ranked_packages,
    summarize_repo,
)
from buglens.schemas import OnboardingBundle
from buglens.utils import console, summary


def resolve_commit(cfg: Config, repo: str, commit: str | None) -> str:
    ensure_clone(cfg, repo)
    return commit or onboarding_commit(cfg, repo)


def run_analyze(cfg: Config, repo: str, commit: str | None = None) -> RepoAnalysis:
    commit = resolve_commit(cfg, repo, commit)
    a = analyze_commit(cfg, repo, commit)
    g = a.graphs
    summary("analyze", repo=repo, commit=commit[:10], files=len(a.facts),
            parse_failures=a.parse_failures, modules=g.imports.number_of_nodes(),
            import_edges=g.imports.number_of_edges(),
            classes=g.inheritance.number_of_nodes(), call_edges=g.calls.number_of_edges(),
            unresolved_calls=unresolved_total(g), entry_points=len(a.entry_points))
    return a


def _entry_start(a: RepoAnalysis, e: dict) -> str | None:
    node = f"{e['module']}.{e['qualname']}" if e["qualname"] != MODULE_NODE else \
        f"{e['module']}.{MODULE_NODE}"
    return node if node in a.graphs.calls else None


def class_modules(a: RepoAnalysis, n: int = 15) -> list[str]:
    """Modules of the key classes first, then the most central modules that define classes."""
    mods: list[str] = []
    for c in key_classes(a):
        m = a.graphs.inheritance.nodes[c]["module"]
        if m not in mods:
            mods.append(m)
    by_pr = sorted(a.graphs.imports.nodes, key=lambda m: (-a.graphs.pagerank.get(m, 0.0), m))
    for m in by_pr:
        if len(mods) >= n:
            break
        f = a.facts[a.graphs.module_path[m]]
        if f.classes and m not in mods:
            mods.append(m)
    return mods[:n]


def run_diagrams(cfg: Config, repo: str, commit: str | None = None, package: str | None = None,
                 module: str | None = None, entry: str | None = None) -> dict:
    commit = resolve_commit(cfg, repo, commit)
    a = analyze_commit(cfg, repo, commit)
    g = a.graphs
    an, dg = cfg.analysis, cfg.diagrams
    base = onboarding_dir(cfg, repo)
    ddir = base / "diagrams"
    index_path = ddir / "index.json"
    index = json.loads(index_path.read_text()) if index_path.exists() else {}
    if index.get("commit") != commit:
        index = {"commit": commit, "packages": {}, "classes": {}, "callflow": {},
                 "reports": {}}
    reports = index["reports"]

    def emit(key: str, spec, rel: str) -> str:
        reports[key] = write_diagram(spec, g, ddir / rel)
        return f"diagrams/{rel}.svg"

    index["block"] = emit("block", block_diagram(g, an.pkg_depth, an.max_nodes,
                                                 dg.max_label_chars), "block")
    pkgs = [package] if package else ranked_packages(a, an.pkg_depth)[:10]
    for pkg in pkgs:
        spec = package_diagram(g, pkg, an.pkg_depth, an.max_nodes, dg.max_package_modules,
                               dg.max_label_chars)
        index["packages"][pkg] = emit(f"package:{pkg}", spec, f"packages/{slug(pkg)}")
    mods = [module] if module else class_modules(a)
    for m in mods:
        f = a.facts[g.module_path[m]]
        if not f.classes:
            continue
        spec = class_diagram(g, m, f.classes, dg.max_class_methods, dg.max_label_chars)
        index["classes"][m] = emit(f"class:{m}", spec, f"classes/{slug(m)}")
    if entry:
        starts = {entry: entry if entry in g.calls else None}
    else:
        starts = {e["name"]: _entry_start(a, e) for e in a.entry_points[:10]}
    for name, start in starts.items():
        if start is None:
            console.print(f"[yellow]no call-graph node for entry {name}[/yellow]")
            continue
        spec = callflow_diagram(g, start, dg.callflow_depth, dg.callflow_max_nodes,
                                dg.max_label_chars)
        index["callflow"][name] = emit(f"callflow:{name}", spec, f"callflow/{slug(name)}")

    total = sum(r["nodes"] + r["edges"] for r in reports.values())
    verified = sum(r["nodes_verified"] + r["edges_verified"] for r in reports.values())
    index["faithfulness"] = {"diagrams": len(reports),
                             "verified_pct": 100.0 * verified / max(total, 1),
                             "all_ok": all(r["ok"] for r in reports.values())}
    write_json(index_path, index)
    write_json(ddir / "faithfulness.json", {"repo": repo, "commit": commit, **reports})
    summary("diagrams", repo=repo, commit=commit[:10], diagrams=len(reports),
            verified=f"{index['faithfulness']['verified_pct']:.1f}%", out=str(ddir))
    return index


def run_guide(cfg: Config, repo: str) -> Path:
    commit = resolve_commit(cfg, repo, None)
    a = analyze_commit(cfg, repo, commit)
    base = onboarding_dir(cfg, repo)
    index_path = base / "diagrams" / "index.json"
    if not index_path.exists() or json.loads(index_path.read_text()).get("commit") != commit:
        run_diagrams(cfg, repo, commit)
    diagrams = json.loads(index_path.read_text())
    summaries = load_summaries(cfg, repo)
    if summaries and summaries.get("commit") != commit:
        summaries = None
    text = build_guide(cfg, a, summaries, diagrams, base)
    guide = base / "guide.md"
    guide.write_text(text, encoding="utf-8")

    st = (summaries or {}).get("stats", {})
    bundle = OnboardingBundle(
        repo=repo, commit=commit, block_svg="diagrams/block.svg",
        block_mermaid="diagrams/block.mmd", package_diagrams=diagrams["packages"],
        class_diagrams=diagrams["classes"], callflow_diagrams=diagrams["callflow"],
        guide_md="guide.md",
        stats={"files": len(a.facts), "parse_failures": a.parse_failures,
               "modules": a.graphs.imports.number_of_nodes(),
               "import_edges": a.graphs.imports.number_of_edges(),
               "classes": a.graphs.inheritance.number_of_nodes(),
               "inheritance_edges": a.graphs.inheritance.number_of_edges(),
               "call_nodes": a.graphs.calls.number_of_nodes(),
               "call_edges": a.graphs.calls.number_of_edges(),
               "unresolved_calls": unresolved_total(a.graphs),
               "entry_points": len(a.entry_points),
               "diagram_faithfulness_pct": diagrams["faithfulness"]["verified_pct"],
               "sentences_kept": st.get("kept", 0), "sentences_dropped": st.get("dropped", 0),
               "summaries_complete": bool(summaries and summaries.get("complete", True))})
    write_json(base / "bundle.json", bundle.model_dump())
    write_meta(base, cfg, repo=repo, commit=commit)
    summary("guide", repo=repo, out=str(guide))
    return guide


def run_onboard(cfg: Config, repo: str, with_llm: bool = True) -> Path:
    run_analyze(cfg, repo)
    run_diagrams(cfg, repo)
    if with_llm:
        from buglens.llm.client import load_api_key

        if load_api_key():
            summarize_repo(cfg, repo)
        else:
            console.print("[yellow]GEMINI_API_KEY not set: skipping summaries; the guide "
                          "will contain static sections only.[/yellow]")
    return run_guide(cfg, repo)
