"""Collect every number used in the research report into tidy CSV files.

Run:  uv run python scripts/research/collect.py
Out:  reports/research/data/*.csv + manifest.json
All new experiments here reuse cached scores/features; they make no LLM calls.
"""

from __future__ import annotations

import json
import platform
import re
import subprocess
import time
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from buglens.chunking.corpus import load_corpus
from buglens.config import PROJECT_ROOT, git_commit_hash, load_config
from buglens.data.prepare import load_labels
from buglens.data.swebench import load_split
from buglens.eval.evaluate import eval_system
from buglens.eval.metrics import METRICS, instance_metrics
from buglens.retrieval.fusion import files_from_chunks
from buglens.retrieval.run import ScoreProvider, build_candidates, group_by_commit
from buglens.schemas import RankedResult

OUT = PROJECT_ROOT / "reports" / "research" / "data"
CFG = load_config()
TEST_SYSTEMS = ["S1", "S2", "S3", "S4", "S5", "S6", "S6b", "S7", "S8", "A1"]
DEV_SYSTEMS = ["S1", "S2", "S3", "S4", "S5", "S6", "A1"]


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


# ------------------------------------------------------------------ 1. per-instance metrics
def per_instance() -> pd.DataFrame:
    rows = []
    for split, systems in (("test", TEST_SYSTEMS), ("dev", DEV_SYSTEMS)):
        repo = {i.instance_id: i.repo for i in load_split(CFG, split)}
        for s in systems:
            if not (CFG.path("runs") / f"{s}_{split}.jsonl").exists():
                continue
            df = eval_system(CFG, s, split, quiet=True).reset_index()
            df.insert(0, "split", split)
            df.insert(0, "system", s)
            df["repo"] = df.instance_id.map(repo)
            rows.append(df)
    out = pd.concat(rows, ignore_index=True)
    out.to_csv(OUT / "per_instance_metrics.csv", index=False)
    log(f"per_instance_metrics: {len(out)} rows")
    return out


# ------------------------------------------------------------------ 2. LTR seed iterations
def ltr_seeds(seeds=(1, 2, 3, 4, 5)) -> None:
    from lightgbm import LGBMRanker

    from buglens.rerank.features import BASE_FEATURES

    feats = pd.read_parquet(CFG.path("cache") / "ltr" / "S6_test.parquet")
    labels = load_labels(CFG, "test")
    k = CFG.rerank
    rows = []
    for seed in seeds:
        t0 = time.perf_counter()
        df = feats.copy()
        df["ltr"] = np.nan
        for repo in sorted(df.repo.unique()):
            train = df[df.repo != repo]
            has = train.groupby("instance_id")["label"].transform("max") > 0
            train = train[has].sort_values(["instance_id", "s5_rank"])
            sizes = train.groupby("instance_id", sort=False).size().to_numpy()
            m = LGBMRanker(objective="lambdarank", n_estimators=k.n_estimators,
                           learning_rate=k.learning_rate, num_leaves=k.num_leaves,
                           min_child_samples=k.min_child_samples, random_state=seed,
                           subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)
            m.fit(train[BASE_FEATURES], train["label"], group=sizes)
            mask = df.repo == repo
            df.loc[mask, "ltr"] = m.predict(df.loc[mask, BASE_FEATURES])
        mets = []
        for iid, g in df.groupby("instance_id"):
            g = g.sort_values(["ltr", "s5_rank"], ascending=[False, True])
            ids = list(g.chunk_id)
            res = RankedResult(instance_id=iid, system="S6", seconds=0,
                               functions=[{"chunk_id": c, "path": p, "scores": {}, "rank": i + 1}
                                          for i, (c, p) in enumerate(zip(ids, g.path, strict=True))],
                               files=files_from_chunks(list(g.path)))
            mets.append(instance_metrics(res, labels[iid]))
        m = pd.DataFrame(mets).mean()
        rows.append({"seed": seed, **{c: round(m[c], 4) for c in METRICS},
                     "seconds": round(time.perf_counter() - t0, 1)})
        log(f"ltr seed {seed}: func_acc@10={m['func_acc@10']:.3f}")
    pd.DataFrame(rows).to_csv(OUT / "ltr_seed_iterations.csv", index=False)


