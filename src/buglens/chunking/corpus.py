"""Build the chunk corpus of a repository at one commit (the shared index unit).

Concept: every retriever (BM25, dense, hybrid) and every onboarding feature
works over the same list of chunks for a `(repo, commit)`. The list is sorted
by chunk_id, so "row i" means the same chunk in BM25 scores, embedding
matrices and feature tables, and ties are broken by id. Chunks are cached per
git blob: a file unchanged between two commits is never parsed twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from buglens.chunking.python_ast import chunk_file
from buglens.config import Config
from buglens.data.repos import ensure_commit, list_py_files, list_tree, read_blobs
from buglens.kvstore import KVStore
from buglens.schemas import Chunk
from buglens.utils import compile_patterns, matches_any, sha1


@dataclass
class Corpus:
    repo: str
    commit: str
    chunks: list[Chunk]
    file_lines: dict[str, int] = field(default_factory=dict)  # path -> number of lines
    stats: dict = field(default_factory=dict)

    @property
    def ids(self) -> list[str]:
        return [c.chunk_id for c in self.chunks]


_STORE: dict[str, KVStore] = {}
_MEMO: dict[tuple[str, str], Corpus] = {}


def _store(cfg: Config) -> KVStore:
    key = str(cfg.path("cache"))
    if key not in _STORE:
        _STORE[key] = KVStore(cfg.path("cache") / "chunks.sqlite", "chunks")
    return _STORE[key]


def exclusion_counts(cfg: Config, repo: str, commit: str) -> dict[str, int]:
    """FR-D5 logging: how many .py files each rule removes."""
    patterns = compile_patterns(cfg.exclusions.path_patterns)
    py = [e for e in list_tree(cfg, repo, commit) if e.path.endswith(".py")]
    by_pattern = sum(matches_any(e.path, patterns) for e in py)
    too_big = sum(e.size > cfg.exclusions.max_file_bytes for e in py
                  if not matches_any(e.path, patterns))
    return {"py_files": len(py), "excluded_pattern": by_pattern, "excluded_size": too_big}


def load_corpus(cfg: Config, repo: str, commit: str) -> Corpus:
    if (repo, commit) in _MEMO:
        return _MEMO[(repo, commit)]
    ensure_commit(cfg, repo, commit)
    entries = list_py_files(cfg, repo, commit)
    c = cfg.chunking
    keys = {e.path: sha1(f"{e.blob}\n{e.path}\n{c.max_chars}") for e in entries}
    store = _store(cfg)
    cached = store.get_many(list(keys.values()))
    missing = [e for e in entries if keys[e.path] not in cached]
    if missing:
        texts = read_blobs(cfg, repo, [e.blob for e in missing])
        new = {}
        for e in missing:
            src = texts.get(e.blob, "")
            chunks, ok = chunk_file(e.path, src, c.max_chars, c.window_lines, c.window_overlap)
            new[keys[e.path]] = {"ok": ok, "lines": len(src.splitlines()),
                                 "chunks": [ch.model_dump() for ch in chunks]}
        store.put_many(new)
        cached.update(new)
    chunks: list[Chunk] = []
    file_lines: dict[str, int] = {}
    parse_fail = 0
    for e in entries:
        rec = cached[keys[e.path]]
        parse_fail += 0 if rec["ok"] else 1
        file_lines[e.path] = rec["lines"]
        chunks.extend(Chunk(**d) for d in rec["chunks"])
    chunks.sort(key=lambda ch: ch.chunk_id)
    corpus = Corpus(repo, commit, chunks, file_lines,
                    {"files": len(entries), "chunks": len(chunks), "parse_failures": parse_fail,
                     "window_chunks": sum(ch.kind == "window" for ch in chunks)})
    if len(_MEMO) > 4:
        _MEMO.pop(next(iter(_MEMO)))
    _MEMO[(repo, commit)] = corpus
    return corpus
