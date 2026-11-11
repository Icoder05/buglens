"""Reciprocal Rank Fusion (RRF) — systems S3 and S5.

Concept: BM25 scores and cosine similarities live on incomparable scales, so
adding them needs fragile normalisation. RRF ignores scores and fuses *ranks*:
score(d) = sum over rankers of 1 / (k + rank_r(d)). A chunk ranked highly by
either ranker rises; one ranked well by both rises most. k (60 by default)
damps the advantage of the very top positions. Ties are broken by chunk id so
results are deterministic.
"""

from __future__ import annotations

import numpy as np


def rrf(rankings: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    """Fuse ranked id lists (best first). Returns [(id, score)] sorted by score desc, id asc."""
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))


def order_by_score(scores: np.ndarray) -> np.ndarray:
    """Indices sorted by score desc; ties broken by index (= chunk_id order)."""
    return np.lexsort((np.arange(len(scores)), -scores))


def ranks_from_scores(scores: np.ndarray) -> np.ndarray:
    """1-based rank of each row under `order_by_score`."""
    order = order_by_score(scores)
    ranks = np.empty(len(scores), dtype=np.int64)
    ranks[order] = np.arange(1, len(scores) + 1)
    return ranks


def files_from_chunks(chunk_paths: list[str]) -> list[str]:
    """FR-R7: file ranking = order of first occurrence in the chunk ranking."""
    return list(dict.fromkeys(chunk_paths))
