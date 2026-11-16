"""Load SWE-bench Lite (test/dev) and SWE-bench (train), and guard against leakage.

Concept: SWE-bench pairs a real GitHub issue with the repository at the commit
*before* the fix (`base_commit`) and the gold fix (`patch`). Bug localization
asks: from the issue text alone, which files/functions does the patch touch?
Two kinds of leakage would make results meaningless: (1) the gold patch or the
tests reaching a model input (guarded in the LLM client and never passed to
retrieval), and (2) fine-tuning on the same repositories we evaluate on, which
would let the encoder memorise repo-specific vocabulary. `assert_no_leakage`
enforces (2): train repositories must be disjoint from test repositories.
"""

from __future__ import annotations

import json
from pathlib import Path

from buglens.config import Config
from buglens.schemas import Instance
from buglens.utils import console, read_jsonl, write_jsonl

# Fields that must never reach retrieval, features or prompts (PRD Section 17.3).
GOLD_FIELDS = ("patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS")


def _load_hf(ids: list[str], split: str):
    from datasets import load_dataset

    errors = []
    for dataset_id in ids:
        try:
            ds = load_dataset(dataset_id, split=split)
            console.print(f"[dim]loaded {dataset_id} split={split} ({len(ds)} rows)[/dim]")
            return dataset_id, ds
        except Exception as e:  # noqa: BLE001 - try the next id
            errors.append(f"{dataset_id}: {type(e).__name__}: {e}")
    raise RuntimeError("Could not load any dataset id:\n" + "\n".join(errors))


def _cache_path(cfg: Config, split: str) -> Path:
    return cfg.path("cache") / "instances" / f"{split}.jsonl"


def _secret_path(cfg: Config, split: str) -> Path:
    return cfg.path("cache") / "instances" / f"{split}_gold_texts.json"


def load_split(cfg: Config, split: str) -> list[Instance]:
    """Return instances for 'test'/'dev' (Lite) or 'train' (full SWE-bench), cached."""
    cache = _cache_path(cfg, split)
    if cache.exists():
        return read_jsonl(cache, Instance)
    ids = cfg.data.full_ids if split == "train" else cfg.data.lite_ids
    dataset_id, ds = _load_hf(ids, split)
    instances = [
        Instance(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            problem_statement=row["problem_statement"],
            hints_text=row.get("hints_text") or "",
            patch=row["patch"],
            split=split,
        )
        for row in ds
    ]
    write_jsonl(cache, instances)
    # Keep the other gold texts (tests) only for the LLM-client leakage guard.
    gold_texts = {
        row["instance_id"]: {f: _as_text(row.get(f)) for f in GOLD_FIELDS} for row in ds
    }
    _secret_path(cfg, split).write_text(json.dumps(gold_texts), encoding="utf-8")
    (cache.parent / f"{split}_source.txt").write_text(dataset_id, encoding="utf-8")
    return instances


def _as_text(value) -> str:
    if value is None:
        return ""
    return value if isinstance(value, str) else json.dumps(value)


def load_gold_texts(cfg: Config, split: str) -> dict[str, dict[str, str]]:
    """{instance_id: {patch, test_patch, FAIL_TO_PASS, PASS_TO_PASS}} for the leakage guard."""
    path = _secret_path(cfg, split)
    if not path.exists():
        load_split(cfg, split)
    return json.loads(path.read_text(encoding="utf-8"))


def assert_no_leakage(train_repos: set[str], test_repos: set[str]) -> None:
    """FR-D3: fine-tuning repositories must be disjoint from evaluation repositories."""
    overlap = sorted(set(train_repos) & set(test_repos))
    if overlap:
        raise ValueError(f"Train/test repository overlap (leakage): {overlap}")


def repos_of(instances: list[Instance]) -> list[str]:
    return sorted({i.repo for i in instances})
