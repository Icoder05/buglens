"""Citation validator for LLM-written sentences — FR-S3.

Concept: grounding. An LLM summary is only trustworthy if each claim points at
code that exists and that the model was actually shown. A citation
`path:line` is valid when (1) the file exists at the commit, (2) the line is
within the file, and (3) in strict mode, the line falls inside one of the
symbols listed in the prompt. Invalid citations are removed; a sentence left
with no valid citation is dropped entirely, and drop rates are reported. This
turns "the model might hallucinate" into a measured, enforced property.
"""

from __future__ import annotations

from buglens.schemas import Citation, Sentence

Spans = dict[str, list[tuple[int, int]]]


def citation_valid(path: str, line: int, file_lines: dict[str, int],
                   allowed: Spans | None, strict: bool = True) -> bool:
    if not isinstance(path, str) or not isinstance(line, int) or isinstance(line, bool):
        return False
    if path not in file_lines or not (1 <= line <= file_lines[path]):
        return False
    if strict:
        return any(s <= line <= e for s, e in (allowed or {}).get(path, []))
    return True


def validate_sentences(raw: list, file_lines: dict[str, int], allowed: Spans | None = None,
                       strict: bool = True) -> tuple[list[Sentence], dict]:
    """Keep sentences with >= 1 valid citation (only valid citations are kept)."""
    kept: list[Sentence] = []
    dropped: list[str] = []
    n_cit = n_valid = 0
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            dropped.append(str(item)[:200])
            continue
        valid = []
        for c in item.get("citations") or []:
            n_cit += 1
            if not isinstance(c, dict):
                continue
            path, line = c.get("path"), c.get("line")
            if isinstance(line, str) and line.isdigit():
                line = int(line)
            if citation_valid(path, line, file_lines, allowed, strict):
                cit = Citation(path=path, line=line)
                if cit not in valid:
                    valid.append(cit)
                n_valid += 1
        if valid:
            kept.append(Sentence(text=item["text"].strip(), citations=valid, valid=True))
        else:
            dropped.append(item["text"].strip())
    stats = {"sentences": len(kept) + len(dropped), "kept": len(kept), "dropped": len(dropped),
             "citations": n_cit, "valid_citations": n_valid, "dropped_texts": dropped}
    return kept, stats
