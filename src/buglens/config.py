"""Configuration loading and run metadata.

Concept: reproducibility in ML experiments means "same config + same code + same
seed => same numbers". All tunable values (paths, model ids, k values, seeds,
request caps) live in YAML, never as literals scattered through the code. Each
run then saves a `meta.json` snapshot holding the resolved config and the git
commit hash, so any result file can be matched to the exact code and settings
that produced it. `set_seed` fixes Python, NumPy and (if installed) PyTorch RNGs.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "configs" / "default.yaml"
EXPERIMENTS_CONFIG = PROJECT_ROOT / "configs" / "experiments.yaml"


class Config(dict):
    """A dict with attribute access (`cfg.retrieval.top_n`) for nested YAML."""

    def __getattr__(self, name: str) -> Any:
        try:
            value = self[name]
        except KeyError as e:
            raise AttributeError(name) from e
        return Config(value) if isinstance(value, dict) else value

    def path(self, key: str) -> Path:
        """Resolve `paths.<key>` relative to the project root."""
        return PROJECT_ROOT / self["paths"][key]


def load_config(path: str | Path | None = None) -> Config:
    with open(path or DEFAULT_CONFIG, encoding="utf-8") as f:
        return Config(yaml.safe_load(f))


def load_experiments(path: str | Path | None = None) -> Config:
    with open(path or EXPERIMENTS_CONFIG, encoding="utf-8") as f:
        return Config(yaml.safe_load(f))


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
    except ImportError:
        pass


def git_commit_hash() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def write_meta(out_dir: str | Path, cfg: Config, **extra: Any) -> Path:
    """Write meta.json (config snapshot + git hash + timestamp) next to a run's outputs."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "git_commit": git_commit_hash(),
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "config": dict(cfg),
        **extra,
    }
    path = out_dir / "meta.json"
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path
