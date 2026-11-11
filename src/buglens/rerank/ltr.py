"""LambdaRank reranking with leave-one-repo-out cross-validation — S6, S6b.

Concept: learning to rank. Instead of predicting "is this chunk gold?" per
chunk (pointwise), LambdaRank optimises the *order* within each instance's
candidate list: its gradients ("lambdas") are pairwise swaps weighted by how
much each swap would change NDCG, so fixing the top of the list matters most.
LightGBM fits gradient-boosted trees to those lambdas. To measure transfer to
unseen codebases we use leave-one-repo-out CV over the 12 test repositories:
train on 11 repos, predict the held-out one, repeat. Instances whose gold is
not among the 50 candidates cannot teach anything and are left out of training.
"""

from __future__ import annotations

import time

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from buglens.analysis.facts import module_name, source_roots  # noqa: E402
from buglens.analysis.packages import package_of  # noqa: E402
from buglens.analysis.repo_analysis import pagerank_by_path  # noqa: E402
from buglens.chunking.corpus import load_corpus  # noqa: E402
from buglens.config import Config, set_seed, write_meta  # noqa: E402
from buglens.data.prepare import load_labels  # noqa: E402
from buglens.data.swebench import load_split  # noqa: E402
from buglens.eval.evaluate import load_run  # noqa: E402
from buglens.rerank.features import BASE_FEATURES, S6B_FEATURES, candidate_features  # noqa: E402
from buglens.retrieval.fusion import files_from_chunks  # noqa: E402
from buglens.retrieval.run import ScoreProvider, group_by_commit  # noqa: E402
from buglens.schemas import Candidate, RankedResult  # noqa: E402
from buglens.utils import console, progress, summary, write_jsonl  # noqa: E402


def _package_similarities(cfg: Config, encoder, inst, summaries: dict[str, str]
                          ) -> dict[str, float]:
    if not summaries:
        return {}
    pkgs = sorted(summaries)
    q = encoder.encode_queries([inst.problem_statement])[0]
    docs = encoder.encode_docs([summaries[p] for p in pkgs])
    return {p: float(v) for p, v in zip(pkgs, docs @ q, strict=True)}


