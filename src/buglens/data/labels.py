"""Derive gold files and gold functions from a unified-diff patch.

Concept: SWE-bench does not label "the buggy function"; it gives the fix as a
diff. We recover labels by reading the diff in the *original* (pre-fix)
coordinates: a removed line `-` was buggy code at a known original line
number; a pure insertion `+` has no original line, so we attribute it to the
original line just before the insertion point (the code it extends). Each such
line is mapped to the innermost AST chunk containing it at `base_commit`
(method > function > class > module). Test files are excluded: localization is
about the source code that must change, not the tests that check it.
"""

from __future__ import annotations

from unidiff import PatchSet

from buglens.chunking.python_ast import chunk_file, innermost_chunk
from buglens.schemas import Chunk, GoldLabels, Instance
from buglens.utils import is_test_path


def _strip_prefix(path: str) -> str:
    return path[2:] if path.startswith(("a/", "b/")) else path


def gold_files(patch: str) -> list[str]:
    """FR-L1: modified (pre-existing) non-test source files touched by the patch."""
    files = []
    for pf in PatchSet(patch):
        if pf.is_added_file:
            continue
        path = _strip_prefix(pf.source_file)
        if path.endswith(".py") and not is_test_path(path) and path not in files:
            files.append(path)
    return files


def original_lines(patch: str) -> dict[str, list[int]]:
    """FR-L2: {path: [original line numbers]} for removed lines and insertion points."""
    result: dict[str, list[int]] = {}
    for pf in PatchSet(patch):
        if pf.is_added_file:
            continue
        path = _strip_prefix(pf.source_file)
        if not path.endswith(".py") or is_test_path(path):
            continue
        lines: list[int] = []
        for hunk in pf:
            last_source = hunk.source_start - 1  # original line before the hunk's first line
            for line in hunk:
                if line.is_removed or line.is_context:
                    if line.is_removed:
                        lines.append(line.source_line_no)
                    last_source = line.source_line_no
                elif line.is_added:
                    lines.append(max(last_source, 1))
        result[path] = sorted(set(lines))
    return result


def label_instance(instance: Instance, sources: dict[str, str], max_chars: int = 6000,
                   window: int = 60, overlap: int = 20) -> tuple[GoldLabels, list[str]]:
    """Map patch lines to chunk ids. `sources` = {path: file text at base_commit}.

    Returns (labels, problems) where problems lists unmappable lines/files.
    """
    files = gold_files(instance.patch)
    functions: list[str] = []
    problems: list[str] = []
    for path, lines in original_lines(instance.patch).items():
        if path not in sources:
            problems.append(f"{path}: missing at base_commit")
            continue
        chunks: list[Chunk] = chunk_file(path, sources[path], max_chars, window, overlap)[0]
        for ln in lines:
            chunk = innermost_chunk(chunks, ln)
            if chunk is None:
                problems.append(f"{path}:{ln}: no chunk")
            elif chunk.chunk_id not in functions:
                functions.append(chunk.chunk_id)
    return GoldLabels(instance_id=instance.instance_id, files=files, functions=functions), problems
