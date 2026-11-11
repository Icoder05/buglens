"""Results report, figures and error dump — FR-E3, FR-E4.

Concept: the report is regenerated purely from `runs/*.jsonl` + gold labels,
so every number in `reports/results.md` is reproducible with `buglens report`.
Each cell shows the mean with its bootstrap 95% CI. Paired comparisons listed
in `experiments.yaml` get a paired-bootstrap CI on the difference and an exact
McNemar test. Systems are compared on identical instance sets; S6b (RQ4) only
covers repos that have onboarding summaries, so it is reported against S6 on
that same subset, with the coverage stated. A1 (hints) is a separate ablation.
"""

from __future__ import annotations

import json
import random

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from buglens.config import Config, load_experiments, write_meta  # noqa: E402
from buglens.data.prepare import load_labels  # noqa: E402
from buglens.data.swebench import load_split  # noqa: E402
from buglens.eval.evaluate import eval_system, load_run  # noqa: E402
from buglens.eval.stats import bootstrap_ci, mcnemar, paired_bootstrap  # noqa: E402
from buglens.utils import console, md_table, summary  # noqa: E402

ORDER = ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]
DESCRIPTIONS = {
    "S1": "BM25", "S2": "Dense (CodeRankEmbed)", "S3": "RRF(S1, S2)",
    "S4": "Dense (fine-tuned)", "S5": "RRF(S1, S4)", "S6": "S5 → LambdaRank",
    "S6b": "S6 + pkg_summary_sim", "S7": "S5 → Gemini rerank", "S8": "S6 → Gemini rerank",
    "A1": "S5 + hints in query",
}
HEADLINE = ["file_acc@1", "file_acc@3", "file_acc@5", "file_mrr", "func_acc@5", "func_acc@10",
            "func_recall@10", "func_mrr"]


def _available(cfg: Config, split: str) -> list[str]:
    return [s for s in [*ORDER, "S6b", "A1"]
            if (cfg.path("runs") / f"{s}_{split}.jsonl").exists()]


def _cell(values, cfg: Config) -> str:
    m, lo, hi = bootstrap_ci(values, cfg.eval.bootstrap_resamples, cfg.seed, cfg.eval.ci)
    return f"{m:.3f} [{lo:.3f}, {hi:.3f}]"


def summary_rows(cfg: Config, frames: dict[str, pd.DataFrame], systems: list[str]
                 ) -> list[dict]:
    rows = []
    for s in systems:
        df = frames[s]
        row = {"system": s, "pipeline": DESCRIPTIONS.get(s, s), "n": len(df)}
        for m in HEADLINE:
            row[m] = _cell(df[m], cfg)
        row["mean_tokens"] = round(float(df["tokens"].mean()), 1)
        row["mean_seconds"] = round(float(df["seconds"].mean()), 3)
        rows.append(row)
    return rows


