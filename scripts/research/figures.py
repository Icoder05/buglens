"""Figures for the research report (one consistent style).

Style rules (from university/IEEE figure guidance): no chart titles (the caption explains),
full axis labels with units, Arial, minimal gridlines, colour-blind-safe Okabe-Ito palette
plus distinct markers so figures survive black-and-white printing, CIs where sampling applies.
Run after collect.py:  uv run python scripts/research/figures.py
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from buglens.config import PROJECT_ROOT  # noqa: E402
from buglens.eval.stats import bootstrap_ci, paired_bootstrap  # noqa: E402

DATA = PROJECT_ROOT / "reports" / "research" / "data"
FIG = PROJECT_ROOT / "reports" / "research" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

OKABE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#000000"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "*"]
SYSTEMS = ["S1", "S2", "S3", "S4", "S5", "S6", "S6b", "S7", "S8"]
NAMES = {"S1": "S1 BM25", "S2": "S2 Dense", "S3": "S3 RRF(S1,S2)", "S4": "S4 Dense-FT",
         "S5": "S5 RRF(S1,S4)", "S6": "S6 LambdaRank", "S6b": "S6b +summaries",
         "S7": "S7 S5→LLM", "S8": "S8 S6→LLM", "A1": "A1 S5+hints"}
METRIC_LABEL = {"file_acc@1": "File Acc@1", "file_acc@5": "File Acc@5",
                "func_acc@10": "Function Acc@10", "func_mrr": "Function MRR"}

plt.rcParams.update({
    "font.family": "Arial", "font.size": 9, "axes.labelsize": 9, "xtick.labelsize": 8,
    "ytick.labelsize": 8, "legend.fontsize": 8, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": False, "savefig.dpi": 220,
    "savefig.bbox": "tight", "figure.dpi": 110,
})
W = 6.3  # inches: A4 text width with 2.5 cm margins
STATS: dict = {}


def save(fig, name: str) -> None:
    fig.savefig(FIG / f"{name}.png")
    plt.close(fig)
    print("saved", name)


def ygrid(ax) -> None:
    ax.yaxis.grid(True, color="#dddddd", linewidth=0.6)
    ax.set_axisbelow(True)


pi = pd.read_csv(DATA / "per_instance_metrics.csv")
test = pi[pi.split == "test"]
wide = test.pivot(index="instance_id", columns="system")


# ------------------------------------------------------------------ F2 main results with CI
def fig_main_results():
    metrics = ["file_acc@1", "file_acc@5", "func_acc@10"]
    fig, axes = plt.subplots(1, 3, figsize=(W, 3.0), sharey=True)
    ys = np.arange(len(SYSTEMS))[::-1]
    table = []
    for ax, m in zip(axes, metrics, strict=True):
        for y, s in zip(ys, SYSTEMS, strict=True):
            mean, lo, hi = bootstrap_ci(wide[(m, s)])
            llm = s in ("S7", "S8")
            ax.errorbar(mean, y, xerr=[[mean - lo], [hi - mean]], fmt="s" if llm else "o",
                        color=OKABE[3] if llm else OKABE[0], ms=4, capsize=2, lw=1)
            table.append({"system": s, "metric": m, "mean": mean, "low": lo, "high": hi})
        ax.set_xlabel(METRIC_LABEL[m])
        ax.set_xlim(0.3, 1.0)
        ax.xaxis.grid(True, color="#dddddd", lw=0.6)
        ax.set_axisbelow(True)
    axes[0].set_yticks(ys, [NAMES[s] for s in SYSTEMS])
    axes[0].plot([], [], "o", color=OKABE[0], label="no LLM (0 tokens)")
    axes[0].plot([], [], "s", color=OKABE[3], label="Gemini reranker (S7, S8)")
    fig.legend(loc="upper center", ncol=2, frameon=False, bbox_to_anchor=(0.55, 1.06))
    STATS["main_ci"] = table
    save(fig, "fig02_main_results_ci")


# ------------------------------------------------------------------ F3 accuracy vs tokens
def fig_tokens():
    fig, ax = plt.subplots(figsize=(W * 0.62, 3.0))
    keys = ["S1", "S5", "S6", "S7", "S8"]
    offsets = {("file_acc@1", "S1"): (8, -3), ("file_acc@1", "S5"): (8, -8),
               ("file_acc@1", "S6"): (8, 2), ("file_acc@1", "S7"): (-14, -12),
               ("file_acc@1", "S8"): (6, -3), ("file_acc@5", "S1"): (8, -3),
               ("file_acc@5", "S5"): (8, -8), ("file_acc@5", "S6"): (8, 2),
               ("file_acc@5", "S7"): (-14, -12), ("file_acc@5", "S8"): (6, -3)}
    for i, (m, mk) in enumerate((("file_acc@1", "o"), ("file_acc@5", "s"))):
        for s in keys:
            x = wide[("tokens", s)].mean() / 1000
            y = wide[(m, s)].mean()
            ax.scatter(x, y, marker=mk, color=OKABE[i], s=26, zorder=3,
                       label=METRIC_LABEL[m] if s == "S1" else None)
            ax.annotate(s, (x, y), textcoords="offset points", xytext=offsets[(m, s)], fontsize=7)
    ax.set_xlim(-0.6, 7)
    ax.set_xlabel("Mean LLM tokens per issue (thousands)")
    ax.set_ylabel("Accuracy (share of 300 issues)")
    ygrid(ax)
    ax.legend(frameon=False, loc="lower right")
    save(fig, "fig03_accuracy_vs_tokens")


# ------------------------------------------------------------------ F4 forest plot
COMPARISONS = [("S2", "S1", "file_acc@5", "RQ1"), ("S3", "S2", "file_acc@5", "RQ1"),
               ("S3", "S2", "func_acc@10", "RQ1"), ("S4", "S2", "file_acc@5", "RQ2"),
               ("S5", "S3", "file_acc@5", "RQ2"), ("S6", "S5", "func_acc@10", "RQ3"),
               ("S6", "S7", "func_acc@10", "RQ3"), ("S7", "S6", "file_acc@1", "RQ3"),
               ("S8", "S6", "file_acc@1", "RQ3"), ("S6b", "S6", "func_acc@10", "RQ4")]


def fig_forest():
    from buglens.eval.stats import mcnemar

    rows = []
    for a, b, m, rq in COMPARISONS:
        pb = paired_bootstrap(wide[(m, a)], wide[(m, b)])
        mc = mcnemar(wide[(m, a)], wide[(m, b)])
        rows.append({"comparison": f"{a} − {b}", "metric": m, "rq": rq, **pb,
                     "a_only": mc["a_only"], "b_only": mc["b_only"], "mcnemar_p": mc["p"]})
    df = pd.DataFrame(rows)
    df.to_csv(DATA / "paired_comparisons.csv", index=False)
    STATS["paired"] = rows
    fig, ax = plt.subplots(figsize=(W, 3.4))
    ys = np.arange(len(df))[::-1]
    for y, r in zip(ys, df.itertuples(), strict=True):
        sig = r.low > 0 or r.high < 0
        ax.errorbar(r.diff * 100, y, xerr=[[(r.diff - r.low) * 100], [(r.high - r.diff) * 100]],
                    fmt="o" if sig else "o", mfc=OKABE[0] if sig else "white", mec=OKABE[0],
                    color=OKABE[0], ms=5, capsize=2, lw=1)
    ax.axvline(0, color="#555555", lw=0.8, ls="--")
    ax.set_yticks(ys, [f"{r.rq}: {r.comparison} ({METRIC_LABEL[r.metric]})" for r in df.itertuples()])
    ax.set_xlabel("Paired difference A − B (percentage points, 95% bootstrap CI)")
    ax.xaxis.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    ax.plot([], [], "o", color=OKABE[0], label="CI excludes 0")
    ax.plot([], [], "o", mfc="white", mec=OKABE[0], label="CI includes 0")
    ax.legend(frameon=False, loc="lower right")
    save(fig, "fig04_paired_differences")


# ------------------------------------------------------------------ F5 bootstrap distributions
def fig_bootstrap():
    bs = pd.read_csv(DATA / "bootstrap_samples.csv", index_col=0)
    fig, axes = plt.subplots(2, 2, figsize=(W, 3.8))
    for ax, col, c in zip(axes.flat, bs.columns, OKABE, strict=False):
        v = bs[col] * 100
        ax.hist(v, bins=30, color=c, edgecolor="white", lw=0.4, zorder=2)
        lo, hi = np.percentile(v, [2.5, 97.5])
        ax.axvline(0, color="#333333", lw=0.8, ls="--")
        ax.axvspan(lo, hi, color="#e5e5e5", lw=0, zorder=0, label="central 95%")
        ax.set_xlabel(f"{col.replace('_', ' ')} difference (pp)")
        ax.set_ylabel("Resamples (of 1,000)")
    fig.tight_layout()
    save(fig, "fig05_bootstrap_distributions")


# ------------------------------------------------------------------ F6 per repo
def fig_per_repo():
    n = test[test.system == "S1"].groupby("repo").size()
    order = n.sort_values().index
    fig, ax = plt.subplots(figsize=(W, 3.6))
    ys = np.arange(len(order))
    for i, s in enumerate(("S1", "S6", "S8")):
        vals = test[test.system == s].groupby("repo")["file_acc@5"].mean().reindex(order)
        ax.scatter(vals, ys + (i - 1) * 0.22, marker=MARKERS[i], color=OKABE[i], s=20,
                   label=NAMES[s], zorder=3)
    ax.set_yticks(ys, [f"{r.split('/')[1]} (n={n[r]})" for r in order])
    ax.set_xlabel("File Acc@5 within repository (share of that repository's issues)")
    ax.xaxis.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    ax.set_xlim(-0.03, 1.03)
    ax.legend(frameon=False, loc="lower left", ncol=3, bbox_to_anchor=(0, 1.0))
    save(fig, "fig06_per_repository")


# ------------------------------------------------------------------ F7 LORO folds
def fig_folds():
    rows = []
    for repo, g in test.groupby("repo"):
        w = g.pivot(index="instance_id", columns="system", values="func_acc@10")
        rows.append({"repo": repo, "n": len(w), "S5": w["S5"].mean(), "S6": w["S6"].mean(),
                     "diff_pp": (w["S6"] - w["S5"]).mean() * 100})
    df = pd.DataFrame(rows).sort_values("diff_pp")
    df.to_csv(DATA / "loro_folds.csv", index=False)
    STATS["folds"] = df.to_dict("records")
    fig, ax = plt.subplots(figsize=(W, 3.3))
    colors = [OKABE[0] if d >= 0 else OKABE[3] for d in df.diff_pp]
    ax.barh(range(len(df)), df.diff_pp, color=colors, height=0.6)
    ax.set_yticks(range(len(df)), [f"{r.split('/')[1]} (n={n})" for r, n in zip(df.repo, df.n, strict=True)])
    ax.axvline(0, color="#333333", lw=0.8)
    ax.set_xlabel("S6 − S5 function Acc@10 on the held-out repository (percentage points)")
    ax.xaxis.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    save(fig, "fig07_loro_folds")


# ------------------------------------------------------------------ F8 candidate depth
def fig_depth():
    d = pd.read_csv(DATA / "candidate_depth.csv")
    fig, ax = plt.subplots(figsize=(W * 0.62, 2.8))
    ax.plot(d.depth, d.gold_function_in_top, marker="o", color=OKABE[0], label="Gold function among top-k chunks")
    ax.plot(d.depth, d.gold_file_in_top_files, marker="s", color=OKABE[1], label="Gold file among top-k files")
    ax.axvline(50, color="#777777", ls=":", lw=0.8)
    ax.annotate("reranker input (k = 50)", (50, 0.62), xytext=(54, 0.62), fontsize=7)
    ax.set_xscale("log")
    ax.set_xticks(d.depth, [str(x) for x in d.depth])
    ax.set_xlabel("Candidate depth k (log scale)")
    ax.set_ylabel("Share of 300 issues")
    ax.set_ylim(0.4, 1.0)
    ygrid(ax)
    ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 0.0))
    save(fig, "fig08_candidate_depth")


# ------------------------------------------------------------------ F9 RRF k
def fig_rrf():
    d = pd.read_csv(DATA / "rrf_k_sensitivity.csv")
    fig, ax = plt.subplots(figsize=(W * 0.62, 2.8))
    for i, m in enumerate(("file_acc@1", "file_acc@5", "func_acc@10")):
        ax.plot(d.rrf_k, d[m], marker=MARKERS[i], color=OKABE[i], label=METRIC_LABEL[m])
    ax.axvline(60, color="#777777", ls=":", lw=0.8)
    ax.set_xscale("log")
    ax.set_xticks(d.rrf_k, [str(x) for x in d.rrf_k])
    ax.set_xlabel("RRF constant k (log scale; 60 = configured value)")
    ax.set_ylabel("S5 accuracy (share of 300 issues)")
    ygrid(ax)
    ax.legend(frameon=False, loc="center right", bbox_to_anchor=(1.0, 0.55))
    save(fig, "fig09_rrf_k_sensitivity")


# ------------------------------------------------------------------ F10 LTR seeds
def fig_seeds():
    d = pd.read_csv(DATA / "ltr_seed_iterations.csv")
    det = {m: wide[(m, "S6")].mean() for m in METRIC_LABEL}
    fig, ax = plt.subplots(figsize=(W * 0.62, 2.8))
    ms = ["file_acc@1", "file_acc@5", "func_acc@10", "func_mrr"]
    for i, m in enumerate(ms):
        ax.scatter([i] * len(d), d[m], color=OKABE[0], s=16, zorder=3,
                   label="stochastic LambdaRank, 5 seeds" if i == 0 else None)
        ax.scatter(i, det[m], marker="_", s=300, color=OKABE[3], zorder=4,
                   label="deterministic S6 (reported)" if i == 0 else None)
    ax.set_xticks(range(len(ms)), [METRIC_LABEL[m] for m in ms])
    ax.set_ylabel("Score (share of 300 issues)")
    ygrid(ax)
    ax.legend(frameon=False, loc="lower left")
    save(fig, "fig10_ltr_seed_iterations")


# ------------------------------------------------------------------ F11 LLM repeats
def fig_llm_repeats():
    p = DATA / "llm_repeats.csv"
    if not p.exists():
        return
    d = pd.read_csv(p)
    reps = sorted(d.repeat.unique())
    piv = d.pivot(index="instance_id", columns="repeat", values="top1_chunk")
    agree_all = (piv.nunique(axis=1) == 1).mean()
    full = d.pivot(index="instance_id", columns="repeat", values="ranking")
    agree_rank = (full.nunique(axis=1) == 1).mean()
    acc = d.groupby("repeat")[["gold_file_top1", "gold_func_in_top5"]].mean()
    STATS["llm_repeats"] = {"n": int(piv.shape[0]), "repeats": len(reps),
                            "top1_identical_all": float(agree_all),
                            "full_ranking_identical_all": float(agree_rank),
                            "acc_by_repeat": acc.round(4).to_dict()}
    fig, axes = plt.subplots(1, 2, figsize=(W, 2.6))
    x = np.arange(len(reps))
    axes[0].bar(x - 0.18, acc.gold_file_top1, 0.36, color=OKABE[0], label="File Acc@1")
    axes[0].bar(x + 0.18, acc.gold_func_in_top5, 0.36, color=OKABE[1], label="Function Acc@5",
                hatch="//", edgecolor="white")
    axes[0].set_xticks(x, [f"Run {r + 1}" for r in reps])
    axes[0].set_ylabel(f"Accuracy on {piv.shape[0]} sampled issues")
    axes[0].set_ylim(0, 1.15)
    axes[0].set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ygrid(axes[0])
    axes[0].legend(frameon=False, loc="upper center", ncol=2)
    axes[1].bar([0, 1], [agree_all, agree_rank], color=[OKABE[2], OKABE[5]], width=0.5)
    axes[1].set_xticks([0, 1], ["Same top-1\nin all runs", "Identical full\nranking in all runs"])
    axes[1].set_ylabel("Share of sampled issues")
    axes[1].set_ylim(0, 1)
    ygrid(axes[1])
    fig.tight_layout()
    save(fig, "fig11_llm_repeat_runs")


# ------------------------------------------------------------------ F12 fine-tuning
def fig_finetune():
    s = pd.read_csv(DATA / "finetune_steps.csv")
    v = pd.read_csv(DATA / "finetune_validation.csv")
    fig, axes = plt.subplots(1, 2, figsize=(W, 2.6), gridspec_kw={"width_ratios": [1.4, 1]})
    axes[0].plot(s.step, s.loss, color="#9ab7d3", lw=0.9, marker=".", ms=3, label="per step")
    axes[0].plot(s.step, s.loss.rolling(5, min_periods=1).mean(), color=OKABE[0], lw=1.6,
                 label="5-step moving average")
    axes[0].set_xlabel("Training step (batch of 64 triples)")
    axes[0].set_ylabel("Contrastive loss (CachedMNRL)")
    ygrid(axes[0])
    axes[0].legend(frameon=False)
    order = ["accuracy@1", "accuracy@5", "accuracy@10", "mrr@10"]
    keep = v.set_index("metric").loc[order].reset_index()
    x = np.arange(len(keep))
    axes[1].bar(x - 0.18, keep.before, 0.36, color="#bbbbbb", label="before")
    axes[1].bar(x + 0.18, keep.after, 0.36, color=OKABE[0], label="after")
    axes[1].set_xticks(x, [m.replace("accuracy", "Acc").replace("mrr", "MRR") for m in keep.metric])
    axes[1].set_ylabel("Validation score (429 held-out pairs)")
    axes[1].set_ylim(0, 0.8)
    ygrid(axes[1])
    axes[1].legend(frameon=False, loc="upper left", ncol=2)
    fig.tight_layout()
    save(fig, "fig12_finetuning")


# ------------------------------------------------------------------ F13 latency
def fig_latency():
    d = pd.read_csv(DATA / "latency_repeats.csv")
    stages = ["bm25_scoring", "query_encoding_gpu", "faiss_search"]
    labels = ["BM25 scoring", "Query encoding (GPU)", "FAISS exact search"]
    llm = pd.read_csv(DATA / "llm_calls.csv")
    llm = llm[llm.seconds > 0]
    data = [d[d.stage == s].milliseconds for s in stages] + [llm.seconds * 1000]
    STATS["latency_ms"] = {lab: {"median": float(np.median(x)), "p90": float(np.percentile(x, 90)),
                                 "n": int(len(x))} for lab, x in zip(labels + ["LLM call"], data, strict=True)}
    fig, ax = plt.subplots(figsize=(W, 2.6))
    ax.boxplot(data, vert=False, widths=0.5, showfliers=True,
               flierprops={"marker": ".", "ms": 3, "mec": "#888888"},
               medianprops={"color": OKABE[3]})
    ax.set_yticks(range(1, 5), labels + ["Gemini call (S7/S8, summaries)"])
    ax.set_xscale("log")
    ax.set_xlabel("Time per issue or call (milliseconds, log scale)")
    ax.xaxis.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    save(fig, "fig13_latency")


# ------------------------------------------------------------------ F14 pipeline timeline
def fig_timeline():
    d = pd.read_csv(DATA / "stage_durations.csv")
    d["start"] = pd.to_datetime(d.start)
    d["exit_code"] = d.exit_code.fillna(0)
    # longest run of each step (including a failed attempt), 14 longest steps, in time order
    d = d.sort_values("minutes", ascending=False).drop_duplicates(["step", "exit_code"])
    d = d.head(14).sort_values("start")
    d["step"] = [f"{s} (failed)" if c else s for s, c in zip(d.step, d.exit_code, strict=True)]
    fig, ax = plt.subplots(figsize=(W, 3.2))
    ys = np.arange(len(d))[::-1]
    ax.barh(ys, d.minutes, color=[OKABE[3] if (c or 0) else OKABE[0] for c in d.exit_code.fillna(0)],
            height=0.6)
    for y, m in zip(ys, d.minutes, strict=True):
        ax.text(m + 1, y, f"{m:.0f} min", va="center", fontsize=7)
    ax.set_yticks(ys, d.step)
    ax.set_xlabel("Wall-clock duration of pipeline step (minutes)")
    ax.xaxis.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    save(fig, "fig14_stage_durations")


# ------------------------------------------------------------------ F15 feature importance
def fig_importance():
    imp = pd.read_csv(PROJECT_ROOT / "reports" / "figures" / "feature_importance.csv", index_col=0)
    mean = imp.mean(axis=1).sort_values()
    sd = imp.std(axis=1).reindex(mean.index)
    mean.round(4).to_frame("mean_share").assign(sd=sd.round(4)).to_csv(DATA / "feature_importance.csv")
    fig, ax = plt.subplots(figsize=(W * 0.75, 4.2))
    ax.barh(mean.index, mean.values, xerr=sd.values, color=OKABE[0],
            error_kw={"lw": 0.8, "capsize": 1.5})
    ax.set_xlabel("Share of total split gain (mean over 12 folds, ±1 SD)")
    ax.xaxis.grid(True, color="#dddddd", lw=0.6)
    ax.set_axisbelow(True)
    save(fig, "fig15_feature_importance")


# ------------------------------------------------------------------ F16 error categories
def fig_errors():
    cats = [("Root cause in shared lower-level module", 8), ("Fix in a different component", 7),
            ("Right package, wrong module", 2), ("Noisy issue text", 2), ("Lexical confusion", 1)]
    pd.DataFrame(cats, columns=["category", "count"]).to_csv(DATA / "error_categories.csv", index=False)
    fig, ax = plt.subplots(figsize=(W * 0.75, 2.2))
    ax.barh([c for c, _ in cats][::-1], [n for _, n in cats][::-1], color=OKABE[3], height=0.55)
    for y, (_, n) in enumerate(cats[::-1]):
        ax.text(n + 0.15, y, str(n), va="center", fontsize=8)
    ax.set_xlabel("Number of the 20 sampled S6 failures")
    save(fig, "fig16_error_categories")


# ------------------------------------------------------------------ F17 dev vs test
def fig_dev_test():
    sy = ["S1", "S2", "S3", "S4", "S5", "S6"]
    fig, ax = plt.subplots(figsize=(W * 0.75, 2.7))
    rows = []
    for i, split in enumerate(("test", "dev")):
        sub = pi[pi.split == split]
        means, los, his = [], [], []
        for s in sy:
            m, lo, hi = bootstrap_ci(sub[sub.system == s]["file_acc@5"])
            means.append(m)
            los.append(m - lo)
            his.append(hi - m)
            rows.append({"split": split, "system": s, "mean": m, "low": lo, "high": hi,
                         "n": int((sub.system == s).sum())})
        x = np.arange(len(sy)) + (i - 0.5) * 0.25
        n = int((sub.system == "S1").sum())
        ax.errorbar(x, means, yerr=[los, his], fmt=MARKERS[i], color=OKABE[i], capsize=2,
                    ms=4, lw=1, label=f"{split} (n = {n}, {'12' if split == 'test' else '6'} repos)")
    STATS["dev_test"] = rows
    ax.set_xticks(range(len(sy)), sy)
    ax.set_ylabel("File Acc@5 (95% bootstrap CI)")
    ax.set_ylim(0.3, 1.05)
    ygrid(ax)
    ax.legend(frameon=False, loc="lower right")
    save(fig, "fig17_dev_vs_test")


if __name__ == "__main__":
    for f in (fig_main_results, fig_tokens, fig_forest, fig_bootstrap, fig_per_repo, fig_folds,
              fig_depth, fig_rrf, fig_seeds, fig_llm_repeats, fig_finetune, fig_latency,
              fig_timeline, fig_importance, fig_errors, fig_dev_test):
        f()
    (DATA / "figure_stats.json").write_text(json.dumps(STATS, indent=1, default=float))
