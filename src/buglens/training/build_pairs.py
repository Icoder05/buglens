"""Build contrastive training triples (anchor, positive, negative) — FR-T1, FR-T2.

Concept: contrastive fine-tuning teaches an encoder "this issue belongs with
this code". Each example is a triple:
- anchor   = the issue text (with the model's query prefix),
- positive = a function the gold patch modifies,
- negative = a *hard* negative: the highest-ranked BM25 chunk that is NOT gold.
Hard negatives look relevant on the surface (shared words) but are wrong, which
forces the model to learn more than word overlap. All other positives in the
batch also act as negatives (in-batch negatives). Pairs come only from
SWE-bench *train* repositories, disjoint from the test repos (leakage guard),
and the validation split is by repository, so validation measures transfer to
unseen codebases — the same situation as the test set.
"""

from __future__ import annotations

import json
import os
import random
import urllib.request
from collections import defaultdict

import bm25s
import numpy as np
import pandas as pd

from buglens.chunking.corpus import load_corpus
from buglens.config import Config, set_seed
from buglens.data.labels import label_instance, original_lines
from buglens.data.repos import ensure_clone, read_files
from buglens.data.swebench import assert_no_leakage, load_split, repos_of
from buglens.retrieval.fusion import order_by_score
from buglens.retrieval.tokenize_code import tokenize
from buglens.utils import console, progress, summary


def repo_size_mb(cfg: Config, repo: str) -> float:
    """GitHub-reported repository size (MB), cached. Follows renames (HTTP redirects)."""
    cache_file = cfg.path("cache") / "repo_sizes.json"
    sizes = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    if repo not in sizes:
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}",
                                     headers={"User-Agent": "buglens"})
        if os.environ.get("GITHUB_TOKEN"):
            req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            sizes[repo] = json.load(resp)["size"] / 1024
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(sizes, indent=1, sort_keys=True))
    return sizes[repo]


def eligible_repos(cfg: Config, repos: list[str]) -> list[str]:
    limit = cfg.training.max_repo_clone_mb
    ok = []
    for r in repos:
        size = repo_size_mb(cfg, r)
        console.print(f"  {r}: {size:.0f} MB {'ok' if size < limit else 'skip'}")
        if size < limit:
            ok.append(r)
    return ok


def _bm25_order(token_lists: list[list[str]], query: str) -> np.ndarray:
    retriever = bm25s.BM25()
    retriever.index(token_lists, show_progress=False)
    q = tokenize(query)
    scores = (np.asarray(retriever.get_scores(q), dtype=np.float32) if q
              else np.zeros(len(token_lists), dtype=np.float32))
    return order_by_score(scores)


def build_pairs(cfg: Config) -> pd.DataFrame:
    set_seed(cfg.seed)
    t = cfg.training
    train = load_split(cfg, "train")
    test_repos = set(repos_of(load_split(cfg, "test")))
    dev_repos = set(repos_of(load_split(cfg, "dev")))
    assert_no_leakage(set(repos_of(train)), test_repos | dev_repos)

    console.print("checking repository sizes (FR-T1: clone < "
                  f"{t.max_repo_clone_mb} MB)")
    repos = eligible_repos(cfg, repos_of(train))
    rng = random.Random(cfg.seed)
    by_repo: dict[str, list] = defaultdict(list)
    for inst in train:
        if inst.repo in repos:
            by_repo[inst.repo].append(inst)
    # Round-robin over repos so no single repo dominates the sample.
    for lst in by_repo.values():
        rng.shuffle(lst)
    order = []
    taken: dict[str, int] = defaultdict(int)
    cap = t.max_pairs_per_repo
    while any(by_repo.values()):
        for r in sorted(by_repo):
            if by_repo[r] and taken[r] < cap:
                order.append(by_repo[r].pop())
                taken[r] += 1
            else:
                by_repo[r] = []
    # Oversample to survive skips, then process grouped by repo for cache locality.
    candidates = sorted(order[: int(t.max_pairs * 1.3)], key=lambda i: (i.repo, i.base_commit))

    rows = []
    skipped = defaultdict(int)
    with progress() as p:
        task = p.add_task("pairs", total=len(candidates))
        token_cache: dict[str, list[str]] = {}
        current_repo = None
        for inst in candidates:
            p.advance(task)
            if inst.repo != current_repo:
                ensure_clone(cfg, inst.repo)
                token_cache.clear()
                current_repo = inst.repo
            try:
                sources = read_files(cfg, inst.repo, inst.base_commit,
                                     list(original_lines(inst.patch)))
                labels, _ = label_instance(inst, sources, cfg.chunking.max_chars,
                                           cfg.chunking.window_lines, cfg.chunking.window_overlap)
                corpus = load_corpus(cfg, inst.repo, inst.base_commit)
            except Exception as e:  # noqa: BLE001 - unreachable commit, bad blob, etc.
                skipped[f"error:{type(e).__name__}"] += 1
                continue
            gold = set(labels.functions)
            id_to_chunk = {c.chunk_id: c for c in corpus.chunks}
            positives = [id_to_chunk[g] for g in labels.functions if g in id_to_chunk]
            positives.sort(key=lambda c: c.kind not in ("function", "method"))
            if not positives:
                skipped["no_gold_in_corpus"] += 1
                continue
            token_lists = []
            for c in corpus.chunks:
                if c.text_sha1 not in token_cache:
                    token_cache[c.text_sha1] = tokenize(c.text)
                token_lists.append(token_cache[c.text_sha1])
            order_idx = _bm25_order(token_lists, inst.problem_statement)
            negative = next((corpus.chunks[i] for i in order_idx
                             if corpus.chunks[i].chunk_id not in gold), None)
            if negative is None:
                skipped["no_negative"] += 1
                continue
            rows.append({
                "anchor": cfg.retrieval.query_prefix + inst.problem_statement,
                "positive": positives[0].text,
                "negative": negative.text,
                "repo": inst.repo,
                "instance_id": inst.instance_id,
            })
            if len(rows) >= t.max_pairs:
                break

    df = pd.DataFrame(rows)
    df = _split_by_repo(df, t.val_fraction, cfg.seed)
    out = cfg.path("pairs")
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "pairs.parquet", index=False)
    df[df.split == "train"].drop(columns="split").to_parquet(out / "train.parquet", index=False)
    df[df.split == "val"].drop(columns="split").to_parquet(out / "val.parquet", index=False)
    train_r = set(df[df.split == "train"].repo)
    val_r = set(df[df.split == "val"].repo)
    assert not (train_r & val_r), "validation split must be repository-disjoint"
    console.print(f"skipped: {dict(skipped)}")
    console.print(f"val repos: {sorted(val_r)}")
    summary("pairs", pairs=len(df), train=int((df.split == "train").sum()),
            val=int((df.split == "val").sum()), repos=df.repo.nunique(), out=str(out))
    return df


def _split_by_repo(df: pd.DataFrame, val_fraction: float, seed: int) -> pd.DataFrame:
    """FR-T2: whole repositories go to validation until it holds >= val_fraction of pairs."""
    counts = df.repo.value_counts()
    repos = sorted(counts.index)
    random.Random(seed).shuffle(repos)
    target = val_fraction * len(df)
    val, n = set(), 0
    for r in repos:
        if n >= target:
            break
        if n + counts[r] <= 2 * target:  # avoid one giant repo swallowing validation
            val.add(r)
            n += counts[r]
    df = df.copy()
    df["split"] = np.where(df.repo.isin(val), "val", "train")
    return df
