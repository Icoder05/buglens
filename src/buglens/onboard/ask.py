""""Ask the codebase": retrieval-augmented, citation-checked Q&A — FR-Q1..Q4.

Concept: RAG (retrieval-augmented generation). The same hybrid retriever used
for bug localization (BM25 + fine-tuned dense, fused with RRF = system S5)
finds the 8 chunks most relevant to a question like "where are blueprints
registered?". The LLM may answer only from those chunks, citing `path:line`,
and the validator (strict mode) keeps only citations inside the retrieved
chunks. Without an API key the retrieved chunks themselves are the answer.
A radius-1 import-neighbourhood diagram shows where the top hit sits.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from buglens.analysis.repo_analysis import analyze_commit
from buglens.chunking.corpus import Corpus, load_corpus
from buglens.config import PROJECT_ROOT, Config
from buglens.onboard.diagrams import neighbourhood_diagram, render_svg, to_mermaid, verify_diagram
from buglens.onboard.guide import permalink
from buglens.onboard.summarize import SENTENCES_SCHEMA, onboarding_commit
from buglens.onboard.validate import validate_sentences
from buglens.retrieval.bm25 import bm25_scores
from buglens.retrieval.dense import faiss_scores
from buglens.retrieval.fusion import order_by_score, rrf
from buglens.schemas import Chunk

_ENCODERS: dict[str, object] = {}


def get_encoder(cfg: Config, device: str | None = None):
    """Fine-tuned encoder if present (S5 configuration), else the off-the-shelf model."""
    from buglens.retrieval.dense import DenseEncoder

    r = cfg.retrieval
    ft = PROJECT_ROOT / r.finetuned_model
    model_id = str(ft) if ft.exists() else (r.dense_model_fallback if r.use_fallback_model
                                            else r.dense_model)
    key = f"{model_id}@{device}"
    if key not in _ENCODERS:
        _ENCODERS[key] = DenseEncoder(cfg, model_id, device=device)
    return _ENCODERS[key]


def hybrid_scores(cfg: Config, corpus: Corpus, query: str, encoder) -> dict[str, np.ndarray]:
    out = {"bm25": bm25_scores(cfg, corpus, query)}
    if encoder is not None:
        out["dense"] = faiss_scores(encoder.corpus_matrix(corpus),
                                    encoder.encode_queries([query])[0])
    return out


def hybrid_search(cfg: Config, corpus: Corpus, query: str, k: int, encoder) -> list[Chunk]:
    scores = hybrid_scores(cfg, corpus, query, encoder)
    ids = corpus.ids
    top_n = cfg.retrieval.top_n
    lists = [[ids[i] for i in order_by_score(s)[:top_n]] for s in scores.values()]
    fused = rrf(lists, cfg.retrieval.rrf_k) if len(lists) > 1 else [(c, 0.0) for c in lists[0]]
    by_id = {c.chunk_id: c for c in corpus.chunks}
    return [by_id[cid] for cid, _ in fused[:k]]


def _numbered(c: Chunk, max_lines: int = 80) -> str:
    body = c.text.split("\n", 2)[2] if c.text.count("\n") >= 2 else c.text
    rows = body.splitlines()[:max_lines]
    return "\n".join(f"{c.start_line + i:>5} | {ln}" for i, ln in enumerate(rows))


@dataclass
class Answer:
    question: str
    repo: str
    commit: str
    chunks: list[Chunk]
    sentences: list[dict] = field(default_factory=list)
    neighbourhood_svg: str = ""
    neighbourhood_mermaid: str = ""
    used_llm: bool = False
    note: str = ""

    def markdown(self) -> str:
        md = [f"**Q:** {self.question}", ""]
        if self.sentences:
            for s in self.sentences:
                links = " ".join(
                    f"[`{c['path']}:{c['line']}`]"
                    f"({permalink(self.repo, self.commit, c['path'], c['line'])})"
                    for c in s["citations"])
                md.append(f"- {s['text']} {links}")
        else:
            md.append(f"_{self.note or 'No generated answer.'}_ Top retrieved locations:")
        md += ["", "**Retrieved chunks:**"]
        for i, c in enumerate(self.chunks, start=1):
            md.append(f"{i}. [`{c.path}:{c.start_line}`]"
                      f"({permalink(self.repo, self.commit, c.path, c.start_line)}) `{c.qualname}`")
        return "\n".join(md)


def ask(cfg: Config, repo: str, question: str, use_llm: bool = True, encoder=None,
        client=None) -> Answer:
    commit = onboarding_commit(cfg, repo)
    corpus = load_corpus(cfg, repo, commit)
    if encoder is None:
        encoder = get_encoder(cfg)
    chunks = hybrid_search(cfg, corpus, question, cfg.onboard.ask_top_k, encoder)
    ans = Answer(question, repo, commit, chunks)

    a = analyze_commit(cfg, repo, commit)
    path_to_module = {p: m for m, p in a.graphs.module_path.items()}
    top_module = path_to_module.get(chunks[0].path) if chunks else None
    if top_module:
        spec = neighbourhood_diagram(a.graphs, top_module, label_chars=cfg.diagrams.max_label_chars)
        if verify_diagram(spec, a.graphs)["ok"]:
            ans.neighbourhood_svg = render_svg(spec)
            ans.neighbourhood_mermaid = to_mermaid(spec)

    from buglens.llm.client import LLMClient, load_api_key

    if not use_llm or (client is None and not load_api_key()):
        ans.note = "No GEMINI_API_KEY: showing retrieval results only."
        return ans
    client = client or LLMClient(cfg)
    prompt = "\n".join([
        f"Answer the question about the Python repository {repo} in at most 5 sentences, "
        "using ONLY the code chunks below. Every sentence must cite `path` and `line` of the "
        "chunk line that supports it. If the chunks do not answer it, say so and cite the "
        "closest chunk.", "", f"## Question\n{question}", "", "## Code chunks"] + [
        f"### {c.path} ({c.qualname}, lines {c.start_line}-{c.end_line})\n```python\n"
        f"{_numbered(c)}\n```" for c in chunks])
    data, _ = client.generate_json(prompt, SENTENCES_SCHEMA)
    raw = (data or {}).get("sentences", []) if isinstance(data, dict) else []
    spans: dict[str, list[tuple[int, int]]] = {}
    for c in chunks:
        spans.setdefault(c.path, []).append((c.start_line, c.end_line))
    kept, _ = validate_sentences(raw[:5], corpus.file_lines, spans, strict=True)
    ans.sentences = [s.model_dump() for s in kept]
    ans.used_llm = True
    if not kept:
        ans.note = "The model's answer had no valid citations and was discarded."
    return ans
