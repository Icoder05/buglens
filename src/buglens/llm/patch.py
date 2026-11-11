"""Stretch M10: generate candidate patches from the localized functions.

Concept: localization is the first half of automated repair. Given the top-3
functions from a localizer (S8, else S6), Gemini proposes *edits* as exact
(original snippet -> replacement) pairs instead of a raw diff: LLMs often get
diff hunk headers wrong, while an exact-match search/replace is easy to check.
Each edit must match exactly once in a candidate file at `base_commit`; the
edited file is diffed with `difflib` into a git-style unified diff. Output is
SWE-bench's predictions format, to be scored by the official Docker harness
(`make harness`, run manually; it needs Docker/Linux or WSL2 and many GB).
"""

from __future__ import annotations

import difflib
import json

from buglens.chunking.corpus import load_corpus
from buglens.config import Config, write_meta
from buglens.data.repos import read_files
from buglens.data.swebench import load_split
from buglens.eval.evaluate import load_run
from buglens.llm.client import LLMClient, QuotaExhausted, RequestCapReached
from buglens.utils import console, summary, write_jsonl

SCHEMA = {
    "type": "object",
    "properties": {
        "edits": {"type": "array", "items": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "original": {"type": "string"},
                           "replacement": {"type": "string"}},
            "required": ["path", "original", "replacement"]}},
        "explanation": {"type": "string"},
    },
    "required": ["edits", "explanation"],
}


def unified_diff(path: str, before: str, after: str) -> str:
    if before == after:
        return ""
    a = before.splitlines(keepends=True)
    b = after.splitlines(keepends=True)
    for lines in (a, b):
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
    body = "".join(difflib.unified_diff(a, b, fromfile=f"a/{path}", tofile=f"b/{path}"))
    return f"diff --git a/{path} b/{path}\n{body}"


def apply_edits(files: dict[str, str], edits: list[dict]) -> tuple[dict[str, str], list[str]]:
    """Apply exact search/replace edits; each `original` must occur exactly once."""
    new = dict(files)
    problems = []
    for e in edits:
        path, orig, repl = e.get("path"), e.get("original", ""), e.get("replacement", "")
        if path not in new:
            problems.append(f"{path}: not a candidate file")
            continue
        count = new[path].count(orig) if orig else 0
        if count != 1:
            problems.append(f"{path}: original snippet matched {count} times")
            continue
        new[path] = new[path].replace(orig, repl, 1)
    return new, problems


def generate_patches(cfg: Config, system: str = "S8", limit: int = 30, split: str = "test"
                     ) -> str:
    src_system = system
    if not (cfg.path("runs") / f"{system}_{split}.jsonl").exists():
        src_system = "S6"
        console.print(f"[yellow]{system} run missing; using S6 localization[/yellow]")
    runs = {r.instance_id: r for r in load_run(cfg, src_system, split)}
    instances = [i for i in load_split(cfg, split) if i.instance_id in runs][:limit]
    client = LLMClient(cfg)
    preds, log = [], []
    for inst in instances:
        top = sorted(runs[inst.instance_id].functions, key=lambda c: c.rank)[:3]
        corpus = load_corpus(cfg, inst.repo, inst.base_commit)
        by_id = {c.chunk_id: c for c in corpus.chunks}
        paths = sorted({c.path for c in top})
        files = read_files(cfg, inst.repo, inst.base_commit, paths)
        blocks = []
        for c in top:
            ch = by_id[c.chunk_id]
            lines = files.get(ch.path, "").splitlines()[ch.start_line - 1:ch.end_line][:150]
            blocks.append(f"### {ch.path} ({ch.qualname}, lines {ch.start_line}-{ch.end_line})"
                          "\n```python\n" + "\n".join(lines) + "\n```")
        prompt = "\n".join([
            "Fix the issue below by editing the code shown. Return JSON `edits`: each edit has "
            "`path`, an `original` snippet copied EXACTLY from the code (enough lines to be "
            "unique, no line numbers) and its `replacement`. Keep edits minimal.",
            "", "## Issue", inst.problem_statement[: cfg.llm.max_issue_chars], "",
            "## Code (most likely locations first)", *blocks])
        try:
            data, usage = client.generate_json(prompt, SCHEMA, inst.instance_id)
        except (QuotaExhausted, RequestCapReached) as e:
            console.print(f"[red]stopping early: {e}[/red]")
            break
        edits = (data or {}).get("edits", []) if isinstance(data, dict) else []
        new, problems = apply_edits(files, edits if isinstance(edits, list) else [])
        patch = "".join(unified_diff(p, files[p], new[p]) for p in paths if p in files)
        preds.append({"instance_id": inst.instance_id,
                      "model_name_or_path": f"buglens-{src_system}-{cfg.llm.model}",
                      "model_patch": patch})
        log.append({"instance_id": inst.instance_id, "edits": len(edits),
                    "problems": problems, "patch_lines": patch.count("\n"),
                    "tokens_in": usage.tokens_in, "tokens_out": usage.tokens_out})
    out = cfg.path("runs") / f"patches_{split}.jsonl"
    write_jsonl(out, preds)
    (cfg.path("runs") / f"patches_{split}.log.json").write_text(json.dumps(log, indent=1))
    write_meta(out.parent, cfg, filename=f"patches_{split}.meta.json", source=src_system)
    non_empty = sum(1 for p in preds if p["model_patch"])
    console.print(client.report())
    summary("patch", source=src_system, instances=len(preds), non_empty=non_empty,
            out=str(out))
    console.print("Evaluate with the official harness (Docker; Linux or WSL2): `make harness`")
    return str(out)
