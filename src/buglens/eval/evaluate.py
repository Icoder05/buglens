"""`buglens eval`: score one system's run file against gold labels.

Concept: evaluation is a pure function of (run file, label file), so results
can always be recomputed from `runs/` without rerunning any model.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from rich.table import Table

from buglens.config import Config
from buglens.data.prepare import load_labels
from buglens.eval.metrics import METRICS, evaluate
from buglens.schemas import RankedResult
from buglens.utils import console, read_jsonl, summary


def load_run(cfg: Config, system: str, split: str) -> list[RankedResult]:
    path = cfg.path("runs") / f"{system}_{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found; run the system first.")
    return read_jsonl(path, RankedResult)


def metrics_path(cfg: Config, system: str, split: str) -> Path:
    return cfg.path("runs") / f"{system}_{split}.metrics.csv"


def eval_system(cfg: Config, system: str, split: str, quiet: bool = False) -> pd.DataFrame:
    results = load_run(cfg, system, split)
    labels = load_labels(cfg, split)
    df = evaluate(results, labels)
    df.to_csv(metrics_path(cfg, system, split))
    if not quiet:
        table = Table(title=f"{system} on {split} (n={len(df)})")
        for m in METRICS:
            table.add_column(m)
        table.add_row(*[f"{df[m].mean():.3f}" for m in METRICS])
        console.print(table)
        summary("eval", system=system, split=split, n=len(df),
                file_acc5=f"{df['file_acc@5'].mean():.3f}",
                func_acc10=f"{df['func_acc@10'].mean():.3f}")
    return df
