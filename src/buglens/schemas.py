"""Typed records passed between pipeline stages (PRD Section 6).

Concept: a research pipeline is a chain of transformations (instance -> chunks ->
candidates -> ranked result -> metrics). Giving each hand-off a pydantic schema
means every stage validates its input, so a bug in one stage fails loudly at the
boundary instead of silently corrupting a metric three steps later. The schemas
also double as the on-disk format: runs/*.jsonl are just `RankedResult` objects
serialized one per line, so any number in the report can be traced back to them.
"""

from typing import Literal

from pydantic import BaseModel


class Instance(BaseModel):
    instance_id: str
    repo: str  # "django/django"
    base_commit: str
    problem_statement: str
    hints_text: str = ""  # only in ablation A1
    patch: str  # gold patch; NEVER passed to retrieval, features or prompts
    split: Literal["test", "dev", "train"]


class GoldLabels(BaseModel):
    instance_id: str
    files: list[str]
    functions: list[str]  # chunk ids "path::qualname"


class Chunk(BaseModel):
    chunk_id: str  # "<path>::<qualname>" | "<path>::<module>" | "<path>::L<s>-<e>"
    path: str
    qualname: str
    kind: Literal["function", "method", "class", "module", "window"]
    start_line: int  # 1-based inclusive
    end_line: int
    text: str
    text_sha1: str


class Candidate(BaseModel):
    chunk_id: str
    path: str
    scores: dict[str, float]  # bm25, dense, dense_ft, rrf, ltr, llm
    rank: int


class RankedResult(BaseModel):
    instance_id: str
    system: str
    functions: list[Candidate]
    files: list[str]
    tokens_in: int = 0
    tokens_out: int = 0
    seconds: float


# ---- Onboard ----
class FileFacts(BaseModel):
    path: str
    module: str  # dotted module name
    imports: list[str]  # resolved dotted module names inside the repo only
    classes: list[dict]  # {name, bases, start_line, end_line, methods: [..], docstring}
    functions: list[dict]  # {name, start_line, end_line, signature, docstring}
    calls: list[dict]  # {caller_qualname, callee_name, line, resolved: str | None}
    is_entry_point: bool
    parse_ok: bool


class Citation(BaseModel):
    path: str
    line: int


class Sentence(BaseModel):
    text: str
    citations: list[Citation]
    valid: bool  # set by validator


class PackageSummary(BaseModel):
    repo: str
    commit: str
    package: str  # e.g. "django/db"
    sentences: list[Sentence]
    tokens_in: int
    tokens_out: int


class OnboardingBundle(BaseModel):
    repo: str
    commit: str
    block_svg: str  # path
    block_mermaid: str  # path
    package_diagrams: dict[str, str]
    class_diagrams: dict[str, str]
    callflow_diagrams: dict[str, str]
    guide_md: str  # path
    stats: dict  # node/edge counts, dropped sentences, parse failures
