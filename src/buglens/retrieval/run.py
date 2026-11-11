"""Run first-stage retrieval systems S1–S5 (and ablation A1) over a split.

Concept: every retriever produces one score per chunk of the instance's
(repo, commit) corpus. We cache those full score vectors per instance, so
systems that *combine* retrievers (RRF in S3/S5, LambdaRank features in S6)
reuse them instead of re-encoding. A system's output is its top-N candidate
chunks, each carrying every component score and rank, written as one
`RankedResult` per line to `runs/<system>_<split>.jsonl`.
"""

from __future__ import annotations

import time
from itertools import groupby
from pathlib import Path

import numpy as np

from buglens.chunking.corpus import Corpus, load_corpus
from buglens.config import PROJECT_ROOT, Config, set_seed, write_meta
from buglens.data.swebench import load_split
from buglens.retrieval.bm25 import bm25_scores
from buglens.retrieval.fusion import files_from_chunks, order_by_score, ranks_from_scores, rrf
from buglens.schemas import Candidate, Instance, RankedResult
from buglens.utils import console, progress, summary, write_jsonl

# system -> (retrievers combined, use hints in query)
SYSTEMS: dict[str, tuple[list[str], bool]] = {
    "S1": (["bm25"], False),
    "S2": (["dense"], False),
    "S3": (["bm25", "dense"], False),
    "S4": (["dense_ft"], False),
    "S5": (["bm25", "dense_ft"], False),
    "A1": (["bm25", "dense_ft"], True),
}


def query_text(inst: Instance, with_hints: bool = False) -> str:
    q = inst.problem_statement
    if with_hints and inst.hints_text:
        q += "\n" + inst.hints_text
    return q


def dense_model_id(cfg: Config, retriever: str) -> str:
    r = cfg.retrieval
    if retriever == "dense":
        return r.dense_model_fallback if r.use_fallback_model else r.dense_model
    path = PROJECT_ROOT / r.finetuned_model
    if not path.exists():
        raise FileNotFoundError(f"Fine-tuned model not found at {path}; run `buglens finetune`.")
    return str(path)


class ScoreProvider:
    """Computes (and caches on disk) full per-chunk score vectors for one retriever."""

    def __init__(self, cfg: Config, retriever: str, with_hints: bool = False):
        self.cfg = cfg
        self.retriever = retriever
        self.with_hints = with_hints
        self.encoder = None
        tag = retriever + ("_hints" if with_hints else "")
        if retriever != "bm25":
            from buglens.retrieval.dense import model_key

            mk = model_key(dense_model_id(cfg, retriever)).replace("/", "_").replace(":", "_")
            tag += "__" + mk
        self.dir = cfg.path("cache") / "scores" / tag
        self.dir.mkdir(parents=True, exist_ok=True)

    def _encoder(self):
        if self.encoder is None:
            from buglens.retrieval.dense import DenseEncoder

            self.encoder = DenseEncoder(self.cfg, dense_model_id(self.cfg, self.retriever))
        return self.encoder

    def scores(self, inst: Instance, corpus: Corpus) -> np.ndarray:
        path = self.dir / f"{inst.instance_id}.npy"
        if path.exists():
            s = np.load(path)
            if len(s) == len(corpus.chunks):
                return s
        q = query_text(inst, self.with_hints)
        if self.retriever == "bm25":
            s = bm25_scores(self.cfg, corpus, q)
        else:
            from buglens.retrieval.dense import faiss_scores

            enc = self._encoder()
            s = faiss_scores(enc.corpus_matrix(corpus), enc.encode_queries([q])[0])
        np.save(path, s.astype(np.float32))
        return s


def build_candidates(corpus: Corpus, comp_scores: dict[str, np.ndarray], top_n: int,
                     rrf_k: int) -> list[Candidate]:
    """Top-N candidates from one retriever, or RRF over several retrievers' top-N."""
    ranks = {name: ranks_from_scores(s) for name, s in comp_scores.items()}
    ids = corpus.ids
    if len(comp_scores) == 1:
        (name, s), = comp_scores.items()
        order = order_by_score(s)[:top_n]
        fused = [(ids[i], float(s[i])) for i in order]
    else:
        lists = [[ids[i] for i in order_by_score(s)[:top_n]] for s in comp_scores.values()]
        fused = rrf(lists, k=rrf_k)[:top_n]
    index = {cid: i for i, cid in enumerate(ids)}
    out = []
    for rank, (cid, fscore) in enumerate(fused, start=1):
        i = index[cid]
        sc: dict[str, float] = {}
        for name in comp_scores:
            sc[name] = float(comp_scores[name][i])
            sc[f"{name}_rank"] = float(ranks[name][i])
        if len(comp_scores) > 1:
            sc["rrf"] = fscore
        out.append(Candidate(chunk_id=cid, path=corpus.chunks[i].path, scores=sc, rank=rank))
    return out


def group_by_commit(instances: list[Instance]) -> list[tuple[tuple[str, str], list[Instance]]]:
    key = lambda i: (i.repo, i.base_commit)  # noqa: E731
    return [(k, list(g)) for k, g in groupby(sorted(instances, key=key), key=key)]


def run_path(cfg: Config, system: str, split: str) -> Path:
    return cfg.path("runs") / f"{system}_{split}.jsonl"


def run_retrieval(cfg: Config, system: str, split: str) -> list[RankedResult]:
    if system not in SYSTEMS:
        raise ValueError(f"retrieve supports {sorted(SYSTEMS)}, got {system}")
    set_seed(cfg.seed)
    retrievers, hints = SYSTEMS[system]
    providers = {r: ScoreProvider(cfg, r, hints) for r in retrievers}
    instances = load_split(cfg, split)
    results: dict[str, RankedResult] = {}
    with progress() as p:
        task = p.add_task(f"{system} {split}", total=len(instances))
        for (repo, commit), group in group_by_commit(instances):
            corpus = load_corpus(cfg, repo, commit)
            for inst in group:
                t0 = time.perf_counter()
                comp = {r: prov.scores(inst, corpus) for r, prov in providers.items()}
                cands = build_candidates(corpus, comp, cfg.retrieval.top_n, cfg.retrieval.rrf_k)
                results[inst.instance_id] = RankedResult(
                    instance_id=inst.instance_id, system=system, functions=cands,
                    files=files_from_chunks([c.path for c in cands]),
                    seconds=time.perf_counter() - t0)
                p.advance(task)
    ordered = [results[i.instance_id] for i in instances]
    out = run_path(cfg, system, split)
    write_jsonl(out, ordered)
    write_meta(out.parent, cfg, filename=f"{system}_{split}.meta.json", system=system,
               split=split)
    for prov in providers.values():
        if prov.encoder is not None:
            from buglens.retrieval.dense import report_cache

            report_cache(prov.encoder)
    summary("retrieve", system=system, split=split, instances=len(ordered), out=str(out))
    console.print()
    return ordered