# ------------------------------------------------------------------ 3+4. RRF k, candidate depth
def fusion_sensitivity(ks=(1, 10, 30, 60, 100, 300), depths=(5, 10, 20, 50, 100, 200)) -> None:
    labels = load_labels(CFG, "test")
    insts = load_split(CFG, "test")
    prov = {r: ScoreProvider(CFG, r) for r in ("bm25", "dense_ft")}
    per_k = {k: [] for k in ks}
    depth_rows = []
    for (repo, commit), group in group_by_commit(insts):
        corpus = load_corpus(CFG, repo, commit)
        for inst in group:
            comp = {r: p.scores(inst, corpus) for r, p in prov.items()}
            for k in ks:
                c = build_candidates(corpus, comp, 50, k)
                res = RankedResult(instance_id=inst.instance_id, system="S5", functions=c,
                                   files=files_from_chunks([x.path for x in c]), seconds=0)
                per_k[k].append(instance_metrics(res, labels[inst.instance_id]))
            c = build_candidates(corpus, comp, max(depths), 60)
            ids = [x.chunk_id for x in c]
            files = files_from_chunks([x.path for x in c])
            gold = labels[inst.instance_id]
            for d in depths:
                depth_rows.append({"instance_id": inst.instance_id, "depth": d,
                                   "gold_function_in_top": int(bool(set(ids[:d]) & set(gold.functions))),
                                   "gold_file_in_top_files": int(bool(set(files[:d]) & set(gold.files)))})
    rows = [{"rrf_k": k, **{m: round(pd.DataFrame(v)[m].mean(), 4) for m in METRICS}}
            for k, v in per_k.items()]
    pd.DataFrame(rows).to_csv(OUT / "rrf_k_sensitivity.csv", index=False)
    dd = pd.DataFrame(depth_rows)
    dd.groupby("depth")[["gold_function_in_top", "gold_file_in_top_files"]].mean().round(4) \
      .reset_index().to_csv(OUT / "candidate_depth.csv", index=False)
    log("rrf k sensitivity + candidate depth written")


# ------------------------------------------------------------------ 5. repeated latency
def latency_repeats(n=50, repeats=3) -> None:
    import random

    from buglens.retrieval.bm25 import load_or_build
    from buglens.retrieval.dense import DenseEncoder, faiss_scores
    from buglens.retrieval.run import dense_model_id
    from buglens.retrieval.tokenize_code import tokenize

    insts = random.Random(7).sample(load_split(CFG, "test"), n)
    enc = DenseEncoder(CFG, dense_model_id(CFG, "dense_ft"))
    enc.encode_queries(["warm up"])
    rows = []
    for inst in insts:
        corpus = load_corpus(CFG, inst.repo, inst.base_commit)
        bm = load_or_build(CFG, corpus)
        mat = enc.corpus_matrix(corpus)
        for r in range(repeats):
            t = time.perf_counter()
            bm.get_scores(tokenize(inst.problem_statement))
            t_bm = time.perf_counter() - t
            t = time.perf_counter()
            q = enc.encode_queries([inst.problem_statement])[0]
            t_enc = time.perf_counter() - t
            t = time.perf_counter()
            faiss_scores(mat, q)
            t_faiss = time.perf_counter() - t
            for stage, sec in (("bm25_scoring", t_bm), ("query_encoding_gpu", t_enc),
                               ("faiss_search", t_faiss)):
                rows.append({"instance_id": inst.instance_id, "repo": inst.repo,
                             "chunks": len(corpus.chunks), "repeat": r + 1, "stage": stage,
                             "milliseconds": round(sec * 1000, 3)})
    pd.DataFrame(rows).to_csv(OUT / "latency_repeats.csv", index=False)
    log(f"latency repeats: {len(rows)} measurements")


