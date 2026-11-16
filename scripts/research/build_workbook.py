"""Build the research workbook: raw data + Excel formulas + native charts.

Conventions: blue text on light-blue fill = data imported from experiment files (edit/replace
freely); black text = formulas (recalculate automatically); grey header rows; Arial throughout.
Run after collect.py and figures.py:  uv run python scripts/research/build_workbook.py
"""

from __future__ import annotations

import json

import pandas as pd
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L
from openpyxl.worksheet.table import Table, TableStyleInfo

from buglens.config import PROJECT_ROOT

DATA = PROJECT_ROOT / "reports" / "research" / "data"
OUT = PROJECT_ROOT / "reports" / "research" / "BugLens_Research_Analysis.xlsx"

FONT = "Arial"
F_DATA = Font(name=FONT, size=10, color="0000FF")
F_FORM = Font(name=FONT, size=10, color="000000")
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_TITLE = Font(name=FONT, size=14, bold=True, color="1F3864")
F_NOTE = Font(name=FONT, size=9, italic=True, color="595959")
F_BOLD = Font(name=FONT, size=10, bold=True)
FILL_HEAD = PatternFill("solid", fgColor="1F3864")
FILL_DATA = PatternFill("solid", fgColor="EAF1FB")
FILL_KPI = PatternFill("solid", fgColor="FFF2CC")
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(top=THIN, bottom=THIN, left=THIN, right=THIN)
PCT = "0.0%"
NUM3 = "0.000"

SYSTEMS = ["S1", "S2", "S3", "S4", "S5", "S6", "S6b", "S7", "S8", "A1"]
PIPE = {"S1": "BM25", "S2": "Dense (CodeRankEmbed)", "S3": "RRF(S1,S2)",
        "S4": "Dense (fine-tuned)", "S5": "RRF(S1,S4)", "S6": "S5 → LambdaRank",
        "S6b": "S6 + summary feature", "S7": "S5 → Gemini rerank",
        "S8": "S6 → Gemini rerank", "A1": "S5 + hints (ablation)"}
METRICS = ["file_acc@1", "file_acc@3", "file_acc@5", "file_mrr", "func_acc@5", "func_acc@10",
           "func_recall@10", "func_mrr"]

wb = Workbook()


# ------------------------------------------------------------------ helpers
def title(ws, text, note=None, row=1):
    ws.cell(row, 1, text).font = F_TITLE
    if note:
        ws.cell(row + 1, 1, note).font = F_NOTE
    return row + 3


def header(ws, row, col, names, widths=None):
    for j, n in enumerate(names):
        c = ws.cell(row, col + j, n)
        c.font, c.fill, c.border = F_HEAD, FILL_HEAD, BOX
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[row].height = 30
    if widths:
        for j, w in enumerate(widths):
            ws.column_dimensions[L(col + j)].width = w


def put(ws, row, col, value, fmt=None, data=False, bold=False):
    c = ws.cell(row, col, value)
    c.font = F_BOLD if bold else (F_DATA if data else F_FORM)
    if data:
        c.fill = FILL_DATA
    c.border = BOX
    if fmt:
        c.number_format = fmt
    return c


