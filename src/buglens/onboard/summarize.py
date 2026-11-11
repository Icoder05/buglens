"""Grounded package summaries and a repo overview — FR-S1..S6.

Concept: retrieval-augmented, citation-checked summarisation. The LLM never
sees whole files; per package it sees only *facts* from static analysis: the
module list, the 10 most central symbols with `path:line`, signature and first
docstring line, and the neighbouring packages. It must answer in JSON where
every sentence cites `path:line`; the validator (strict mode) keeps only
citations inside the symbols it was shown. The overview is written from the
validated package sentences only, and inherits their citations. Summaries are
generated at each repo's *earliest* test base commit, so S6b (RQ4) cannot
benefit from code written after any evaluated bug.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from buglens.analysis.packages import package_of
from buglens.analysis.repo_analysis import RepoAnalysis, analyze_commit
from buglens.config import Config
from buglens.data.repos import repo_dir
from buglens.data.swebench import load_split
from buglens.llm.client import LLMClient, QuotaExhausted, RequestCapReached
from buglens.onboard.validate import Spans, validate_sentences
from buglens.schemas import PackageSummary, Sentence
from buglens.utils import console, repo_slug, summary

SENTENCES_SCHEMA = {
    "type": "object",
    "properties": {"sentences": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "citations": {"type": "array", "items": {
                "type": "object",
                "properties": {"path": {"type": "string"}, "line": {"type": "integer"}},
                "required": ["path", "line"]}},
        },
        "required": ["text", "citations"]}}},
    "required": ["sentences"],
}
OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {"sentences": {"type": "array", "items": {
        "type": "object",
        "properties": {"text": {"type": "string"},
                       "sources": {"type": "array", "items": {"type": "string"}}},
        "required": ["text", "sources"]}}},
    "required": ["sentences"],
}


def onboarding_dir(cfg: Config, repo: str) -> Path:
    return cfg.path("onboarding") / repo_slug(repo)


def onboarding_commit(cfg: Config, repo: str) -> str:
    """FR-S5: the earliest base commit (by commit date) among the repo's test instances."""
    commits = sorted({i.base_commit for i in load_split(cfg, "test") if i.repo == repo})
    if not commits:
        raise ValueError(f"{repo} has no SWE-bench Lite test instances; pass --commit")
    dates = {}
    for c in commits:
        out = subprocess.run(["git", "show", "-s", "--format=%ct", c], cwd=repo_dir(cfg, repo),
                             capture_output=True, text=True, check=True)
        dates[c] = int(out.stdout.strip())
    return min(commits, key=lambda c: (dates[c], c))


def package_modules(a: RepoAnalysis, depth: int) -> dict[str, list[str]]:
    pk: dict[str, list[str]] = {}
    for m in sorted(a.graphs.imports.nodes):
        pk.setdefault(package_of(m, depth), []).append(m)
    return pk


def ranked_packages(a: RepoAnalysis, depth: int) -> list[str]:
    pk = package_modules(a, depth)
    pr = {p: sum(a.graphs.pagerank.get(m, 0.0) for m in mods) for p, mods in pk.items()}
    return sorted(pk, key=lambda p: (-pr[p], p))


def package_symbols(a: RepoAnalysis, modules: list[str], top: int = 10) -> list[dict]:
    """Top symbols by (module PageRank, size): classes and top-level functions."""
    path_of = a.graphs.module_path
    syms = []
    for m in modules:
        f = a.facts[path_of[m]]
        pr = a.graphs.pagerank.get(m, 0.0)
        for c in f.classes:
            bases = ", ".join(c["bases"])
            syms.append({"path": f.path, "line": c["start_line"], "end": c["end_line"],
                         "signature": f"class {c['name']}({bases})" if bases
                         else f"class {c['name']}", "doc": c["docstring"], "pr": pr,
                         "size": c["end_line"] - c["start_line"]})
        for fn in f.functions:
            syms.append({"path": f.path, "line": fn["start_line"], "end": fn["end_line"],
                         "signature": f"def {fn['name']}{fn['signature']}", "doc": fn["docstring"],
                         "pr": pr, "size": fn["end_line"] - fn["start_line"]})
    syms.sort(key=lambda s: (-s["pr"], -s["size"], s["path"], s["line"]))
    return syms[:top]


def package_neighbours(a: RepoAnalysis, pkg: str, depth: int, n: int = 8
                       ) -> tuple[list[str], list[str]]:
    out_w: dict[str, int] = {}
    in_w: dict[str, int] = {}
    for x, y in a.graphs.imports.edges:
        px, py = package_of(x, depth), package_of(y, depth)
        if px == pkg and py != pkg:
            out_w[py] = out_w.get(py, 0) + 1
        elif py == pkg and px != pkg:
            in_w[px] = in_w.get(px, 0) + 1
    rank = lambda d: sorted(d, key=lambda k: (-d[k], k))[:n]  # noqa: E731
    return rank(out_w), rank(in_w)


def package_prompt(repo: str, pkg: str, modules: list[str], symbols: list[dict],
                   uses: list[str], used_by: list[str]) -> str:
    lines = [
        f"You are writing onboarding notes for the Python repository {repo}.",
        f"Describe the responsibilities of the package `{pkg}` in 2-4 sentences.",
        "Use ONLY the facts below. Every sentence must cite at least one `path` and `line` "
        "of a symbol listed below that supports it (use that symbol's line).",
        "Do not mention anything that is not supported by the listed symbols.",
        "",
        f"## Package `{pkg}` ({len(modules)} modules)",
        "Modules: " + ", ".join(modules[:40]) + (" …" if len(modules) > 40 else ""),
        "",
        "## Key symbols (path:line-end  signature — docstring)",
    ]
    for s in symbols:
        doc = f" — {s['doc']}" if s["doc"] else ""
        lines.append(f"- {s['path']}:{s['line']}-{s['end']}  {s['signature'][:200]}{doc}")
    lines += ["", "## Imports packages: " + (", ".join(uses) or "(none)"),
              "## Imported by packages: " + (", ".join(used_by) or "(none)")]
    return "\n".join(lines)


