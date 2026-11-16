"""Gather every number quoted in the report into one JSON file (no hand-typed results).

Run after figures.py:  uv run python scripts/research/numbers.py
"""

import json

import pandas as pd

from buglens.config import PROJECT_ROOT
from buglens.eval.stats import bootstrap_ci

R = PROJECT_ROOT / "reports"
DATA = R / "research" / "data"
pi = pd.read_csv(DATA / "per_instance_metrics.csv")
test = pi[pi.split == "test"]
fs = json.loads((DATA / "figure_stats.json").read_text())
N = {}

# main table
rows = []
for s in ["S1", "S2", "S3", "S4", "S5", "S6", "S6b", "S7", "S8", "A1"]:
    g = test[test.system == s]
    row = {"system": s, "n": len(g), "tokens": float(g.tokens.mean()), "seconds": float(g.seconds.mean())}
    for m in ["file_acc@1", "file_acc@5", "func_acc@5", "func_acc@10", "func_mrr"]:
        mean, lo, hi = bootstrap_ci(g[m])
        row[m] = {"mean": mean, "low": lo, "high": hi}
    rows.append(row)
N["main"] = rows
N["paired"] = pd.read_csv(DATA / "paired_comparisons.csv").to_dict("records")

# dev
dev = pi[pi.split == "dev"]
N["dev"] = [{"system": s, "n": int((dev.system == s).sum()),
             "file_acc@5": float(dev[dev.system == s]["file_acc@5"].mean()),
             "func_acc@10": float(dev[dev.system == s]["func_acc@10"].mean())}
            for s in ["S1", "S2", "S3", "S4", "S5", "S6"]]

# per repo
n_repo = test[test.system == "S1"].groupby("repo").size()
N["repos"] = [{"repo": r, "n": int(n),
               **{s: float(test[(test.system == s) & (test.repo == r)]["file_acc@5"].mean())
                  for s in ["S1", "S5", "S6", "S8"]}} for r, n in n_repo.items()]
folds = pd.read_csv(DATA / "loro_folds.csv")
N["folds"] = {"higher": int((folds.diff_pp > 0).sum()), "equal": int((folds.diff_pp == 0).sum()),
              "lower": int((folds.diff_pp < 0).sum()), "rows": folds.to_dict("records")}

# iterations / sensitivity
seeds = pd.read_csv(DATA / "ltr_seed_iterations.csv")
N["seeds"] = {m: {"mean": float(seeds[m].mean()), "sd": float(seeds[m].std()),
                  "min": float(seeds[m].min()), "max": float(seeds[m].max())}
              for m in ["file_acc@1", "file_acc@5", "func_acc@10", "func_mrr"]}
N["rrf"] = pd.read_csv(DATA / "rrf_k_sensitivity.csv").to_dict("records")
N["depth"] = pd.read_csv(DATA / "candidate_depth.csv").to_dict("records")
N["llm_repeats"] = fs.get("llm_repeats")
N["dev_test"] = fs.get("dev_test")

# fine-tuning
ft = json.loads((R / "finetune_eval.json").read_text())
st = pd.read_csv(DATA / "finetune_steps.csv")
N["finetune"] = {"train_pairs": ft["train_pairs"], "val_pairs": ft["val_pairs"],
                 "steps": int(st.step.max()), "loss_first5": float(st.loss.head(5).mean()),
                 "loss_last5": float(st.loss.tail(5).mean()),
                 "val": pd.read_csv(DATA / "finetune_validation.csv").to_dict("records")}

# timing / cost
lat = pd.read_csv(DATA / "latency_repeats.csv")
N["latency"] = {s: {"median": float(g.milliseconds.median()), "p90": float(g.milliseconds.quantile(.9)),
                    "mean": float(g.milliseconds.mean()), "n": int(len(g))}
                for s, g in lat.groupby("stage")}
llm = pd.read_csv(DATA / "llm_calls.csv")
N["llm_calls"] = {"n": int(len(llm)), "tokens_in_mean": float(llm.tokens_in.mean()),
                  "tokens_out_mean": float(llm.tokens_out.mean()),
                  "seconds_median": float(llm.seconds.median()),
                  "seconds_p90": float(llm.seconds.quantile(.9)),
                  "tokens_total": int(llm.tokens_in.sum() + llm.tokens_out.sum()),
                  "valid_json": float(llm.valid_json.mean())}
sd = pd.read_csv(DATA / "stage_durations.csv")
N["stages"] = sd.sort_values("minutes", ascending=False).head(10).to_dict("records")
N["resources"] = pd.read_csv(DATA / "resources.csv").to_dict("records")

# onboarding
ratings = pd.read_csv(R / "summary_ratings.csv", keep_default_na=False)
N["ratings"] = ratings.rating.value_counts().to_dict() | {"n": int(len(ratings))}
oe = (R / "onboarding_eval.md").read_text(encoding="utf-8")
N["onboarding_eval_md"] = oe
fi = pd.read_csv(DATA / "feature_importance.csv", index_col=0)
N["feature_importance_top"] = fi.sort_values("mean_share", ascending=False).head(6).round(3).to_dict("index")
def clean(x):
    """NaN is not valid JSON (JavaScript cannot parse it): replace with null."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, list):
        return [clean(v) for v in x]
    if isinstance(x, float) and x != x:
        return None
    return x


(DATA / "report_numbers.json").write_text(json.dumps(clean(N), indent=1, default=float),
                                          encoding="utf-8")
print("ok", len(json.dumps(N)))
