"""BM25 lexical retrieval over the chunks of one (repo, commit) — system S1.

Concept: BM25 scores a document by summing, over query terms, an IDF weight
(rare terms count more) times a saturating term-frequency factor (the 5th
occurrence adds less than the 1st), normalised by document length (k1, b).
It is a strong baseline for bug localization because issues often quote exact
identifiers, file names and error messages. `bm25s` stores the index as a
sparse matrix, so scoring every chunk for a query is a fast sparse lookup.
"""

from __future__ import annotations

from pathlib import Path

import bm25s
import numpy as np

from buglens.chunking.corpus import Corpus
from buglens.config import Config
from buglens.retrieval.tokenize_code import tokenize
from buglens.utils import repo_slug


def index_dir(cfg: Config, repo: str, commit: str) -> Path:
    return cfg.path("indexes") / "bm25" / repo_slug(repo) / commit


def load_or_build(cfg: Config, corpus: Corpus) -> bm25s.BM25:
    """FR-R2: one index per (repo, commit), cached on disk."""
    d = index_dir(cfg, corpus.repo, corpus.commit)
    if (d / "params.index.json").exists():
        return bm25s.BM25.load(str(d), show_progress=False)
    retriever = bm25s.BM25()
    retriever.index([tokenize(c.text) for c in corpus.chunks], show_progress=False)
    d.mkdir(parents=True, exist_ok=True)
    retriever.save(str(d), show_progress=False)
    return retriever


def bm25_scores(cfg: Config, corpus: Corpus, query: str) -> np.ndarray:
    """Score every chunk (aligned with corpus.chunks)."""
    retriever = load_or_build(cfg, corpus)
    tokens = tokenize(query)
    if not tokens:
        return np.zeros(len(corpus.chunks), dtype=np.float32)
    return np.asarray(retriever.get_scores(tokens), dtype=np.float32)