def summaries_path(cfg: Config, repo: str) -> Path:
    return onboarding_dir(cfg, repo) / "summaries.json"


def load_summaries(cfg: Config, repo: str) -> dict | None:
    path = summaries_path(cfg, repo)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def load_summary_texts(cfg: Config, repo: str) -> dict[str, str]:
    """{package: validated summary text} for S6b; {} when the repo has no summaries."""
    data = load_summaries(cfg, repo)
    if not data:
        return {}
    return {p["package"]: " ".join(s["text"] for s in p["sentences"])
            for p in data["packages"] if p["sentences"]}


def summarize_repo(cfg: Config, repo: str, max_packages: int | None = None,
                   client: LLMClient | None = None) -> dict:
    commit = onboarding_commit(cfg, repo)
    a = analyze_commit(cfg, repo, commit)
    depth = cfg.analysis.pkg_depth
    client = client or LLMClient(cfg)
    max_packages = max_packages or cfg.onboard.max_summary_packages
    pk = package_modules(a, depth)
    strict = cfg.onboard.strict_citations
    packages: list[PackageSummary] = []
    all_spans: Spans = {}
    stats = {"packages": 0, "sentences": 0, "kept": 0, "dropped": 0, "citations": 0,
             "valid_citations": 0}
    stopped = None
    for pkg in ranked_packages(a, depth)[:max_packages]:
        mods = pk[pkg]
        symbols = package_symbols(a, mods, cfg.onboard.summary_top_symbols)
        if not symbols:
            continue
        uses, used_by = package_neighbours(a, pkg, depth)
        spans: Spans = {}
        for s in symbols:
            spans.setdefault(s["path"], []).append((s["line"], s["end"]))
            all_spans.setdefault(s["path"], []).append((s["line"], s["end"]))
        prompt = package_prompt(repo, pkg, mods, symbols, uses, used_by)
        try:
            data, usage = client.generate_json(prompt, SENTENCES_SCHEMA)
        except (QuotaExhausted, RequestCapReached) as e:
            stopped = str(e)
            console.print(f"[red]stopping early: {e}[/red]")
            break
        raw = (data or {}).get("sentences", []) if isinstance(data, dict) else []
        kept, st = validate_sentences(raw, a.file_lines, spans, strict)
        for k in ("sentences", "kept", "dropped", "citations", "valid_citations"):
            stats[k] += st[k]
        stats["packages"] += 1
        packages.append(PackageSummary(repo=repo, commit=commit, package=pkg, sentences=kept,
                                       tokens_in=usage.tokens_in, tokens_out=usage.tokens_out))
        console.print(f"  {pkg}: kept {st['kept']}/{st['sentences']} sentences")

    overview, ov_stats = [], {"sentences": 0, "kept": 0, "dropped": 0}
    if not stopped:
        try:
            overview, ov_stats = _overview(cfg, client, repo, packages, a.file_lines, all_spans,
                                           strict)
        except (QuotaExhausted, RequestCapReached) as e:
            stopped = str(e)
    result = {"repo": repo, "commit": commit, "model": cfg.llm.model,
              "complete": stopped is None, "stopped_reason": stopped,
              "packages": [p.model_dump() for p in packages],
              "overview": [s.model_dump() for s in overview],
              "stats": {**stats, "overview": ov_stats}}
    out = summaries_path(cfg, repo)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1), encoding="utf-8")
    console.print(client.report())
    summary("summarize", repo=repo, commit=commit[:10], packages=len(packages),
            kept=stats["kept"], dropped=stats["dropped"], api_calls=client.requests)
    return result


def _overview(cfg: Config, client: LLMClient, repo: str, packages: list[PackageSummary],
              file_lines: dict[str, int], spans: Spans, strict: bool
              ) -> tuple[list[Sentence], dict]:
    ids: dict[str, Sentence] = {}
    lines = [f"Write a 4-6 sentence overview of the Python repository {repo} for a developer "
             "new to it, using ONLY the validated package notes below.",
             "For each sentence list in `sources` the ids (like P1.S2) of the notes it relies on.",
             ""]
    for i, p in enumerate(packages, start=1):
        for j, s in enumerate(p.sentences, start=1):
            sid = f"P{i}.S{j}"
            ids[sid] = s
            lines.append(f"[{sid}] ({p.package}) {s.text}")
    if not ids:
        return [], {"sentences": 0, "kept": 0, "dropped": 0}
    data, _ = client.generate_json("\n".join(lines), OVERVIEW_SCHEMA)
    raw = []
    for item in (data or {}).get("sentences", []) if isinstance(data, dict) else []:
        if not isinstance(item, dict):
            continue
        cits: list[dict] = []
        for sid in item.get("sources") or []:
            for c in ids.get(sid, Sentence(text="", citations=[], valid=False)).citations:
                if c.model_dump() not in cits:
                    cits.append(c.model_dump())
        raw.append({"text": item.get("text", ""), "citations": cits})
    kept, st = validate_sentences(raw, file_lines, spans, strict)
    return kept, {k: st[k] for k in ("sentences", "kept", "dropped")}
