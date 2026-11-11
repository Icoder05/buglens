"""`buglens index`: pre-build BM25 indexes or pre-encode dense embeddings for a split.

Concept: batching. Encoding all unique chunk texts of all commits in one large
call keeps the GPU busy (sentence-transformers sorts texts by length so each
batch has little padding), instead of thousands of small per-commit calls.
"""

from __future__ import annotations

from buglens.chunking.corpus import exclusion_counts, load_corpus
from buglens.config import Config
from buglens.data.swebench import load_split
from buglens.retrieval.bm25 import load_or_build
from buglens.retrieval.run import dense_model_id, group_by_commit
from buglens.utils import console, summary, track


def build_index(cfg: Config, split: str, retriever: str, model: str | None = None) -> None:
    instances = load_split(cfg, split)
    groups = group_by_commit(instances)
    if retriever == "bm25":
        stats = {"files": 0, "chunks": 0, "parse_failures": 0, "window_chunks": 0}
        excl = {"py_files": 0, "excluded_pattern": 0, "excluded_size": 0}
        for (repo, commit), _ in track(groups, f"bm25 index {split}"):
            corpus = load_corpus(cfg, repo, commit)
            load_or_build(cfg, corpus)
            for k in stats:
                stats[k] += corpus.stats[k]
            for k, v in exclusion_counts(cfg, repo, commit).items():
                excl[k] += v
        console.print(f"exclusions (summed over commits): {excl}")
        summary("index", retriever="bm25", split=split, commits=len(groups), **stats)
        return

    from buglens.retrieval.dense import DenseEncoder, report_cache

    model_id = model or dense_model_id(cfg, "dense" if retriever == "dense" else "dense_ft")
    enc = DenseEncoder(cfg, model_id)
    texts: dict[str, None] = {}
    for (repo, commit), _ in track(groups, f"collect chunks {split}"):
        for c in load_corpus(cfg, repo, commit).chunks:
            texts[c.text] = None
    console.print(f"{len(texts)} unique chunk texts across {len(groups)} commits")
    unique = list(texts)
    step = 20000
    for i in range(0, len(unique), step):
        enc.encode_docs(unique[i:i + step])
        console.print(f"  encoded {min(i + step, len(unique))}/{len(unique)}")
    report_cache(enc)
    summary("index", retriever=retriever, model=model_id, split=split, texts=len(unique))