def df_block(ws, df, row, col, fmts=None, widths=None, table_name=None):
    header(ws, row, col, list(df.columns), widths)
    for i, rec in enumerate(df.itertuples(index=False), start=1):
        for j, v in enumerate(rec):
            v = None if (isinstance(v, float) and pd.isna(v)) else v
            put(ws, row + i, col + j, v, (fmts or {}).get(df.columns[j]), data=True)
    if table_name:
        ref = f"{L(col)}{row}:{L(col + len(df.columns) - 1)}{row + len(df)}"
        t = Table(displayName=table_name, ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleLight1", showRowStripes=True)
        ws.add_table(t)
    return row + len(df) + 1


def style_chart(ch, x_title, y_title, w=16, h=8):
    ch.width, ch.height = w, h
    ch.roundedCorners = False
    ch.varyColors = False  # one colour per series, not per bar/point
    ch.x_axis.title, ch.y_axis.title = x_title, y_title
    for t in (ch.x_axis.title, ch.y_axis.title):
        t.overlay = False  # keep axis titles outside the plot area
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    if ch.legend is not None:
        ch.legend.position = "b"
        ch.legend.overlay = False
    ch.x_axis.majorGridlines = None
    return ch


def note(ws, row, text, col=1):
    ws.cell(row, col, text).font = F_NOTE
    return row + 1


# ------------------------------------------------------------------ load data
pi = pd.read_csv(DATA / "per_instance_metrics.csv")
paired_py = pd.read_csv(DATA / "paired_comparisons.csv")
stats = json.loads((DATA / "figure_stats.json").read_text())
manifest = json.loads((DATA / "manifest.json").read_text())

# ================================================================== Read Me
ws = wb.active
ws.title = "Read Me"
r = title(ws, "BugLens — Research Analysis Workbook",
          f"Companion to the research report. Built {manifest['created'][:10]} from git commit "
          f"{manifest['git_commit'][:10]}.")
guide = [
    ("Dashboard", "Key results and charts on one page (all cells link to the sheets below)."),
    ("Summary", "Per-system means, standard deviation, standard error and 95% CI (formulas)."),
    ("Comparisons", "Paired differences between systems, 95% CI and McNemar exact test (formulas)."),
    ("Per_Repo", "Accuracy within each of the 12 test repositories (formulas)."),
    ("Iterations", "Repeated runs: LambdaRank seeds, leave-one-repo-out folds, repeated LLM runs."),
    ("Sensitivity", "Effect of the RRF constant k and of candidate depth."),
    ("FineTune", "Training loss per step and validation before/after fine-tuning."),
    ("Timing", "Repeated latency measurements, LLM call cost, pipeline stage durations."),
    ("Bootstrap", "1,000 bootstrap resamples of four key differences + histogram counts."),
    ("Errors", "Errors and incidents during the project; categories of 20 failures."),
    ("Reproducibility", "Code version, package versions, dataset, configuration, commands."),
    ("Data_Instances", "Raw per-issue results for every system (test: 300 issues; dev: 23)."),
    ("Paired_Wide", "Same results side by side per issue, used by Comparisons."),
]
header(ws, r, 1, ["Sheet", "What it contains"], [22, 100])
for i, (a, b) in enumerate(guide, start=1):
    put(ws, r + i, 1, a, bold=True)
    put(ws, r + i, 2, b)
r += len(guide) + 2
ws.cell(r, 1, "Legend").font = F_BOLD
put(ws, r + 1, 1, "1234", data=True)
ws.cell(r + 1, 2, "Blue text, light-blue fill = data imported from experiment files (you may edit).").font = F_FORM
put(ws, r + 2, 1, "=1+1")
ws.cell(r + 2, 2, "Black text = Excel formula (recalculates automatically).").font = F_FORM
c = put(ws, r + 3, 1, "0.867")
c.fill = FILL_KPI
ws.cell(r + 3, 2, "Yellow fill = headline value on the Dashboard.").font = F_FORM
r += 5
for line in [
    "Metrics are shares of issues (0–1, shown as %): Acc@k = the gold file/function is in the top k; "
    "MRR = mean of 1 / rank of the first gold item.",
    "95% CI (normal approximation) = mean ± 1.96 × standard error. Bootstrap CIs (1,000 resamples) "
    "from the Python analysis are shown next to them for comparison.",
    "McNemar exact p = 2 × BINOMDIST(min(b, c), b + c, 0.5, TRUE) where b, c = issues solved by only one "
    "of the two systems.",
    "Statistics are intentionally simple: means, CIs, paired differences and one paired test.",
]:
    r = note(ws, r, line)

# ================================================================== Data_Instances
wd = wb.create_sheet("Data_Instances")
cols = ["system", "split", "instance_id", "repo", *METRICS, "tokens", "seconds"]
d = pi[cols].copy()
fm = {m: NUM3 for m in METRICS} | {"seconds": "0.000"}
end = df_block(wd, d, 1, 1, fm, [8, 7, 34, 26] + [11] * len(METRICS) + [9, 9], "Instances")
N_ROWS = len(d) + 1
RNG = {c: f"Data_Instances!${L(i + 1)}$2:${L(i + 1)}${N_ROWS}" for i, c in enumerate(cols)}
wd.freeze_panes = "A2"

# ================================================================== Summary
ws = wb.create_sheet("Summary")
r = title(ws, "Per-system results on SWE-bench Lite (test, 300 issues)",
          "All numbers are formulas over Data_Instances. CI = mean ± 1.96 × SE (normal approximation).")
show = ["file_acc@1", "file_acc@5", "func_acc@10", "func_mrr"]
heads = ["System", "Pipeline", "n"]
for m in show:
    heads += [f"{m} mean", f"{m} SD", f"{m} SE", f"{m} CI low", f"{m} CI high"]
heads += ["Mean LLM tokens", "Mean seconds", "file_acc@5 bootstrap CI low (Python)",
          "file_acc@5 bootstrap CI high (Python)"]
header(ws, r, 1, heads, [8, 22, 6] + [9] * (5 * len(show)) + [11, 10, 13, 13])
boot = {(x["system"], x["metric"]): x for x in stats["main_ci"]}
SUM_ROW = {}
for i, s in enumerate(SYSTEMS, start=1):
    rr = r + i
    SUM_ROW[s] = rr
    put(ws, rr, 1, s, bold=True)
    put(ws, rr, 2, PIPE[s])
    crit = f'{RNG["system"]},$A{rr},{RNG["split"]},"test"'
    put(ws, rr, 3, f"=COUNTIFS({crit})")
    for k, m in enumerate(show):
        c0 = 4 + 5 * k
        mean, sd, se = L(c0), L(c0 + 1), L(c0 + 2)
        put(ws, rr, c0, f"=AVERAGEIFS({RNG[m]},{crit})", PCT)
        sumsq = (f'SUMPRODUCT(({RNG["system"]}=$A{rr})*({RNG["split"]}="test")*{RNG[m]}^2)')
        put(ws, rr, c0 + 1, f"=SQRT(MAX(0,({sumsq}-$C{rr}*{mean}{rr}^2)/($C{rr}-1)))", NUM3)
        put(ws, rr, c0 + 2, f"={sd}{rr}/SQRT($C{rr})", NUM3)
        put(ws, rr, c0 + 3, f"={mean}{rr}-1.96*{se}{rr}", PCT)
        put(ws, rr, c0 + 4, f"={mean}{rr}+1.96*{se}{rr}", PCT)
    ct = 4 + 5 * len(show)
    put(ws, rr, ct, f"=AVERAGEIFS({RNG['tokens']},{crit})", "#,##0")
    put(ws, rr, ct + 1, f"=AVERAGEIFS({RNG['seconds']},{crit})", "0.000")
    b = boot.get((s, "file_acc@5"))
    put(ws, rr, ct + 2, b["low"] if b else None, PCT, data=True)
    put(ws, rr, ct + 3, b["high"] if b else None, PCT, data=True)
SUM_FIRST, SUM_LAST = r + 1, r + len(SYSTEMS)
ws.freeze_panes = ws.cell(r + 1, 3)
r = SUM_LAST + 2
r = note(ws, r, "A1 uses maintainer hints in the query (information not available to the other "
                "systems) and is reported only as an ablation.")
ch = BarChart()
ch.type = "col"
ch.grouping = "clustered"
for m in ["file_acc@1", "file_acc@5", "func_acc@10"]:
    col = 4 + 5 * show.index(m)
    s_ref = Reference(ws, min_col=col, min_row=SUM_FIRST - 1, max_row=SUM_LAST - 1)
    ch.add_data(s_ref, titles_from_data=True)
ch.set_categories(Reference(ws, min_col=1, min_row=SUM_FIRST, max_row=SUM_LAST - 1))
style_chart(ch, "System", "Share of 300 issues", 22, 9)
ch.y_axis.number_format = "0%"
ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 1
ws.add_chart(ch, f"B{r + 1}")

# ================================================================== Paired_Wide
pw = wb.create_sheet("Paired_Wide")
need = [("file_acc@1", ["S6", "S7", "S8"]), ("file_acc@5", ["S1", "S2", "S3", "S4", "S5"]),
        ("func_acc@10", ["S2", "S3", "S5", "S6", "S6b", "S7"])]
test = pi[pi.split == "test"]
wide = test.pivot(index="instance_id", columns="system")
cols_w, data_w = ["instance_id"], {"instance_id": wide.index}
for m, ss in need:
    for s in ss:
        cols_w.append(f"{m} | {s}")
        data_w[f"{m} | {s}"] = wide[(m, s)].values
dw = pd.DataFrame(data_w)[cols_w]
df_block(pw, dw, 1, 1, None, [34] + [12] * (len(cols_w) - 1))
PW = {c: f"Paired_Wide!${L(i + 1)}$2:${L(i + 1)}${len(dw) + 1}" for i, c in enumerate(cols_w)}
pw.freeze_panes = "B2"

# ================================================================== Comparisons
ws = wb.create_sheet("Comparisons")
r = title(ws, "Paired comparisons (same 300 issues for both systems)",
          "Difference = A − B in percentage points. b = issues only A solves, c = only B solves. "
          "Formulas use Paired_Wide.")
heads = ["RQ", "A", "B", "Metric", "n", "Mean A", "Mean B", "Difference (pp)", "SD of diff",
         "SE of diff", "95% CI low (pp)", "95% CI high (pp)", "Relative change", "b (A only)",
         "c (B only)", "McNemar exact p", "Bootstrap CI low (Python, pp)",
         "Bootstrap CI high (Python, pp)", "Reading"]
header(ws, r, 1, heads, [6, 6, 6, 12, 6, 9, 9, 11, 9, 9, 11, 11, 10, 9, 9, 10, 13, 13, 36])
COMP = [("RQ1", "S2", "S1", "file_acc@5"), ("RQ1", "S3", "S2", "file_acc@5"),
        ("RQ1", "S3", "S2", "func_acc@10"), ("RQ2", "S4", "S2", "file_acc@5"),
        ("RQ2", "S5", "S3", "file_acc@5"), ("RQ3", "S6", "S5", "func_acc@10"),
        ("RQ3", "S6", "S7", "func_acc@10"), ("RQ3", "S7", "S6", "file_acc@1"),
        ("RQ3", "S8", "S6", "file_acc@1"), ("RQ4", "S6b", "S6", "func_acc@10")]
COMP_FIRST = r + 1
for i, (rq, a, b, m) in enumerate(COMP, start=1):
    rr = r + i
    A, B = PW[f"{m} | {a}"], PW[f"{m} | {b}"]
    put(ws, rr, 1, rq, bold=True)
    put(ws, rr, 2, a)
    put(ws, rr, 3, b)
    put(ws, rr, 4, m)
    put(ws, rr, 5, f"=COUNT({A})")
    put(ws, rr, 6, f"=AVERAGE({A})", PCT)
    put(ws, rr, 7, f"=AVERAGE({B})", PCT)
    put(ws, rr, 8, f"=(F{rr}-G{rr})*100", "+0.0;-0.0;0.0")
    put(ws, rr, 9, f"=SQRT(MAX(0,(SUMPRODUCT(({A}-{B})^2)-E{rr}*(H{rr}/100)^2)/(E{rr}-1)))", NUM3)
    put(ws, rr, 10, f"=I{rr}/SQRT(E{rr})", "0.0000")
    put(ws, rr, 11, f"=H{rr}-1.96*J{rr}*100", "+0.0;-0.0;0.0")
    put(ws, rr, 12, f"=H{rr}+1.96*J{rr}*100", "+0.0;-0.0;0.0")
    put(ws, rr, 13, f"=IF(G{rr}=0,\"\",(F{rr}-G{rr})/G{rr})", "+0.0%;-0.0%;0.0%")
    put(ws, rr, 14, f"=SUMPRODUCT(({A}=1)*({B}=0))")
    put(ws, rr, 15, f"=SUMPRODUCT(({A}=0)*({B}=1))")
    put(ws, rr, 16, f"=IF(N{rr}+O{rr}=0,1,MIN(1,2*BINOMDIST(MIN(N{rr},O{rr}),N{rr}+O{rr},0.5,TRUE)))",
        "0.000")
    py = paired_py[(paired_py.comparison == f"{a} − {b}") & (paired_py.metric == m)]
    put(ws, rr, 17, float(py.low.iloc[0]) * 100 if len(py) else None, "+0.0;-0.0", data=True)
    put(ws, rr, 18, float(py.high.iloc[0]) * 100 if len(py) else None, "+0.0;-0.0", data=True)
    put(ws, rr, 19, f'=IF(AND(K{rr}<0,L{rr}>0),"CI includes 0: difference not established",'
                    f'IF(H{rr}>0,"A higher under tested conditions","B higher under tested conditions"))')
COMP_LAST = r + len(COMP)
r = COMP_LAST + 2
r = note(ws, r, "Note: an LLM reranker only reorders the top 10, so it cannot change Acc@10; "
                "compare LLM systems on Acc@1/Acc@5/MRR.")
r = note(ws, r, "Ten comparisons are made; at a 0.05 level about one 'significant' result could "
                "arise by chance, so borderline p-values (0.01–0.05) should be read cautiously.")
ch = BarChart()
ch.type = "bar"
ch.add_data(Reference(ws, min_col=8, min_row=COMP_FIRST - 1, max_row=COMP_LAST), titles_from_data=True)
ws.cell(COMP_FIRST - 1, 20, "Label").font = F_HEAD
ws.cell(COMP_FIRST - 1, 20).fill = FILL_HEAD
for rr in range(COMP_FIRST, COMP_LAST + 1):
    put(ws, rr, 20, f'=B{rr}&" − "&C{rr}&" ("&D{rr}&")"')
ch.set_categories(Reference(ws, min_col=20, min_row=COMP_FIRST, max_row=COMP_LAST))
style_chart(ch, "Comparison", "Difference A − B (percentage points)", 22, 9)
ch.legend = None
ch.x_axis.tickLblPos = "low"
for s in ch.series:
    s.invertIfNegative = False
ws.add_chart(ch, f"B{r + 1}")

# ================================================================== Per_Repo
ws = wb.create_sheet("Per_Repo")
r = title(ws, "File Acc@5 within each test repository",
          "Formulas over Data_Instances. Small repositories (n < 10) give unstable percentages.")
repos = sorted(test.repo.unique())
sys_rep = ["S1", "S5", "S6", "S8"]
header(ws, r, 1, ["Repository", "n"] + [f"{s} File Acc@5" for s in sys_rep] + ["S6 − S1 (pp)"],
       [28, 6, 13, 13, 13, 13, 12])
for i, repo in enumerate(repos, start=1):
    rr = r + i
    put(ws, rr, 1, repo, bold=True)
    put(ws, rr, 2, f'=COUNTIFS({RNG["repo"]},$A{rr},{RNG["system"]},"S1",{RNG["split"]},"test")')
    for k, s in enumerate(sys_rep):
        put(ws, rr, 3 + k, f'=AVERAGEIFS({RNG["file_acc@5"]},{RNG["repo"]},$A{rr},'
                           f'{RNG["system"]},"{s}",{RNG["split"]},"test")', PCT)
    put(ws, rr, 7, f"=(E{rr}-C{rr})*100", "+0.0;-0.0;0.0")
REP_FIRST, REP_LAST = r + 1, r + len(repos)
put(ws, REP_LAST + 1, 1, "All (weighted)", bold=True)
put(ws, REP_LAST + 1, 2, f"=SUM(B{REP_FIRST}:B{REP_LAST})")
for k in range(len(sys_rep)):
    col = L(3 + k)
    put(ws, REP_LAST + 1, 3 + k, f"=SUMPRODUCT($B{REP_FIRST}:$B{REP_LAST},{col}{REP_FIRST}:{col}{REP_LAST})/$B{REP_LAST + 1}", PCT)
ch = BarChart()
ch.type = "bar"
ch.add_data(Reference(ws, min_col=3, max_col=6, min_row=REP_FIRST - 1, max_row=REP_LAST), titles_from_data=True)
ch.set_categories(Reference(ws, min_col=1, min_row=REP_FIRST, max_row=REP_LAST))
style_chart(ch, "Repository", "File Acc@5", 18, 12)
ch.y_axis.number_format = "0%"
ws.add_chart(ch, f"I{r}")

# ================================================================== Iterations
ws = wb.create_sheet("Iterations")
r = title(ws, "Repeated runs and iterations",
          "A. LambdaRank with random subsampling, 5 seeds   B. Leave-one-repo-out folds   "
          "C. Gemini reranker, 3 repeated runs on 50 issues")
ws.cell(r, 1, "A. LambdaRank seeds (stochastic variant: 80% row and feature subsampling)").font = F_BOLD
seeds = pd.read_csv(DATA / "ltr_seed_iterations.csv")[["seed", "file_acc@1", "file_acc@5", "func_acc@10", "func_mrr"]]
r0 = r + 1
r = df_block(ws, seeds, r0, 1, {c: PCT for c in seeds.columns[1:]}, [14, 12, 12, 12, 12])
for lab, fn in (("Mean", "AVERAGE"), ("SD", "STDEV"), ("Min", "MIN"), ("Max", "MAX")):
    put(ws, r, 1, lab, bold=True)
    for j in range(2, 6):
        put(ws, r, j, f"={fn}({L(j)}{r0 + 1}:{L(j)}{r0 + len(seeds)})", PCT if fn != "STDEV" else "0.0000")
    r += 1
put(ws, r, 1, "Range (pp)", bold=True)
for j in range(2, 6):
    put(ws, r, j, f"=({L(j)}{r - 1}-{L(j)}{r - 2})*100", "0.0")
r += 1
put(ws, r, 1, "Deterministic S6", bold=True)
smap = {"file_acc@1": 4, "file_acc@5": 9, "func_acc@10": 14, "func_mrr": 19}
for j, m in enumerate(["file_acc@1", "file_acc@5", "func_acc@10", "func_mrr"], start=2):
    put(ws, r, j, f"=Summary!{L(smap[m])}{SUM_ROW['S6']}", PCT)
r += 2
ws.cell(r, 1, "B. Leave-one-repo-out folds: Function Acc@10 of S5 and S6 on each held-out repository").font = F_BOLD
r += 1
header(ws, r, 1, ["Held-out repository", "n", "S5", "S6", "S6 − S5 (pp)", "S6 better?"])
FOLD_FIRST = r + 1
for i, repo in enumerate(repos, start=1):
    rr = r + i
    put(ws, rr, 1, repo, bold=True)
    put(ws, rr, 2, f'=COUNTIFS({RNG["repo"]},$A{rr},{RNG["system"]},"S5",{RNG["split"]},"test")')
    for j, s in ((3, "S5"), (4, "S6")):
        put(ws, rr, j, f'=AVERAGEIFS({RNG["func_acc@10"]},{RNG["repo"]},$A{rr},{RNG["system"]},"{s}",{RNG["split"]},"test")', PCT)
    put(ws, rr, 5, f"=(D{rr}-C{rr})*100", "+0.0;-0.0;0.0")
    put(ws, rr, 6, f'=IF(E{rr}>0,"higher",IF(E{rr}<0,"lower","equal"))')
FOLD_LAST = r + len(repos)
r = FOLD_LAST + 1
put(ws, r, 1, "Folds where S6 is higher / equal / lower", bold=True)
put(ws, r, 2, f'=COUNTIF(F{FOLD_FIRST}:F{FOLD_LAST},"higher")&" / "&COUNTIF(F{FOLD_FIRST}:F{FOLD_LAST},"equal")&" / "&COUNTIF(F{FOLD_FIRST}:F{FOLD_LAST},"lower")')
r += 2
ws.cell(r, 1, "C. Gemini reranker (S7 prompt) repeated 3 times on 50 random issues, temperature 0").font = F_BOLD
r += 1
rep = pd.read_csv(DATA / "llm_repeats.csv")
top1 = rep.pivot(index="instance_id", columns="repeat", values="top1_chunk")
full = rep.pivot(index="instance_id", columns="repeat", values="ranking")
gold1 = rep.pivot(index="instance_id", columns="repeat", values="gold_file_top1")
gold5 = rep.pivot(index="instance_id", columns="repeat", values="gold_func_in_top5")
nrep = top1.shape[1]
tab = pd.DataFrame({"instance_id": top1.index})
for k in range(nrep):
    tab[f"top-1 run {k + 1}"] = top1[k].values
for k in range(nrep):
    tab[f"file@1 run {k + 1}"] = gold1[k].values
for k in range(nrep):
    tab[f"func@5 run {k + 1}"] = gold5[k].values
tab["ranking identical all runs"] = (full.nunique(axis=1) == 1).astype(int).values
hdr = r
r = df_block(ws, tab, hdr, 1, None, [34] + [30] * nrep + [9] * (2 * nrep) + [12])
put(ws, hdr, 1 + len(tab.columns), "Same top-1 in all runs").font = F_HEAD
ws.cell(hdr, 1 + len(tab.columns)).fill = FILL_HEAD
agree_col = 1 + len(tab.columns)
for i in range(1, len(tab) + 1):
    cells = [f"{L(2 + k)}{hdr + i}" for k in range(nrep)]
    cond = ",".join(f"{cells[0]}={c}" for c in cells[1:])
    put(ws, hdr + i, agree_col, f"=IF(AND({cond}),1,0)")
first, last = hdr + 1, hdr + len(tab)
r += 1
put(ws, r, 1, "Summary (formulas)", bold=True)
r += 1
for k in range(nrep):
    put(ws, r, 1, f"Run {k + 1}: File Acc@1 / Function Acc@5", bold=True)
    c1, c2 = L(2 + nrep + k), L(2 + 2 * nrep + k)
    put(ws, r, 2, f"=AVERAGE({c1}{first}:{c1}{last})", PCT)
    put(ws, r, 3, f"=AVERAGE({c2}{first}:{c2}{last})", PCT)
    r += 1
put(ws, r, 1, "Share of issues with same top-1 in all runs", bold=True)
put(ws, r, 2, f"=AVERAGE({L(agree_col)}{first}:{L(agree_col)}{last})", PCT)
r += 1
put(ws, r, 1, "Share with identical full top-10 ranking", bold=True)
rc = L(1 + 3 * nrep + 1)
put(ws, r, 2, f"=AVERAGE({rc}{first}:{rc}{last})", PCT)

# ================================================================== Sensitivity
ws = wb.create_sheet("Sensitivity")
r = title(ws, "Sensitivity analyses (S5 configuration, 300 test issues)",
          "Values computed in Python from cached retrieval scores (no re-training).")
ws.cell(r, 1, "A. RRF constant k (60 = configured value)").font = F_BOLD
rk = pd.read_csv(DATA / "rrf_k_sensitivity.csv")[["rrf_k", "file_acc@1", "file_acc@5", "func_acc@10", "func_mrr"]]
a0 = r + 1
r = df_block(ws, rk, a0, 1, {c: PCT for c in rk.columns[1:]}, [10, 12, 12, 12, 12])
put(ws, r, 1, "Max − min (pp)", bold=True)
for j in range(2, 6):
    put(ws, r, j, f"=(MAX({L(j)}{a0 + 1}:{L(j)}{a0 + len(rk)})-MIN({L(j)}{a0 + 1}:{L(j)}{a0 + len(rk)}))*100", "0.0")
lc = LineChart()
for j in range(2, 5):
    lc.add_data(Reference(ws, min_col=j, min_row=a0, max_row=a0 + len(rk)), titles_from_data=True)
lc.set_categories(Reference(ws, min_col=1, min_row=a0 + 1, max_row=a0 + len(rk)))
style_chart(lc, "RRF constant k", "Share of 300 issues", 14, 7.5)
lc.y_axis.number_format = "0%"
ws.add_chart(lc, f"H{a0}")
r += 3
ws.cell(r, 1, "B. Candidate depth: is the gold item within the top-k at all? (ceiling for any reranker)").font = F_BOLD
dp = pd.read_csv(DATA / "candidate_depth.csv")
b0 = r + 1
r = df_block(ws, dp, b0, 1, {"gold_function_in_top": PCT, "gold_file_in_top_files": PCT}, [10, 18, 18])
lc = LineChart()
for j in (2, 3):
    lc.add_data(Reference(ws, min_col=j, min_row=b0, max_row=b0 + len(dp)), titles_from_data=True)
lc.set_categories(Reference(ws, min_col=1, min_row=b0 + 1, max_row=b0 + len(dp)))
style_chart(lc, "Candidate depth k", "Share of 300 issues", 14, 7.5)
lc.y_axis.number_format = "0%"
ws.add_chart(lc, f"H{b0 + 2}")

# ================================================================== FineTune
ws = wb.create_sheet("FineTune")
r = title(ws, "Fine-tuning the code encoder (CodeRankEmbed, 2,571 training triples)",
          "Loss per optimiser step; validation on 429 pairs from 2 repositories not used in training.")
st = pd.read_csv(DATA / "finetune_steps.csv")
s0 = r
header(ws, s0, 1, ["Step", "Loss", "5-step moving average"], [8, 10, 18])
for i, rec in enumerate(st.itertuples(index=False), start=1):
    rr = s0 + i
    put(ws, rr, 1, int(rec.step), data=True)
    put(ws, rr, 2, float(rec.loss), "0.000", data=True)
    put(ws, rr, 3, f"=AVERAGE(B{max(s0 + 1, rr - 4)}:B{rr})", "0.000")
s_last = s0 + len(st)
put(ws, s_last + 1, 1, "First 5 vs last 5 steps (mean loss)", bold=True)
put(ws, s_last + 1, 2, f"=AVERAGE(B{s0 + 1}:B{s0 + 5})", "0.000")
put(ws, s_last + 1, 3, f"=AVERAGE(B{s_last - 4}:B{s_last})", "0.000")
lc = LineChart()
lc.add_data(Reference(ws, min_col=2, max_col=3, min_row=s0, max_row=s_last), titles_from_data=True)
lc.set_categories(Reference(ws, min_col=1, min_row=s0 + 1, max_row=s_last))
style_chart(lc, "Training step", "Contrastive loss", 16, 8)
ws.add_chart(lc, "F4")
v = pd.read_csv(DATA / "finetune_validation.csv")
v0 = s_last + 4
header(ws, v0, 1, ["Validation metric", "Before", "After", "Change (pp)"])
for i, rec in enumerate(v.itertuples(index=False), start=1):
    rr = v0 + i
    put(ws, rr, 1, rec.metric, bold=True)
    put(ws, rr, 2, float(rec.before), PCT, data=True)
    put(ws, rr, 3, float(rec.after), PCT, data=True)
    put(ws, rr, 4, f"=(C{rr}-B{rr})*100", "+0.0;-0.0;0.0")

# ================================================================== Timing
ws = wb.create_sheet("Timing")
r = title(ws, "Execution time and cost",
          "A. Repeated latency (50 issues × 3 repeats)   B. Gemini calls   C. Pipeline stage durations")
lat = pd.read_csv(DATA / "latency_repeats.csv")
stages = [("bm25_scoring", "BM25 scoring (ms)"), ("query_encoding_gpu", "Query encoding, GPU (ms)"),
          ("faiss_search", "FAISS search (ms)")]
header(ws, r, 1, ["Statistic"] + [lab for _, lab in stages], [30, 18, 22, 18])
stat_rows = [("n", "COUNT"), ("Mean", "AVERAGE"), ("Median", "MEDIAN"), ("SD", "STDEV"),
             ("90th percentile", None), ("Min", "MIN"), ("Max", "MAX")]
raw0 = r + len(stat_rows) + 3
for j, (sname, _) in enumerate(stages):
    vals = lat[lat.stage == sname].milliseconds.tolist()
    col = 2 + j
    ws.cell(raw0, col, f"raw: {sname}").font = F_HEAD
    ws.cell(raw0, col).fill = FILL_HEAD
    for i, val in enumerate(vals, start=1):
        put(ws, raw0 + i, col, float(val), "0.00", data=True)
    rng = f"{L(col)}{raw0 + 1}:{L(col)}{raw0 + len(vals)}"
    for i, (lab, fn) in enumerate(stat_rows, start=1):
        if j == 0:
            put(ws, r + i, 1, lab, bold=True)
        f = f"=PERCENTILE({rng},0.9)" if fn is None else f"={fn}({rng})"
        put(ws, r + i, col, f, "0" if lab == "n" else "0.00")
ws.cell(raw0 - 1, 2, "Raw measurements (one per issue × repeat)").font = F_NOTE
llm = pd.read_csv(DATA / "llm_calls.csv")
c0 = 7
ws.cell(3, c0, "B. Gemini API calls (all cached responses)").font = F_BOLD
header(ws, 4, c0, ["Statistic", "Tokens in", "Tokens out", "Seconds"], [24, 12, 12, 10])
lraw = 15
for j, colname in enumerate(["tokens_in", "tokens_out", "seconds"]):
    col = c0 + 1 + j
    ws.cell(lraw, col, f"raw: {colname}").font = F_HEAD
    ws.cell(lraw, col).fill = FILL_HEAD
    for i, val in enumerate(llm[colname].tolist(), start=1):
        put(ws, lraw + i, col, float(val), "0" if "tokens" in colname else "0.00", data=True)
    rng = f"{L(col)}{lraw + 1}:{L(col)}{lraw + len(llm)}"
    for i, (lab, fn) in enumerate([("Calls", "COUNT"), ("Mean", "AVERAGE"), ("Median", "MEDIAN"),
                                   ("90th percentile", None), ("Total", "SUM")], start=1):
        if j == 0:
            put(ws, 4 + i, c0, lab, bold=True)
        f = f"=PERCENTILE({rng},0.9)" if fn is None else f"={fn}({rng})"
        put(ws, 4 + i, col, f, "#,##0" if "tokens" in colname or lab == "Calls" else "0.00")
sd = pd.read_csv(DATA / "stage_durations.csv")
sd = sd[sd.minutes >= 0.5].drop_duplicates("step", keep="last")[["log", "step", "start", "minutes", "exit_code"]]
c1 = 12
ws.cell(3, c1, "C. Pipeline stages (from data/*.log timestamps, ≥ 0.5 min)").font = F_BOLD
df_block(ws, sd, 4, c1, {"minutes": "0.0"}, [16, 22, 20, 9, 9])
put(ws, 5 + len(sd), c1 + 2, "Total minutes", bold=True)
put(ws, 5 + len(sd), c1 + 3, f"=SUM({L(c1 + 3)}5:{L(c1 + 3)}{4 + len(sd)})", "0.0")
bc = BarChart()
bc.type = "bar"
bc.add_data(Reference(ws, min_col=c1 + 3, min_row=4, max_row=4 + len(sd)), titles_from_data=True)
bc.set_categories(Reference(ws, min_col=c1 + 1, min_row=5, max_row=4 + len(sd)))
style_chart(bc, "Pipeline step", "Minutes", 16, 10)
bc.legend = None
ws.add_chart(bc, f"{L(c1 + 6)}4")

# ================================================================== Bootstrap
ws = wb.create_sheet("Bootstrap")
r = title(ws, "Bootstrap resampling of four key differences (1,000 resamples, seed 42)",
          "Each row = one resample of the 300 issues with replacement; value = difference in means "
          "(A − B). Summary and histogram counts are formulas.")
bs = pd.read_csv(DATA / "bootstrap_samples.csv", index_col=0)
raw0 = r + 12
header(ws, raw0, 1, list(bs.columns), [24] * len(bs.columns))
for i, row in enumerate(bs.itertuples(index=False), start=1):
    for j, val in enumerate(row, start=1):
        put(ws, raw0 + i, j, float(val), "0.0000", data=True)
last = raw0 + len(bs)
header(ws, r, 1, [" "] + [c for c in bs.columns], [24] + [24] * len(bs.columns))
for i, (lab, f) in enumerate([("Mean difference (pp)", "=AVERAGE({R})*100"),
                              ("2.5th percentile (pp)", "=PERCENTILE({R},0.025)*100"),
                              ("97.5th percentile (pp)", "=PERCENTILE({R},0.975)*100"),
                              ("Share of resamples > 0", '=COUNTIF({R},">0")/COUNT({R})')], start=1):
    put(ws, r + i, 1, lab, bold=True)
    for j in range(len(bs.columns)):
        R = f"{L(1 + j)}{raw0 + 1}:{L(1 + j)}{last}"
        put(ws, r + i, 2 + j, f.format(R=R), PCT if "Share" in lab else "+0.0;-0.0;0.0")
h0 = r + 6
header(ws, h0, len(bs.columns) + 3, ["Bin upper edge (pp)", f"Count: {bs.columns[1]}"], [16, 26])
edges = list(range(-4, 13))
col_data = f"{L(2)}{raw0 + 1}:{L(2)}{last}"
for i, e in enumerate(edges, start=1):
    put(ws, h0 + i, len(bs.columns) + 3, e, data=True)
    lo = "-1000" if i == 1 else f"{L(len(bs.columns) + 3)}{h0 + i - 1}"
    put(ws, h0 + i, len(bs.columns) + 4,
        f'=COUNTIFS({col_data},">"&{lo}/100,{col_data},"<="&{L(len(bs.columns) + 3)}{h0 + i}/100)')
bc = BarChart()
bc.add_data(Reference(ws, min_col=len(bs.columns) + 4, min_row=h0, max_row=h0 + len(edges)), titles_from_data=True)
bc.set_categories(Reference(ws, min_col=len(bs.columns) + 3, min_row=h0 + 1, max_row=h0 + len(edges)))
style_chart(bc, "Difference (pp, bin upper edge)", "Resamples", 14, 7.5)
bc.gapWidth = 10
bc.legend = None
ws.add_chart(bc, f"{L(len(bs.columns) + 6)}{h0}")

# ================================================================== Errors
ws = wb.create_sheet("Errors")
r = title(ws, "Errors, incidents and failure analysis")
ws.cell(r, 1, "A. Incidents during the project (from logs and notes)").font = F_BOLD
ev = pd.read_csv(DATA / "events_and_errors.csv")
r = df_block(ws, ev, r + 1, 1, None, [11, 18, 48, 40, 40]) + 1
for col in "CDE":
    for row in ws[f"{col}1:{col}{r}"]:
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
ws.cell(r, 1, "B. Misses per system (test): issues where the gold item is NOT found").font = F_BOLD
r += 1
header(ws, r, 1, ["System", "n", "File misses @5", "File miss rate @5", "Function misses @10", "Function miss rate @10"])
for i, s in enumerate(SYSTEMS[:-1], start=1):
    rr = r + i
    put(ws, rr, 1, s, bold=True)
    crit = f'{RNG["system"]},$A{rr},{RNG["split"]},"test"'
    put(ws, rr, 2, f"=COUNTIFS({crit})")
    put(ws, rr, 3, f'=B{rr}-SUMIFS({RNG["file_acc@5"]},{crit})')
    put(ws, rr, 4, f"=C{rr}/B{rr}", PCT)
    put(ws, rr, 5, f'=B{rr}-SUMIFS({RNG["func_acc@10"]},{crit})')
    put(ws, rr, 6, f"=E{rr}/B{rr}", PCT)
r += len(SYSTEMS) + 1
ws.cell(r, 1, "C. Categories of 20 randomly sampled S6 failures (manual reading of issue vs gold patch)").font = F_BOLD
cat = pd.read_csv(DATA / "error_categories.csv")
c0 = r + 1
r = df_block(ws, cat, c0, 1, None, [44, 8])
put(ws, r, 1, "Total", bold=True)
put(ws, r, 2, f"=SUM(B{c0 + 1}:B{c0 + len(cat)})")
put(ws, r + 1, 1, "'Symptom ≠ fix site' (first two rows) share", bold=True)
put(ws, r + 1, 2, f"=(B{c0 + 1}+B{c0 + 2})/B{r}", PCT)

# ================================================================== Reproducibility
ws = wb.create_sheet("Reproducibility")
r = title(ws, "Reproducibility record", "Everything needed to rerun and verify the experiments.")
rows = [("Git commit", manifest["git_commit"]), ("Collected", manifest["created"]),
        ("Python", manifest["python"]), ("OS", manifest["os"]), ("Dataset", manifest["dataset"]),
        ("LLM model", manifest["llm_model"]), ("Random seed", manifest["seed"]),
        ("Repository", "https://github.com/Icoder05/buglens")]
rows += [(f"package: {k}", v) for k, v in manifest["packages"].items()]
rows += [("Rebuild all numbers", "make reproduce   (≈ 9 minutes from cache, 0 API calls)"),
         ("Rebuild this workbook", "uv run python scripts/research/collect.py && "
                                   "uv run python scripts/research/figures.py && "
                                   "uv run python scripts/research/build_workbook.py"),
         ("Configuration", "configs/default.yaml, configs/experiments.yaml (snapshot in data/manifest.json)"),
         ("Logs", "data/pipeline.log, data/llm_pipeline.log, runs/*.meta.json")]
header(ws, r, 1, ["Item", "Value"], [28, 110])
for i, (k, v) in enumerate(rows, start=1):
    put(ws, r + i, 1, k, bold=True)
    put(ws, r + i, 2, str(v), data=True)

# ================================================================== Dashboard (first tab)
ws = wb.create_sheet("Dashboard", 1)
ws.sheet_view.showGridLines = False
title(ws, "BugLens — results dashboard",
      "Every value links to Summary / Comparisons / Iterations. Change the data and the dashboard updates.")
tiles = [
    ("Best zero-token system", "S6 LambdaRank", None),
    ("S6 File Acc@5", f"=Summary!I{SUM_ROW['S6']}", PCT),
    ("S6 Function Acc@10", f"=Summary!N{SUM_ROW['S6']}", PCT),
    ("S8 File Acc@1 (LLM)", f"=Summary!D{SUM_ROW['S8']}", PCT),
    ("S6 File Acc@1", f"=Summary!D{SUM_ROW['S6']}", PCT),
    ("S8 mean tokens / issue", f"=Summary!X{SUM_ROW['S8']}", "#,##0"),
    ("Same LLM top-1 across 3 runs", None, PCT),
    ("Seed range, Func Acc@10 (pp)", None, "0.0"),
]
for k, (lab, f, fmt) in enumerate(tiles):
    row, col = 4 + (k // 4) * 3, 1 + (k % 4) * 3
    a = ws.cell(row, col, lab)
    a.font = Font(name=FONT, size=9, color="595959")
    ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
    v = ws.cell(row + 1, col, f)
    v.font = Font(name=FONT, size=16, bold=True, color="1F3864")
    v.fill = FILL_KPI
    if fmt:
        v.number_format = fmt
    ws.merge_cells(start_row=row + 1, start_column=col, end_row=row + 1, end_column=col + 1)
for c in range(1, 13):
    ws.column_dimensions[L(c)].width = 12
it = wb["Iterations"]
for row in it.iter_rows(min_col=1, max_col=2):
    if row[0].value == "Share of issues with same top-1 in all runs":
        ws.cell(8, 7).value = f"=Iterations!B{row[0].row}"
    if row[0].value == "Range (pp)":
        ws.cell(8, 10).value = f"=Iterations!D{row[0].row}"
sm = wb["Summary"]
ch = BarChart()
ch.type = "col"
for m_col in (4, 9, 14):
    ch.add_data(Reference(sm, min_col=m_col, min_row=SUM_FIRST - 1, max_row=SUM_LAST - 1), titles_from_data=True)
ch.set_categories(Reference(sm, min_col=1, min_row=SUM_FIRST, max_row=SUM_LAST - 1))
style_chart(ch, "System", "Share of 300 issues", 18, 8)
ch.y_axis.number_format = "0%"
ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 1
ws.add_chart(ch, "A14")
a1 = BarChart()
a1.type = "col"
a1.add_data(Reference(sm, min_col=4, min_row=SUM_FIRST - 1, max_row=SUM_LAST - 1), titles_from_data=True)
a1.set_categories(Reference(sm, min_col=1, min_row=SUM_FIRST, max_row=SUM_LAST - 1))
style_chart(a1, "System (S7, S8 use the LLM reranker)", "File Acc@1", 12, 8)
a1.legend = None
a1.y_axis.number_format = "0%"
a1.y_axis.scaling.min, a1.y_axis.scaling.max = 0, 1
ws.add_chart(a1, "K14")
cp = wb["Comparisons"]
bc = BarChart()
bc.type = "bar"
bc.add_data(Reference(cp, min_col=8, min_row=COMP_FIRST - 1, max_row=COMP_LAST), titles_from_data=True)
bc.set_categories(Reference(cp, min_col=20, min_row=COMP_FIRST, max_row=COMP_LAST))
style_chart(bc, "Comparison", "Difference (pp)", 18, 9)
bc.legend = None
bc.x_axis.tickLblPos = "low"  # category labels at the left edge, not on the zero line
for s in bc.series:
    s.invertIfNegative = False
ws.add_chart(bc, "A31")
ft = wb["FineTune"]
lc = LineChart()
lc.add_data(Reference(ft, min_col=3, min_row=4, max_row=4 + len(st)), titles_from_data=True)
lc.set_categories(Reference(ft, min_col=1, min_row=5, max_row=4 + len(st)))
style_chart(lc, "Training step", "Loss (5-step average)", 12, 9)
lc.legend = None
ws.add_chart(lc, "K31")

for name in ("Read Me", "Dashboard"):
    wb[name].sheet_properties.tabColor = "1F3864"
wb.active = 1  # open on the Dashboard
wb.save(OUT)
print("saved", OUT)