def make_report(cfg: Config, split: str = "test") -> str:
    systems = _available(cfg, split)
    if not systems:
        raise FileNotFoundError("no runs found; run `buglens retrieve` first")
    frames = {s: eval_system(cfg, s, split, quiet=True) for s in systems}
    n_total = len(load_split(cfg, split))
    full = [s for s in systems if len(frames[s]) == n_total and s not in ("S6b", "A1")]
    partial = [s for s in systems if len(frames[s]) < n_total and s not in ("S6b", "A1")]
    reports = cfg.path("reports")
    figures = reports / "figures"
    figures.mkdir(parents=True, exist_ok=True)

    main_rows = summary_rows(cfg, frames, full + partial)
    cols = ["system", "pipeline", "n", *HEADLINE, "mean_tokens", "mean_seconds"]
    pd.DataFrame(main_rows)[cols].to_csv(reports / "results.csv", index=False)

    md = ["# BugLens results", "",
          f"SWE-bench Lite **{split}** ({n_total} instances). Cells: mean [bootstrap 95% CI, "
          f"{cfg.eval.bootstrap_resamples} resamples, seed {cfg.seed}].", ""]
    best = max(full, key=lambda s: frames[s]["file_acc@5"].mean()) if full else None
    if best:
        b = frames[best]
        md += [f"**Finding.** The best system on all {n_total} instances is **{best}** "
               f"({DESCRIPTIONS.get(best, best)}): file Acc@5 {_cell(b['file_acc@5'], cfg)}, "
               f"function Acc@10 {_cell(b['func_acc@10'], cfg)}, at "
               f"{b['tokens'].mean():.0f} LLM tokens per issue.", ""]
    md += ["## Main results", "", md_table(main_rows, cols), ""]
    if partial:
        md += [f"_Partial runs (fewer than {n_total} instances, e.g. stopped by the free-tier "
               f"quota): {', '.join(partial)}. Their rows are not directly comparable._", ""]

    # paired comparisons
    md += ["## Paired comparisons", "",
           "Difference A − B on common instances; paired bootstrap 95% CI and two-sided "
           "p; exact McNemar on the binary metric.", ""]
    comp_rows = []
    for a_sys, b_sys in load_experiments().comparisons:
        if a_sys not in frames or b_sys not in frames:
            continue
        common = frames[a_sys].index.intersection(frames[b_sys].index)
        for m in ("file_acc@5", "func_acc@10"):
            fa, fb = frames[a_sys].loc[common, m], frames[b_sys].loc[common, m]
            pb = paired_bootstrap(fa, fb, cfg.eval.bootstrap_resamples, cfg.seed, cfg.eval.ci)
            mc = mcnemar(fa, fb)
            comp_rows.append({"A vs B": f"{a_sys} vs {b_sys}", "metric": m, "n": len(common),
                              "diff": f"{pb['diff']:+.3f} [{pb['low']:+.3f}, {pb['high']:+.3f}]",
                              "bootstrap p": f"{pb['p']:.3f}",
                              "McNemar (A only / B only, p)":
                                  f"{mc['a_only']} / {mc['b_only']}, p={mc['p']:.3f}"})
    md += [md_table(comp_rows, ["A vs B", "metric", "n", "diff", "bootstrap p",
                                 "McNemar (A only / B only, p)"]) if comp_rows
           else "_No comparison pairs available yet._", ""]

    # RQ4
    if "S6b" in frames and "S6" in frames:
        sub = frames["S6b"].index.intersection(frames["S6"].index)
        insts = {i.instance_id: i.repo for i in load_split(cfg, split)}
        from buglens.onboard.summarize import load_summary_texts

        covered = sorted({insts[i] for i in sub if load_summary_texts(cfg, insts[i])})
        sub = [i for i in sub if insts[i] in covered]
        if sub:
            rows = summary_rows(cfg, {"S6": frames["S6"].loc[sub],
                                      "S6b": frames["S6b"].loc[sub]}, ["S6", "S6b"])
            md += ["## RQ4: onboarding summaries as a reranker feature (S6b vs S6)", "",
                   f"Subset: {len(sub)} instances from repos with package summaries "
                   f"({', '.join(covered)}).", "", md_table(rows, cols), ""]
    if "A1" in frames:
        md += ["## Ablation A1: hints appended to the query", "",
               md_table(summary_rows(cfg, frames, ["A1"] + (["S5"] if "S5" in frames else [])),
                         cols), ""]

    _plot_tokens(cfg, frames, full + partial, figures)
    _plot_per_repo(cfg, frames, full, split, figures)
    md += ["## Figures", "", "![Accuracy vs tokens](figures/acc_vs_tokens.png)", "",
           "![Per-repo Acc@5](figures/per_repo_acc5.png)", ""]
    for name, title in (("feature_importance.png", "LambdaRank feature importance"),
                        ("finetune_loss.png", "Fine-tuning loss")):
        if (figures / name).exists():
            md += [f"![{title}](figures/{name})", ""]
    ft = reports / "finetune_eval.json"
    if ft.exists():
        d = json.loads(ft.read_text())
        md += ["## Fine-tuning (RQ2) — validation on held-out repositories", "",
               f"{d['train_pairs']} train / {d['val_pairs']} val pairs (repo-disjoint).", "",
               "| metric | before | after |", "| --- | --- | --- |"]
        for k in sorted(d["after"]):
            if any(t in k for t in ("accuracy@1", "accuracy@10", "mrr@10")):
                md.append(f"| {k} | {d['before'].get(k, float('nan')):.3f} | "
                          f"{d['after'][k]:.3f} |")
        md.append("")
    text = "\n".join(md)
    (reports / "results.md").write_text(text, encoding="utf-8")
    write_meta(reports, cfg, filename="results_meta.json", systems=systems, split=split)
    summary("report", systems=",".join(systems), out=str(reports / "results.md"))
    return text


