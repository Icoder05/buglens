"""LLM reranking of the top-10 candidates — S7 (S5 → Gemini), S8 (S6 → Gemini). FR-M2.

Concept: an LLM reranker reads the issue and the actual code of the top
candidates and reorders them — "reasoning" a small learned ranker cannot do,
at the cost of tokens and latency (RQ3 compares accuracy per token). The
output is constrained JSON (`{"ranking": [chunk_id], "reason": str}`) via
`response_mime_type="application/json"` + a schema; ids not in the list are
discarded, a malformed answer is retried once, and if it still fails the input
order is kept (and logged) so every instance gets a result. Candidates the LLM
did not rank, and ranks 11–50, follow in their input order.
"""

from __future__ import annotations

import time

from buglens.chunking.corpus import load_corpus
from buglens.config import Config, set_seed, write_meta
from buglens.data.swebench import load_split
from buglens.eval.evaluate import load_run
from buglens.llm.client import LLMClient, QuotaExhausted, RequestCapReached
from buglens.retrieval.fusion import files_from_chunks
from buglens.retrieval.run import group_by_commit
from buglens.schemas import Candidate, Chunk, Instance, RankedResult
from buglens.utils import console, progress, summary, write_jsonl

SCHEMA = {
    "type": "object",
    "properties": {
        "ranking": {"type": "array", "items": {"type": "string"}},
        "reason": {"type": "string"},
    },
    "required": ["ranking", "reason"],
}
BASE_OF = {"S7": "S5", "S8": "S6"}


def _code_lines(chunk: Chunk, n_lines: int) -> str:
    body = chunk.text.split("\n", 2)[2] if chunk.text.count("\n") >= 2 else chunk.text
    lines = body.splitlines()[:n_lines]
    return "\n".join(f"{chunk.start_line + i:>5} | {ln}" for i, ln in enumerate(lines))


def build_prompt(inst: Instance, chunks: list[Chunk], cfg: Config, retry: bool = False) -> str:
    issue = inst.problem_statement[: cfg.llm.max_issue_chars]
    parts = [
        "You are helping localize a bug in a Python repository.",
        "Rank the candidate code locations by how likely they must be modified to fix the issue.",
        "Return JSON with `ranking` (candidate ids, most likely first) and a short `reason`.",
    ]
    if retry:
        parts.append("IMPORTANT: use ONLY the exact candidate ids listed below.")
    parts += ["", "## Issue", issue, "", "## Candidates"]
    for c in chunks:
        parts += [f"### id: {c.chunk_id}", f"path: {c.path}  qualname: {c.qualname}",
                  "```python", _code_lines(c, cfg.llm.rerank_lines), "```"]
    return "\n".join(parts)


def parse_ranking(data: dict | None, valid_ids: list[str]) -> list[str] | None:
    if not isinstance(data, dict) or not isinstance(data.get("ranking"), list):
        return None
    valid = set(valid_ids)
    out = []
    for cid in data["ranking"]:
        if isinstance(cid, str) and cid in valid and cid not in out:
            out.append(cid)
    return out or None


def llm_rerank(cfg: Config, system: str, split: str, limit: int | None = None
               ) -> list[RankedResult]:
    if system not in BASE_OF:
        raise ValueError("llm supports S7 and S8")
    set_seed(cfg.seed)
    base = {r.instance_id: r for r in load_run(cfg, BASE_OF[system], split)}
    instances = load_split(cfg, split)
    if limit:
        instances = instances[:limit]
    client = LLMClient(cfg)
    top = cfg.llm.rerank_top
    results: dict[str, RankedResult] = {}
    fallbacks = 0
    stopped = None
    with progress() as p:
        task = p.add_task(f"{system} {split}", total=len(instances))
        for (repo, commit), group in group_by_commit(instances):
            if stopped:
                break
            corpus = load_corpus(cfg, repo, commit)
            by_id = {c.chunk_id: c for c in corpus.chunks}
            for inst in group:
                prev = sorted(base[inst.instance_id].functions, key=lambda c: c.rank)
                head = prev[:top]
                t0 = time.perf_counter()
                tin = tout = 0
                ranking = None
                try:
                    for retry in (False, True):
                        prompt = build_prompt(inst, [by_id[c.chunk_id] for c in head], cfg, retry)
                        data, usage = client.generate_json(prompt, SCHEMA, inst.instance_id)
                        tin += usage.tokens_in
                        tout += usage.tokens_out
                        ranking = parse_ranking(data, [c.chunk_id for c in head])
                        if ranking:
                            break
                except (QuotaExhausted, RequestCapReached) as e:
                    stopped = str(e)
                    console.print(f"[red]stopping early: {e}[/red]")
                    break
                if not ranking:
                    fallbacks += 1
                    console.print(f"[yellow]{inst.instance_id}: invalid LLM output, "
                                  "keeping input order[/yellow]")
                    ranking = []
                order = ranking + [c.chunk_id for c in head if c.chunk_id not in ranking]
                order += [c.chunk_id for c in prev[top:]]
                old = {c.chunk_id: c for c in prev}
                cands = []
                for rank, cid in enumerate(order, start=1):
                    scores = dict(old[cid].scores)
                    if cid in ranking:
                        scores["llm"] = 1.0 / (ranking.index(cid) + 1)
                    cands.append(Candidate(chunk_id=cid, path=old[cid].path, scores=scores,
                                           rank=rank))
                results[inst.instance_id] = RankedResult(
                    instance_id=inst.instance_id, system=system, functions=cands,
                    files=files_from_chunks([c.path for c in cands]), tokens_in=tin,
                    tokens_out=tout,
                    seconds=base[inst.instance_id].seconds + time.perf_counter() - t0)
                p.advance(task)
    done = [results[i.instance_id] for i in instances if i.instance_id in results]
    out = cfg.path("runs") / f"{system}_{split}.jsonl"
    write_jsonl(out, done)
    write_meta(out.parent, cfg, filename=f"{system}_{split}.meta.json", system=system,
               split=split, model=cfg.llm.model, fallbacks=fallbacks, complete=not stopped,
               stopped_reason=stopped)
    console.print(client.report())
    summary("llm", system=system, split=split, done=f"{len(done)}/{len(instances)}",
            fallbacks=fallbacks, api_calls=client.requests, cache_hits=client.cache_hits)
    if stopped:
        console.print("[yellow]Partial run saved. Rerun the same command later: cached "
                      "answers are reused, so it resumes where it stopped.[/yellow]")
    return done
