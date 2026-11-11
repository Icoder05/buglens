"""Ranking metrics for localization — FR-E1.

Concept: we score a ranked list against a *set* of gold items.
- Acc@k ("hit@k"): 1 if any gold item is in the top k. Answers "would a
  developer reading the top k results find a place to fix?".
- MRR: 1 / rank of the first gold item (0 if absent). Rewards putting it first.
- Recall@k: fraction of the gold items found in the top k (multi-function fixes).
Each metric is computed per instance and then averaged, so confidence
intervals can be bootstrapped over instances. An empty gold set or an empty
prediction list scores 0 (conservative, and identical for every system).
"""

from __future__ import annotations

import pandas as pd

from buglens.schemas import GoldLabels, RankedResult

METRICS = ["file_acc@1", "file_acc@3", "file_acc@5", "file_mrr",
           "func_acc@5", "func_acc@10", "func_recall@10", "func_mrr"]


def acc_at_k(pred: list[str], gold: list[str], k: int) -> float:
    return 1.0 if set(pred[:k]) & set(gold) else 0.0


def recall_at_k(pred: list[str], gold: list[str], k: int) -> float:
    if not gold:
        return 0.0
    return len(set(pred[:k]) & set(gold)) / len(set(gold))


def reciprocal_rank(pred: list[str], gold: list[str]) -> float:
    gold_set = set(gold)
    for rank, item in enumerate(pred, start=1):
        if item in gold_set:
            return 1.0 / rank
    return 0.0


def instance_metrics(result: RankedResult, labels: GoldLabels) -> dict[str, float]:
    files = result.files
    funcs = [c.chunk_id for c in sorted(result.functions, key=lambda c: c.rank)]
    return {
        "file_acc@1": acc_at_k(files, labels.files, 1),
        "file_acc@3": acc_at_k(files, labels.files, 3),
        "file_acc@5": acc_at_k(files, labels.files, 5),
        "file_mrr": reciprocal_rank(files, labels.files),
        "func_acc@5": acc_at_k(funcs, labels.functions, 5),
        "func_acc@10": acc_at_k(funcs, labels.functions, 10),
        "func_recall@10": recall_at_k(funcs, labels.functions, 10),
        "func_mrr": reciprocal_rank(funcs, labels.functions),
    }


def evaluate(results: list[RankedResult], labels: dict[str, GoldLabels]) -> pd.DataFrame:
    """Per-instance metric table (index = instance_id)."""
    rows = []
    for r in results:
        row = {"instance_id": r.instance_id, **instance_metrics(r, labels[r.instance_id]),
               "tokens": r.tokens_in + r.tokens_out, "seconds": r.seconds}
        rows.append(row)
    return pd.DataFrame(rows).set_index("instance_id")