def _plot_tokens(cfg, frames, systems, figures) -> None:
    plt.figure(figsize=(6, 4))
    for s in systems:
        x = frames[s]["tokens"].mean()
        y = frames[s]["file_acc@5"].mean()
        plt.scatter([x], [y], s=40)
        plt.annotate(s, (x, y), textcoords="offset points", xytext=(5, 4))
    plt.xscale("symlog", linthresh=10)
    plt.xlabel("mean LLM tokens per issue (symlog)")
    plt.ylabel("file Acc@5")
    plt.title("Accuracy vs. cost")
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(figures / "acc_vs_tokens.png", dpi=150)
    plt.close()


def _plot_per_repo(cfg, frames, systems, split, figures) -> None:
    cheap = [s for s in systems if s not in ("S7", "S8")]
    llm = [s for s in systems if s in ("S7", "S8")]
    if not cheap:
        return
    best_cheap = max(cheap, key=lambda s: frames[s]["file_acc@5"].mean())
    picks = [best_cheap] + ([max(llm, key=lambda s: frames[s]["file_acc@5"].mean())]
                            if llm else [])
    repo_of = {i.instance_id: i.repo.split("/")[1] for i in load_split(cfg, split)}
    data = {}
    for s in picks:
        df = frames[s].copy()
        df["repo"] = [repo_of[i] for i in df.index]
        data[s] = df.groupby("repo")["file_acc@5"].mean()
    table = pd.DataFrame(data).sort_index()
    ax = table.plot.bar(figsize=(8, 4), width=0.8)
    ax.set_ylabel("file Acc@5")
    ax.set_title("Per-repository file Acc@5")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(figures / "per_repo_acc5.png", dpi=150)
    plt.close()


def error_dump(cfg: Config, system: str, n: int = 20, split: str = "test") -> str:
    """FR-E4: failures (gold file not in top-5) with an empty Category field to fill in."""
    results = {r.instance_id: r for r in load_run(cfg, system, split)}
    labels = load_labels(cfg, split)
    insts = {i.instance_id: i for i in load_split(cfg, split)}
    fails = sorted(i for i, r in results.items()
                   if not set(r.files[:5]) & set(labels[i].files))
    random.Random(cfg.seed).shuffle(fails)
    md = [f"# Error analysis: {system} ({split})", "",
          f"{len(fails)} of {len(results)} instances miss the gold file in the top 5. "
          f"Showing {min(n, len(fails))} (random, seed {cfg.seed}). Fill in `Category:` "
          "(e.g. vague issue, multi-file, test-only hint, wrong module, ranking).", ""]
    for iid in fails[:n]:
        r, lab, inst = results[iid], labels[iid], insts[iid]
        excerpt = inst.problem_statement.strip().replace("\n", " ")[:600]
        md += [f"## {iid}", "", f"**Issue (excerpt):** {excerpt}", "",
               f"**Gold files:** {', '.join(f'`{f}`' for f in lab.files)}  ",
               f"**Gold functions:** {', '.join(f'`{f}`' for f in lab.functions)}", "",
               "**Top-5 predictions:**", ""]
        for c in sorted(r.functions, key=lambda c: c.rank)[:5]:
            mark = " ✅" if c.chunk_id in lab.functions else ""
            md.append(f"{c.rank}. `{c.chunk_id}`{mark}")
        md += ["", "Category: ", ""]
    out = cfg.path("reports") / "error_analysis.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    summary("errors", system=system, failures=len(fails), shown=min(n, len(fails)),
            out=str(out))
    console.print()
    return str(out)