# ------------------------------------------------------------------ 6. stage durations from logs
def stage_durations() -> None:
    pat = re.compile(r"=== (\S+) (START|END) (.+?)(?: \(exit (\d+)\))? ===")
    rows = []
    for log_name in ("pipeline.log", "llm_pipeline.log"):
        p = CFG.path("data") / log_name
        if not p.exists():
            continue
        start = {}
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = pat.search(line)
            if not m:
                continue
            ts, kind, name, code = m.groups()
            t = datetime.fromisoformat(ts)
            if kind == "START":
                start[name] = t
            elif name in start:
                rows.append({"log": log_name, "step": name, "start": start[name].isoformat(),
                             "end": t.isoformat(),
                             "minutes": round((t - start[name]).total_seconds() / 60, 2),
                             "exit_code": int(code) if code else None})
    pd.DataFrame(rows).to_csv(OUT / "stage_durations.csv", index=False)
    log(f"stage durations: {len(rows)} steps")


# ------------------------------------------------------------------ 7. LLM calls
def llm_calls() -> None:
    rows = []
    for p in sorted((CFG.path("cache") / "llm").glob("*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        try:
            ok = json.loads(rec["response"]) is not None
        except (json.JSONDecodeError, TypeError):
            ok = False
        rows.append({"call_id": p.stem[:12], "model": rec["model"],
                     "tokens_in": rec["tokens_in"], "tokens_out": rec["tokens_out"],
                     "seconds": round(rec.get("seconds", 0.0), 3), "valid_json": int(ok),
                     "written": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")})
    pd.DataFrame(rows).to_csv(OUT / "llm_calls.csv", index=False)
    log(f"llm calls: {len(rows)}")


# ------------------------------------------------------------------ 8. fine-tuning
def finetune() -> None:
    d = json.loads((CFG.path("reports") / "finetune_eval.json").read_text())
    pd.DataFrame(d["loss_history"], columns=["step", "loss"]).to_csv(OUT / "finetune_steps.csv",
                                                                     index=False)
    keys = sorted(k for k in d["after"] if "cosine" in k and any(
        t in k for t in ("accuracy@1", "accuracy@5", "accuracy@10", "mrr@10", "ndcg@10")))
    pd.DataFrame([{"metric": k.replace("val_cosine_", ""), "before": round(d["before"][k], 4),
                   "after": round(d["after"][k], 4)} for k in keys]) \
      .to_csv(OUT / "finetune_validation.csv", index=False)
    log("fine-tuning data written")


# ------------------------------------------------------------------ 9. bootstrap samples
def bootstrap_samples(pi: pd.DataFrame, n=1000, seed=42) -> None:
    t = pi[pi.split == "test"].pivot(index="instance_id", columns="system")
    pairs = [("S4", "S2", "file_acc@5"), ("S6", "S5", "func_acc@10"),
             ("S6b", "S6", "func_acc@10"), ("S8", "S6", "file_acc@1")]
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(t), size=(n, len(t)))
    out = {}
    for a, b, m in pairs:
        diff = (t[(m, a)] - t[(m, b)]).to_numpy()
        out[f"{a}-{b} {m}"] = diff[idx].mean(axis=1)
    pd.DataFrame(out).round(5).to_csv(OUT / "bootstrap_samples.csv", index_label="resample")
    log("bootstrap samples written")


# ------------------------------------------------------------------ 10. resources
def resources() -> None:
    def size_mb(p: Path) -> float:
        if p.is_file():
            return p.stat().st_size / 2**20
        return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 2**20

    data = CFG.path("data")
    rows = [{"resource": name, "value": round(size_mb(data / rel), 1), "unit": "MB",
             "source": f"measured on disk {datetime.now():%Y-%m-%d}"}
            for name, rel in [("Cloned repositories (bare)", "repos"),
                              ("Chunk cache (SQLite)", "cache/chunks.sqlite"),
                              ("Embedding cache (SQLite)", "cache/embeddings.sqlite"),
                              ("Per-instance score vectors", "cache/scores"),
                              ("BM25 indexes", "indexes"),
                              ("Fine-tuned model", "models/coderankembed-ft")]]
    rows += [
        {"resource": "GPU", "value": "GTX 1660 SUPER 6 GB", "unit": "", "source": "nvidia-smi"},
        {"resource": "Fine-tune peak GPU memory, mini-batch 4", "value": 3.65, "unit": "GB",
         "source": "torch.cuda.max_memory_allocated, benchmark 2026-11-11"},
        {"resource": "Fine-tune peak GPU memory, mini-batch 8", "value": 6.15, "unit": "GB",
         "source": "same benchmark (exceeds 6 GB VRAM -> spills to system RAM)"},
        {"resource": "Fine-tune step time, mini-batch 4", "value": 55.0, "unit": "s/step",
         "source": "same benchmark, 64 triples per step"},
        {"resource": "Fine-tune step time, mini-batch 16 (first attempt)", "value": "~900", "unit": "s/step",
         "source": "data/pipeline.log progress bar, 2026-10-25"},
        {"resource": "Encoding throughput fp32 vs fp16 (256 docs x 512 tok)", "value": "10.5 s vs 45.2 s",
         "unit": "", "source": "benchmark 2026-10-21"},
    ]
    pd.DataFrame(rows).to_csv(OUT / "resources.csv", index=False)
    log("resources written")


# ------------------------------------------------------------------ 11. events / errors
EVENTS = [
    ("2026-10-21", "Dense encoder", "CodeRankEmbed failed to load (missing einops, then removed "
     "transformers API)", "Dependency + library version change", "Added einops; compatibility shim"),
    ("2026-10-21", "Dense encoder", "fp16 encoding 4.3x slower than fp32 on GTX 1660",
     "No tensor cores on GTX 16xx", "fp32 locally; fp16 kept for Kaggle T4"),
    ("2026-10-25", "Fine-tuning", "~15 min per step; run killed at step 31/41",
     "Mini-batch 16 exceeded 6 GB VRAM (spill to shared memory)", "Mini-batch 4 (same gradients)"),
    ("2026-11-11", "Static analysis", "RecursionError on a deeply nested sympy file",
     "AST deeper than Python recursion limit", "Counted as parse failure + regression test"),
    ("2026-11-14", "LLM client", "gemini-2.5-flash returned 404",
     "Model retired for new API keys", "Switched to gemini-3.5-flash-lite"),
    ("2026-11-14", "LLM leakage guard", "False positive on django__django-13220",
     "Gold added line already existed in base-commit code", "Guard ignores lines present in shown base code"),
    ("2026-11-14", "LLM client", "429 RESOURCE_EXHAUSTED after ~500 requests",
     "Free-tier daily quota", "Stopped cleanly; resumed after reset from cache"),
    ("2026-11-14", "LLM reranker", "1 invalid ranking each in S7 and S8 (of 300)",
     "Model returned ids not in the candidate list twice", "Fallback to input order (logged)"),
]


def events() -> None:
    pd.DataFrame(EVENTS, columns=["date", "component", "event", "cause", "resolution"]) \
      .to_csv(OUT / "events_and_errors.csv", index=False)


# ------------------------------------------------------------------ manifest
def manifest() -> None:
    pkgs = ["torch", "sentence-transformers", "transformers", "bm25s", "faiss-cpu", "lightgbm",
            "networkx", "google-genai", "gradio", "numpy", "pandas", "scipy"]
    m = {"created": datetime.now().isoformat(timespec="seconds"),
         "git_commit": git_commit_hash(),
         "python": platform.python_version(), "os": platform.platform(),
         "packages": {p: version(p) for p in pkgs},
         "dataset": (CFG.path("cache") / "instances" / "test_source.txt").read_text().strip(),
         "llm_model": CFG.llm.model, "seed": CFG.seed,
         "config": dict(CFG)}
    (OUT / "manifest.json").write_text(json.dumps(m, indent=1, default=str), encoding="utf-8")
    subprocess.run(["git", "-C", str(PROJECT_ROOT), "status", "--short"], check=False)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    pi = per_instance()
    bootstrap_samples(pi)
    finetune()
    llm_calls()
    stage_durations()
    events()
    resources()
    ltr_seeds()
    fusion_sensitivity()
    latency_repeats()
    manifest()
    log("done")
