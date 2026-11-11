"""Split a Python file into retrieval units ("chunks") using its syntax tree.

Concept: retrieval quality depends on what a "document" is. Whole files are too
coarse (a 3,000-line module matches every query), fixed-size windows cut
functions in half. Python's `ast` module gives exact line spans for every
function, method and class, so each becomes one chunk; whatever is left at the
top level (imports, constants, `if __name__ == "__main__"`) becomes one module
chunk. Spans start at the first decorator and end at `end_lineno`, so a gold
line can later be mapped to the innermost chunk containing it. Files that do
not parse (e.g. Python 2 syntax) fall back to overlapping 60-line windows.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from buglens.schemas import Chunk
from buglens.utils import sha1

MODULE_QUALNAME = "<module>"
DefNode = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


@dataclass
class _Span:
    qualname: str
    kind: str
    start: int
    end: int
    child_spans: list[tuple[int, int]]  # spans removed from a class chunk's text


def _start_line(node: DefNode) -> int:
    lines = [node.lineno] + [d.lineno for d in node.decorator_list]
    return min(lines)


def _collect(body: list[ast.stmt], prefix: str, in_class: bool, out: list[_Span]) -> None:
    """Walk function/class definitions; nested functions inside functions stay in their parent."""
    for node in body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            out.append(_Span(prefix + node.name, "method" if in_class else "function",
                             _start_line(node), node.end_lineno or node.lineno, []))
        elif isinstance(node, ast.ClassDef):
            children = [
                (_start_line(c), c.end_lineno or c.lineno)
                for c in node.body
                if isinstance(c, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            ]
            out.append(_Span(prefix + node.name, "class", _start_line(node),
                             node.end_lineno or node.lineno, children))
            _collect(node.body, prefix + node.name + ".", True, out)


def _lines_excluding(lines: list[str], start: int, end: int,
                     holes: list[tuple[int, int]]) -> str:
    keep = []
    for ln in range(start, end + 1):
        if not any(s <= ln <= e for s, e in holes):
            keep.append(lines[ln - 1])
    return "\n".join(keep)


def embed_text(path: str, qualname: str, source: str, max_chars: int) -> str:
    """FR-C4: the text the encoders see. Labels always use the full span."""
    return f"{path}\n{qualname}\n{source}"[:max_chars]


def _make_chunk(path: str, qualname: str, kind: str, start: int, end: int, source: str,
                max_chars: int, chunk_id: str | None = None) -> Chunk:
    text = embed_text(path, qualname, source, max_chars)
    return Chunk(chunk_id=chunk_id or f"{path}::{qualname}", path=path, qualname=qualname,
                 kind=kind, start_line=start, end_line=end, text=text, text_sha1=sha1(text))


def window_chunks(path: str, source: str, max_chars: int, window: int = 60,
                  overlap: int = 20) -> list[Chunk]:
    """FR-C3 fallback: overlapping line windows."""
    lines = source.splitlines()
    n = max(len(lines), 1)
    chunks = []
    step = window - overlap
    start = 1
    while True:
        end = min(start + window - 1, n)
        q = f"L{start}-{end}"
        chunks.append(_make_chunk(path, q, "window", start, end,
                                  "\n".join(lines[start - 1:end]), max_chars))
        if end >= n:
            break
        start += step
    return chunks


def chunk_file(path: str, source: str, max_chars: int = 6000, window: int = 60,
               overlap: int = 20) -> tuple[list[Chunk], bool]:
    """Return (chunks, parse_ok). Chunks are sorted by chunk_id for determinism."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return window_chunks(path, source, max_chars, window, overlap), False

    lines = source.splitlines()
    n = max(len(lines), 1)
    spans: list[_Span] = []
    _collect(tree.body, "", False, spans)

    chunks: list[Chunk] = []
    seen: dict[str, int] = {}
    for sp in spans:
        if sp.kind == "class":
            text = _lines_excluding(lines, sp.start, sp.end, sp.child_spans)
        else:
            text = "\n".join(lines[sp.start - 1:sp.end])
        qual = sp.qualname
        seen[qual] = seen.get(qual, 0) + 1
        if seen[qual] > 1:  # e.g. @property getter + setter share a name
            qual = f"{qual}#{seen[qual]}"
        chunks.append(_make_chunk(path, qual, sp.kind, sp.start, sp.end, text, max_chars))

    top_level = [(s.start, s.end) for s in spans if "." not in s.qualname]
    module_text = _lines_excluding(lines, 1, n, top_level) if lines else ""
    chunks.append(_make_chunk(path, MODULE_QUALNAME, "module", 1, n, module_text, max_chars))
    chunks.sort(key=lambda c: c.chunk_id)
    return chunks, True


_KIND_PRIORITY = {"method": 0, "function": 0, "class": 1, "window": 2, "module": 3}


def innermost_chunk(chunks: list[Chunk], line: int) -> Chunk | None:
    """FR-L2: the innermost chunk containing `line` (method > function > class > module)."""
    containing = [c for c in chunks if c.start_line <= line <= c.end_line]
    if not containing:
        return None
    return min(containing,
               key=lambda c: (c.end_line - c.start_line, _KIND_PRIORITY[c.kind], c.chunk_id))
