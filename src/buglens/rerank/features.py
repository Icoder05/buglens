"""Per-candidate features for learning to rank — FR-K1.

Concept: a reranker re-scores a short candidate list (S5's top 50) using
signals a single retriever cannot combine on its own:
- retrieval evidence: each retriever's score and rank (BM25, off-the-shelf
  dense, fine-tuned dense, RRF);
- explicit mentions: does the issue name the file, the qualified name, the
  bare function name, or show it in a traceback frame?
- structure: chunk size, file size in chunks, chunk kind, directory depth, and
  how central the file is in the import graph (PageRank x #modules, so 1.0
  means "average module" in any repo size);
- S6b only: cosine similarity between the issue and the onboarding summary of
  the candidate's package (RQ4: do human-oriented summaries help machines?).
Features never look at the gold patch; labels are attached separately.
"""

from __future__ import annotations

import re

import numpy as np

from buglens.chunking.corpus import Corpus
from buglens.schemas import Candidate, Instance

KINDS = ["function", "method", "class", "module", "window"]
_TRACE = re.compile(r'File "([^"]+)", line (\d+), in ([\w<>]+)')

BASE_FEATURES = [
    "bm25", "bm25_rank", "dense", "dense_rank", "dense_ft", "dense_ft_rank", "rrf", "rrf_rank",
    "path_in_issue", "qualname_in_issue", "name_in_issue", "in_traceback",
    "chunk_len_lines", "file_num_chunks", *[f"kind_{k}" for k in KINDS],
    "import_pagerank", "dir_depth",
]
S6B_FEATURES = [*BASE_FEATURES, "pkg_summary_sim"]


def _clean_qualname(q: str) -> str:
    return q.split("#")[0]


def traceback_frames(issue: str) -> list[tuple[str, str]]:
    return [(p.replace("\\", "/"), fn) for p, _, fn in _TRACE.findall(issue)]


def mention_features(issue: str, path: str, qualname: str,
                     frames: list[tuple[str, str]]) -> dict[str, float]:
    q = _clean_qualname(qualname)
    name = q.split(".")[-1]
    module = path[:-3].replace("/", ".") if path.endswith(".py") else path
    base = path.split("/")[-1]
    if path in issue or module in issue:
        pin = 1.0
    elif re.search(rf"(?<![\w/]){re.escape(base)}\b", issue):
        pin = 0.5
    else:
        pin = 0.0
    qin = 1.0 if ("." in q and q in issue) else 0.0
    is_window = re.fullmatch(r"L\d+-\d+", name) is not None
    nin = 0.0
    if name != "<module>" and not is_window and len(name) >= 3:
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", issue):
            nin = 1.0
    tb = 0.0
    for fpath, fn in frames:
        if fpath.endswith("/" + path) or fpath == path:
            tb = max(tb, 1.0 if fn == name else 0.5)
    return {"path_in_issue": pin, "qualname_in_issue": qin, "name_in_issue": nin,
            "in_traceback": tb}


def candidate_features(inst: Instance, corpus: Corpus, cands: list[Candidate],
                       comp_scores: dict[str, np.ndarray], pagerank: dict[str, float],
                       pkg_sim: dict[str, float] | None = None,
                       pkg_of_path: dict[str, str] | None = None) -> list[dict[str, float]]:
    """Feature dict per candidate (same order as `cands`)."""
    from buglens.retrieval.fusion import ranks_from_scores

    index = {cid: i for i, cid in enumerate(corpus.ids)}
    ranks = {k: ranks_from_scores(v) for k, v in comp_scores.items()}
    chunks_per_file: dict[str, int] = {}
    for c in corpus.chunks:
        chunks_per_file[c.path] = chunks_per_file.get(c.path, 0) + 1
    n_modules = max(len(pagerank), 1)
    issue = inst.problem_statement
    frames = traceback_frames(issue)
    rows = []
    for cand in cands:
        i = index[cand.chunk_id]
        ch = corpus.chunks[i]
        row: dict[str, float] = {}
        for k in ("bm25", "dense", "dense_ft"):
            if k in comp_scores:
                row[k] = float(comp_scores[k][i])
                row[f"{k}_rank"] = float(ranks[k][i])
            else:
                row[k] = np.nan
                row[f"{k}_rank"] = np.nan
        row["rrf"] = cand.scores.get("rrf", np.nan)
        row["rrf_rank"] = float(cand.rank)
        row.update(mention_features(issue, ch.path, ch.qualname, frames))
        row["chunk_len_lines"] = float(ch.end_line - ch.start_line + 1)
        row["file_num_chunks"] = float(chunks_per_file.get(ch.path, 1))
        for k in KINDS:
            row[f"kind_{k}"] = 1.0 if ch.kind == k else 0.0
        row["import_pagerank"] = pagerank.get(ch.path, 0.0) * n_modules
        row["dir_depth"] = float(ch.path.count("/"))
        if pkg_sim is not None and pkg_of_path is not None:
            row["pkg_summary_sim"] = pkg_sim.get(pkg_of_path.get(ch.path, ""), np.nan)
        rows.append(row)
    return rows
