"""Run static analysis for a (repo, commit) from git, with caching — FR-A3, FR-A4.

Concept: the same analysis feeds two consumers. Localize needs import PageRank
at each of 300 test commits (reranker feature); Onboard needs full facts,
graphs and entry points at one commit per repo. Raw per-file facts are cached
per git blob (unchanged files are never re-parsed); the resolved facts for a
commit are written as JSON to `data/cache/facts/<repo>/<commit>.json`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from buglens.analysis.code_graph import CodeGraphs, build_graphs
from buglens.analysis.entry_points import console_scripts, find_entry_points
from buglens.analysis.facts import build_facts, extract_raw, module_name, source_roots
from buglens.config import Config
from buglens.data.repos import ensure_commit, list_py_files, list_tree, read_blobs, read_files
from buglens.kvstore import KVStore
from buglens.schemas import FileFacts
from buglens.utils import repo_slug, sha1

CONFIG_FILES = ("setup.py", "setup.cfg", "pyproject.toml")


@dataclass
class RepoAnalysis:
    repo: str
    commit: str
    facts: dict[str, FileFacts]
    raw: dict[str, dict]
    graphs: CodeGraphs
    entry_points: list[dict]
    file_lines: dict[str, int]
    parse_failures: int


_STORES: dict[str, KVStore] = {}
_MEMO: dict[tuple[str, str], RepoAnalysis] = {}


def _store(cfg: Config) -> KVStore:
    key = str(cfg.path("cache"))
    if key not in _STORES:
        _STORES[key] = KVStore(cfg.path("cache") / "facts_raw.sqlite", "raw")
    return _STORES[key]


def analyze_commit(cfg: Config, repo: str, commit: str) -> RepoAnalysis:
    if (repo, commit) in _MEMO:
        return _MEMO[(repo, commit)]
    ensure_commit(cfg, repo, commit)
    entries = list_py_files(cfg, repo, commit)
    keys = {e.path: sha1(f"facts-v1\n{e.blob}\n{e.path}") for e in entries}
    store = _store(cfg)
    cached = store.get_many(list(keys.values()))
    missing = [e for e in entries if keys[e.path] not in cached]
    if missing:
        texts = read_blobs(cfg, repo, [e.blob for e in missing])
        new = {}
        for e in missing:
            src = texts.get(e.blob, "")
            rec = extract_raw(e.path, src)
            rec["lines"] = len(src.splitlines())
            new[keys[e.path]] = rec
        store.put_many(new)
        cached.update(new)
    raw = {e.path: cached[keys[e.path]] for e in entries}

    top_level = {e.path for e in list_tree(cfg, repo, commit)} & set(CONFIG_FILES)
    config_files = read_files(cfg, repo, commit, sorted(top_level))
    roots = source_roots(sorted(raw))
    script_modules = {mod for _, mod, _ in console_scripts(config_files)}
    known = {module_name(p, roots) for p in raw}
    facts = build_facts(raw, main_targets=script_modules & known)
    graphs = build_graphs(facts, cfg.analysis.pagerank_alpha)
    eps = find_entry_points(facts, raw, config_files)
    graphs.entry_modules |= {e["module"] for e in eps}
    result = RepoAnalysis(repo, commit, facts, raw, graphs, eps,
                          {p: r.get("lines", 0) for p, r in raw.items()},
                          sum(not f.parse_ok for f in facts.values()))
    _write_facts_json(cfg, result)
    if len(_MEMO) > 3:
        _MEMO.pop(next(iter(_MEMO)))
    _MEMO[(repo, commit)] = result
    return result


def _write_facts_json(cfg: Config, a: RepoAnalysis) -> None:
    out = cfg.path("cache") / "facts" / repo_slug(a.repo) / f"{a.commit}.json"
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "repo": a.repo, "commit": a.commit,
        "files": [f.model_dump() for f in a.facts.values()],
        "entry_points": a.entry_points,
    }), encoding="utf-8")


def pagerank_by_path(cfg: Config, repo: str, commit: str) -> dict[str, float]:
    """Import-graph PageRank per file path, cached separately (cheap to load)."""
    out = cfg.path("cache") / "pagerank" / repo_slug(repo) / f"{commit}.json"
    if out.exists():
        return json.loads(out.read_text())
    a = analyze_commit(cfg, repo, commit)
    pr = {a.graphs.module_path[m]: v for m, v in a.graphs.pagerank.items()}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(pr))
    return pr