def build_feature_table(cfg: Config, system: str, split: str) -> pd.DataFrame:
    """One row per (instance, S5 candidate). Cached as parquet."""
    out = cfg.path("cache") / "ltr" / f"{system}_{split}.parquet"
    if out.exists():
        return pd.read_parquet(out)
    base = {r.instance_id: r for r in load_run(cfg, "S5", split)}
    labels = load_labels(cfg, split)
    instances = load_split(cfg, split)
    providers = {k: ScoreProvider(cfg, k) for k in ("bm25", "dense", "dense_ft")}
    encoder = None
    summaries_by_repo: dict[str, dict[str, str]] = {}
    if system == "S6b":
        from buglens.onboard.summarize import load_summary_texts

        encoder = providers["dense_ft"]._encoder()
        for repo in sorted({i.repo for i in instances}):
            summaries_by_repo[repo] = load_summary_texts(cfg, repo)
    rows = []
    with progress() as p:
        task = p.add_task(f"features {system} {split}", total=len(instances))
        for (repo, commit), group in group_by_commit(instances):
            corpus = load_corpus(cfg, repo, commit)
            pr = pagerank_by_path(cfg, repo, commit)
            pkg_of_path = None
            if system == "S6b":
                roots = source_roots(sorted(corpus.file_lines))
                pkg_of_path = {path: package_of(module_name(path, roots), cfg.analysis.pkg_depth)
                               for path in corpus.file_lines}
            for inst in group:
                comp = {k: prov.scores(inst, corpus) for k, prov in providers.items()}
                cands = base[inst.instance_id].functions
                sims = (_package_similarities(cfg, encoder, inst, summaries_by_repo[repo])
                        if system == "S6b" else None)
                feats = candidate_features(inst, corpus, cands, comp, pr, sims, pkg_of_path)
                gold = set(labels[inst.instance_id].functions)
                for cand, f in zip(cands, feats, strict=True):
                    rows.append({"instance_id": inst.instance_id, "repo": inst.repo,
                                 "chunk_id": cand.chunk_id, "path": cand.path,
                                 "s5_rank": cand.rank, "label": int(cand.chunk_id in gold),
                                 **f})
                p.advance(task)
    df = pd.DataFrame(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df


def _ranker(cfg: Config):
    from lightgbm import LGBMRanker

    k = cfg.rerank
    return LGBMRanker(objective="lambdarank", n_estimators=k.n_estimators,
                      learning_rate=k.learning_rate, num_leaves=k.num_leaves,
                      min_child_samples=k.min_child_samples, random_state=cfg.seed,
                      deterministic=True, force_row_wise=True, verbose=-1)


def _fit(cfg: Config, train: pd.DataFrame, features: list[str]):
    has_gold = train.groupby("instance_id")["label"].transform("max") > 0
    train = train[has_gold].sort_values(["instance_id", "s5_rank"])
    sizes = train.groupby("instance_id", sort=False).size().to_numpy()
    model = _ranker(cfg)
    model.fit(train[features], train["label"], group=sizes)
    return model


def rerank(cfg: Config, system: str, split: str) -> list[RankedResult]:
    if system not in ("S6", "S6b"):
        raise ValueError("rerank supports S6 and S6b")
    set_seed(cfg.seed)
    features = S6B_FEATURES if system == "S6b" else BASE_FEATURES
    t0 = time.perf_counter()
    df = build_feature_table(cfg, system, split)
    no_gold = int((df.groupby("instance_id")["label"].max() == 0).sum())
    console.print(f"{no_gold}/{df.instance_id.nunique()} instances have no gold among "
                  "the candidates (excluded from training, still ranked)")

    df["ltr"] = np.nan
    importances = []
    if split == "test":
        repos = sorted(df.repo.unique())
        for repo in repos:  # FR-K4 leave-one-repo-out
            model = _fit(cfg, df[df.repo != repo], features)
            mask = df.repo == repo
            df.loc[mask, "ltr"] = model.predict(df.loc[mask, features])
            importances.append(pd.Series(model.booster_.feature_importance("gain"),
                                         index=features, name=repo))
        _plot_importance(cfg, system, pd.concat(importances, axis=1))
    else:  # dev / other: train on all test repos, predict this split
        train = build_feature_table(cfg, system, "test")
        model = _fit(cfg, train, features)
        df["ltr"] = model.predict(df[features])
    if split == "test":  # final model on all test repos, used by the demo
        final = _fit(cfg, df, features)
        path = cfg.path("models") / f"ltr_{system}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        final.booster_.save_model(str(path))

    elapsed = (time.perf_counter() - t0) / max(df.instance_id.nunique(), 1)
    base = {r.instance_id: r for r in load_run(cfg, "S5", split)}
    results = []
    for inst in load_split(cfg, split):
        sub = df[df.instance_id == inst.instance_id].sort_values(
            ["ltr", "s5_rank"], ascending=[False, True])
        old = {c.chunk_id: c for c in base[inst.instance_id].functions}
        cands = []
        for rank, row in enumerate(sub.itertuples(), start=1):
            scores = dict(old[row.chunk_id].scores)
            scores["ltr"] = float(row.ltr)
            cands.append(Candidate(chunk_id=row.chunk_id, path=row.path, scores=scores,
                                   rank=rank))
        results.append(RankedResult(
            instance_id=inst.instance_id, system=system, functions=cands,
            files=files_from_chunks([c.path for c in cands]),
            seconds=base[inst.instance_id].seconds + elapsed))
    out = cfg.path("runs") / f"{system}_{split}.jsonl"
    write_jsonl(out, results)
    write_meta(out.parent, cfg, filename=f"{system}_{split}.meta.json", system=system,
               split=split, features=features)
    summary("rerank", system=system, split=split, instances=len(results), out=str(out))
    return results


def _plot_importance(cfg: Config, system: str, imp: pd.DataFrame) -> None:
    norm = imp / imp.sum(axis=0)
    mean = norm.mean(axis=1).sort_values()
    std = norm.std(axis=1).reindex(mean.index)
    figures = cfg.path("reports") / "figures"
    figures.mkdir(parents=True, exist_ok=True)
    name = "feature_importance.png" if system == "S6" else f"feature_importance_{system}.png"
    plt.figure(figsize=(6.5, 0.28 * len(mean) + 1.2))
    plt.barh(mean.index, mean.values, xerr=std.values, color="#4C72B0", alpha=0.9)
    plt.xlabel("normalised gain (mean over leave-one-repo-out folds, ±1 sd)")
    plt.title(f"{system} LambdaRank feature importance")
    plt.tight_layout()
    plt.savefig(figures / name, dpi=150)
    plt.close()
    norm.to_csv(figures / name.replace(".png", ".csv"))
