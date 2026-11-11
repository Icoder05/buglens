"""Small shared helpers: console logging, JSONL I/O, hashing, path patterns.

Concept: research code produces many intermediate files. Writing them as JSONL
(one JSON object per line) keeps them append-friendly, streamable and diffable,
and pydantic models round-trip through them losslessly. Every command ends with
one summary line (`summary`) so a long pipeline log stays skimmable.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

console = Console()
T = TypeVar("T", bound=BaseModel)


def sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def repo_slug(repo: str) -> str:
    """'django/django' -> 'django__django' (used for directory names)."""
    return repo.replace("/", "__")


def write_jsonl(path: str | Path, rows: Iterable[BaseModel | dict]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            line = row.model_dump_json() if isinstance(row, BaseModel) else json.dumps(row)
            f.write(line + "\n")
            n += 1
    return n


def read_jsonl(path: str | Path, model: type[T] | None = None) -> list:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                out.append(model.model_validate_json(line) if model else json.loads(line))
    return out


def progress() -> Progress:
    return Progress(
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    )


def track(items: list, description: str) -> Iterator:
    """Iterate with a rich progress bar."""
    with progress() as p:
        task = p.add_task(description, total=len(items))
        for item in items:
            yield item
            p.advance(task)


def summary(command: str, **fields) -> None:
    """One summary line per command (NFR logging)."""
    parts = " ".join(f"{k}={v}" for k, v in fields.items())
    console.print(f"[bold green]✓ {command}[/bold green] {parts}")


def md_table(rows: list[dict], cols: list[str] | None = None) -> str:
    """Render a list of dicts as a GitHub Markdown table."""
    if not rows:
        return ""
    cols = cols or list(rows[0])
    out = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")).replace("|", "\\|") for c in cols) + " |")
    return "\n".join(out)


def compile_patterns(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p) for p in patterns]


def matches_any(path: str, patterns: list[re.Pattern]) -> bool:
    return any(p.search(path) for p in patterns)


TEST_PATTERNS = compile_patterns(
    [r"(^|/)tests?/", r"(^|/)test_[^/]*\.py$", r"_test\.py$", r"(^|/)conftest\.py$",
     r"(^|/)testing/"]
)


def is_test_path(path: str) -> bool:
    return matches_any(path, TEST_PATTERNS)
