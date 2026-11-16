// Build the BugLens research report (.docx). Numbers come from reports/research/data/*.json/csv.
// Run: node scripts/research/build_report.js   (after collect.py, figures.py, report_numbers.py)
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType,
  AlignmentType, HeadingLevel, BorderStyle, ShadingType, LevelFormat, PageNumber, Header, Footer,
  TableOfContents, PageBreak, VerticalAlign,
} = require("docx");

const ROOT = path.resolve(__dirname, "..", "..");
const RES = path.join(ROOT, "reports", "research");
const FIG = path.join(RES, "figures");
const N = JSON.parse(fs.readFileSync(path.join(RES, "data", "report_numbers.json"), "utf8"));
const OUT = path.join(RES, "BugLens_Research_Report.docx");

const FONT = "Arial";
const TEXT_W = 9070; // A4 width 11906 - 2 x 1418 (2.5 cm) margins, in DXA
const pct = (x, d = 1) => (100 * x).toFixed(d) + "%";
const pp = (x, d = 1) => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(d);
const sys = (s) => N.main.find((r) => r.system === s);

// ------------------------------------------------------------------ text helpers
function runs(text, base = {}) {
  // **bold**, *italic*
  const out = [];
  const re = /(\*\*[^*]+\*\*|\*[^*]+\*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), italics: true, ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (text, opts = {}) => new Paragraph({ children: runs(text), spacing: { after: 120, line: 276 }, alignment: AlignmentType.JUSTIFIED, ...opts });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)], pageBreakBefore: true });
const H1n = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const B = (t, level = 0) => new Paragraph({ numbering: { reference: "bullets", level }, children: runs(t), spacing: { after: 60, line: 264 } });
const NUM = (t) => new Paragraph({ numbering: { reference: "numbers", level: 0 }, children: runs(t), spacing: { after: 60, line: 264 } });

// ------------------------------------------------------------------ tables (three-line style)
const NONE = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const RULE = (sz) => ({ style: BorderStyle.SINGLE, size: sz, color: "000000" });
let tableNo = 0, figNo = 0;

function caption(kind, text) {
  const n = kind === "Table" ? ++tableNo : ++figNo;
  return new Paragraph({
    keepNext: true,
    spacing: { before: kind === "Table" ? 160 : 60, after: kind === "Table" ? 60 : 120 },
    children: [new TextRun({ text: `${kind} ${n}. `, bold: true, size: 18, font: FONT }),
      ...runs(text, { size: 18, font: FONT })],
  });
}

function table(cap, headers, rows, widths, opts = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const scale = TEXT_W / total;
  const w = widths.map((x) => Math.round(x * scale));
  w[w.length - 1] += TEXT_W - w.reduce((a, b) => a + b, 0);
  // text columns left-aligned; columns listed in opts.center (numbers) centred
  const center = new Set(opts.center || []);
  const align = headers.map((_, i) => (center.has(i) ? AlignmentType.CENTER : AlignmentType.LEFT));
  const cell = (text, i, isHead, isLast) => new TableCell({
    width: { size: w[i], type: WidthType.DXA },
    verticalAlign: VerticalAlign.CENTER,
    shading: isHead ? { fill: "EDEDED", type: ShadingType.CLEAR, color: "auto" } : undefined,
    borders: { top: isHead ? RULE(12) : NONE, bottom: isHead ? RULE(6) : (isLast ? RULE(12) : NONE), left: NONE, right: NONE },
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ alignment: isHead ? AlignmentType.CENTER : align[i], keepNext: !isLast,
      children: runs(String(text), { size: 17, font: FONT, bold: isHead || undefined }) })],
  });
  const t = new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: w,
    borders: { top: NONE, bottom: NONE, left: NONE, right: NONE, insideHorizontal: NONE, insideVertical: NONE },
    rows: [new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, i, true, false)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((v, i) => cell(v, i, false, ri === rows.length - 1)) }))],
  });
  const out = [caption("Table", cap), t];
  if (opts.note) out.push(new Paragraph({ spacing: { before: 60, after: 160 }, children: runs(opts.note, { size: 16, italics: true, color: "404040" }) }));
  else out.push(new Paragraph({ spacing: { after: 120 }, children: [] }));
  return out;
}

// ------------------------------------------------------------------ figures with explanation box
function pngSize(file) {
  const b = fs.readFileSync(file);
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function figure(file, capText, ex, widthFrac = 1.0) {
  const f = path.join(FIG, file);
  const { w, h } = pngSize(f);
  const px = Math.round(605 * widthFrac); // 6.3 in at 96 dpi
  const img = new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(f), transformation: { width: px, height: Math.round(px * h / w) },
      altText: { title: capText.slice(0, 60), description: capText, name: file } })] });
  const lab = [["What was measured", ex.measured], ["What it shows", ex.shows], ["Why it may occur", ex.why],
    ["What it means", ex.means], ["Limitations", ex.limits]];
  const cw = [1900, TEXT_W - 1900];
  const box = new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: cw,
    borders: { top: RULE(4), bottom: RULE(4), left: NONE, right: NONE, insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: "D9D9D9" }, insideVertical: NONE },
    rows: lab.map(([k, v], ri) => new TableRow({ cantSplit: true, children: [
      new TableCell({ width: { size: cw[0], type: WidthType.DXA }, shading: { fill: "F3F6FA", type: ShadingType.CLEAR, color: "auto" },
        margins: { top: 40, bottom: 40, left: 90, right: 90 },
        children: [new Paragraph({ keepNext: ri < lab.length - 1, children: [new TextRun({ text: k, bold: true, size: 17, font: FONT })] })] }),
      new TableCell({ width: { size: cw[1], type: WidthType.DXA }, margins: { top: 40, bottom: 40, left: 90, right: 90 },
        children: [new Paragraph({ keepNext: ri < lab.length - 1, children: runs(v, { size: 17, font: FONT }) })] })] })),
  });
  // keep image + caption + explanation box on one page
  const cap = caption("Figure", capText);
  return [img, cap, box, new Paragraph({ spacing: { after: 160 }, children: [] })];
}

const callout = (title, lines) => new Table({
  width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: [TEXT_W],
  borders: { top: RULE(4), bottom: RULE(4), left: { style: BorderStyle.SINGLE, size: 24, color: "1F3864" }, right: NONE, insideHorizontal: NONE, insideVertical: NONE },
  rows: [new TableRow({ children: [new TableCell({ width: { size: TEXT_W, type: WidthType.DXA },
    shading: { fill: "F3F6FA", type: ShadingType.CLEAR, color: "auto" }, margins: { top: 80, bottom: 80, left: 160, right: 120 },
    children: [new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: title, bold: true, size: 19, font: FONT, color: "1F3864" })] }),
      ...lines.map((l) => new Paragraph({ spacing: { after: 40 }, children: runs(l, { size: 18, font: FONT }) }))] })] })],
});
const gap = () => new Paragraph({ spacing: { after: 120 }, children: [] });

// ------------------------------------------------------------------ numbers used in text
const S1 = sys("S1"), S2 = sys("S2"), S3 = sys("S3"), S4 = sys("S4"), S5 = sys("S5"),
  S6 = sys("S6"), S6b = sys("S6b"), S7 = sys("S7"), S8 = sys("S8"), A1 = sys("A1");
const cmp = (a, b, m) => N.paired.find((r) => r.comparison === `${a} − ${b}` && r.metric === m);
const ci = (r) => `${pp(100 * r.diff)} pp [${pp(100 * r.low)}, ${pp(100 * r.high)}]`;
const pv = (p) => (p < 0.001 ? "p < 0.001" : `p = ${p.toFixed(3)}`);
const rep = N.llm_repeats;
const seeds = N.seeds;
const depth = Object.fromEntries(N.depth.map((d) => [d.depth, d]));
const rrf = Object.fromEntries(N.rrf.map((d) => [d.rrf_k, d]));
const fvl = Object.fromEntries(N.finetune.val.map((d) => [d.metric, d]));
const lat = N.latency;

// ================================================================== CONTENT
const C = [];

// ---------- Title page
C.push(new Paragraph({ spacing: { before: 2400, after: 200 }, alignment: AlignmentType.LEFT,
  children: [new TextRun({ text: "BugLens", font: FONT, size: 56, bold: true, color: "1F3864" })] }));
C.push(new Paragraph({ spacing: { after: 400 }, children: [new TextRun({
  text: "An experimental evaluation of retrieval, learning-to-rank and LLM reranking for bug localization on SWE-bench Lite, with a static-analysis onboarding component",
  font: FONT, size: 30, color: "404040" })] }));
C.push(new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: "1F3864", space: 1 } }, children: [] }));
C.push(new Paragraph({ spacing: { before: 300, after: 80 }, children: [new TextRun({ text: "Research report", font: FONT, size: 24, bold: true })] }));
for (const l of ["Version 1.0 — 16 November 2026",
  "Code and data: https://github.com/Icoder05/buglens",
  "Companion workbook: BugLens_Research_Analysis.xlsx (all calculations and charts)"])
  C.push(new Paragraph({ spacing: { after: 60 }, children: [new TextRun({ text: l, font: FONT, size: 20 })] }));
C.push(new Paragraph({ spacing: { before: 1600 }, children: runs(
  "*Scope statement.* This report evaluates how well BugLens **ranks** the files and functions that a fix will change, on a fixed public benchmark, under the tested conditions. It does not evaluate automatic bug fixing, developer productivity, or performance on private codebases.",
  { size: 19, color: "404040" }) }));

// ---------- Abstract + TOC
C.push(H1("Abstract"));
C.push(P(`**Problem.** When a GitHub issue is reported, a developer must first find which code to change. This report measures how accurately several automated ranking pipelines identify those locations on SWE-bench Lite [1], a public benchmark of 300 real issues from 12 Python repositories, and how these pipelines compare in cost.`));
C.push(P(`**Method.** Nine systems were built on one shared index of syntax-tree code chunks: lexical retrieval (BM25), a dense code encoder before and after contrastive fine-tuning on 18 disjoint repositories, rank fusion, a LambdaRank reranker with 21 features, and a Gemini 3.5 Flash-Lite reranker of the top 10. Hypotheses, metrics and comparison pairs were fixed in configuration files before the test runs; uncertainty is reported with bootstrap 95% confidence intervals and exact McNemar tests on paired outcomes.`));
C.push(P(`**Results.** Under the tested conditions, the best system without an LLM (S6) placed a correct file in its top five for ${pct(S6["file_acc@5"].mean)} of issues [95% CI ${pct(S6["file_acc@5"].low)}–${pct(S6["file_acc@5"].high)}] and a correct function in its top ten for ${pct(S6["func_acc@10"].mean)}. Fine-tuning the encoder improved file Acc@5 by ${ci(cmp("S4", "S2", "file_acc@5"))}. The LLM reranker did not improve top-10 recall, but it placed the correct file first far more often (file Acc@1 ${pct(S6["file_acc@1"].mean)} → ${pct(S8["file_acc@1"].mean)}), at about ${Math.round(S8.tokens).toLocaleString("en")} tokens per issue. Repeating the LLM step on 50 issues showed that its first-ranked answer changed between runs for ${pct(1 - rep.top1_identical_all, 0)} of them, so single-run LLM figures carry run-to-run variation of roughly ±2 percentage points.`));
C.push(P(`**Conclusion.** The measured results support three of the four hypotheses (fine-tuning, learning to rank, LLM reranking at rank 1), support the first only partly (hybrid retrieval beats BM25 but not strong dense retrieval), and do not support the fourth (onboarding summaries as a ranking feature). The findings are limited to one benchmark that is dominated by two repositories, and to one LLM version.`));
C.push(new Paragraph({ pageBreakBefore: true, spacing: { after: 200 },
  children: [new TextRun({ text: "Contents", font: FONT, size: 30, bold: true, color: "1F3864" })] }));
C.push(new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }));

// ---------- 1 Introduction
C.push(H1("1. Introduction and problem statement"));
C.push(H2("1.1 Problem"));
C.push(P("Fixing a reported bug starts with *localization*: deciding which files and functions must change. In large repositories this is slow for people who do not know the code. Information-retrieval methods have been used for this since at least BugLocator [3], and SWE-bench [1] made it possible to measure localization on real GitHub issues with the exact fixing patches as ground truth."));
C.push(P("Recent systems often use large language models (LLMs) or agents for localization [2], [6], [7], [9]. These are capable but costly and not fully deterministic. This project asks how far cheaper, reproducible components (lexical and dense retrieval, fusion, a learned reranker) can go, where an LLM adds value, and what that value costs."));
C.push(H2("1.2 Objectives"));
for (const o of [
  "**O1.** Build a reproducible localization pipeline on SWE-bench Lite with file- and function-level ranking.",
  "**O2.** Compare retrieval, fine-tuning, learning-to-rank and LLM reranking under one controlled experimental design.",
  "**O3.** Quantify uncertainty: confidence intervals, paired tests, repeated runs and sensitivity analyses.",
  "**O4.** Record cost and resource use (tokens, latency, GPU memory, wall-clock time) alongside accuracy.",
  "**O5.** Evaluate an onboarding component (architecture diagrams and cited summaries) and test whether its summaries help localization."]) C.push(B(o));
C.push(H2("1.3 Research questions"));
C.push(...table("Research questions and the systems that answer them.",
  ["ID", "Research question", "Compared systems"],
  [["RQ1", "Does hybrid retrieval (BM25 + dense) rank fix locations better than either alone?", "S1, S2, S3"],
    ["RQ2", "Does contrastive fine-tuning on other repositories improve dense retrieval on unseen repositories?", "S2 vs S4; S3 vs S5"],
    ["RQ3", "Does a learned reranker (LambdaRank) close the gap to an LLM reranker, and at what cost?", "S5, S6, S7, S8"],
    ["RQ4", "Do package summaries written for onboarding improve ranking when added as a feature?", "S6 vs S6b"]],
  [8, 70, 22]));
C.push(H2("1.4 Positioning and claims"));
C.push(P("To keep the report's claims within what was measured, Table 2 separates claims this report does not make from the positioning that the evidence supports."));
C.push(...table("Claim positioning used throughout the report.",
  ["Avoided claim", "Grounded positioning", "Reason"],
  [["An automatic bug-fixing system", "A ranking component that suggests where a fix is likely", "Generated patches (M10) were not executed against tests"],
    ["Highly accurate on any codebase", "Measured accuracy on 300 SWE-bench Lite issues from 12 repositories", "No evaluation on private or non-Python code"],
    ["The LLM version is better", "Better first-ranked answer under the tested conditions, at ~5–6k tokens per issue", "Top-10 recall did not improve; outputs vary between runs"],
    ["Speeds up developer onboarding", "Produces faithful diagrams and cited summaries", "No user study was performed"]],
  [30, 40, 30]));

// ---------- 2 Literature review
C.push(H1("2. Literature review"));
C.push(P("The review covers five strands that the project builds on. Reported results from other papers are given as context only: they use different metrics, label definitions, subsets and LLMs, so they are not directly comparable with the numbers in Section 9."));
C.push(H2("2.1 Information-retrieval bug localization"));
C.push(P("Early work treated a bug report as a query and source files as documents. BugLocator [3] ranked files with a revised vector space model that accounts for file length and similar past bugs. Ye, Bunescu and Liu [4] combined many such signals (lexical similarity, API descriptions, bug-fixing and change history) with a learning-to-rank model and reported better file rankings than earlier IR methods on Java projects. Two lessons carry over: lexical overlap is a strong baseline, and combining signals with a learned ranker helps. Their limitation is that they were evaluated on file-level labels in a few Java projects, often with history features that SWE-bench does not provide."));
C.push(H2("2.2 Benchmarks: SWE-bench and SWE-bench Lite"));
C.push(P("SWE-bench [1] pairs real GitHub issues with the repository at the commit before the fix and the gold patch, which allows file- and function-level labels to be derived from the patch. SWE-bench Lite is a 300-issue subset of mostly self-contained fixes. Xia et al. [2] manually reviewed Lite and reported that some issues contain the exact patch in the description (4.3%), some lack critical information (10.0%), and some include misleading solutions (5.0%). This matters for interpreting any Lite result, including this report's: a part of the measured accuracy, and of the failures, reflects issue quality rather than method quality."));
C.push(H2("2.3 Dense code retrieval and contrastive training"));
C.push(P("Bi-encoders map queries and documents into one vector space, trained with contrastive objectives that pull matching pairs together and push in-batch negatives apart [14]. Because larger batches give more negatives, gradient caching [15] allows large effective batches on small GPUs. CoRNStack [5] built large, filtered contrastive datasets for code and released CodeRankEmbed, a 137M-parameter code embedding model that this project uses as its dense encoder; it also reports function-localization experiments on SWE-bench Lite following the Agentless setup."));
C.push(H2("2.4 LLM-based and agentic localization"));
C.push(P("Agentless [2] localizes hierarchically (files, then classes and functions) with an LLM and a simple retrieval component, and then repairs. LocAgent [7] parses repositories into dependency graphs and lets an LLM agent navigate them. SweRank [6] combines a code-ranking retriever with an LLM reranker and reports state-of-the-art localization on SWE-bench Lite. BLAgent [9] restricts an LLM reranker to a small retrieval-filtered candidate set and reports more than 78% top-1 file accuracy on Lite with open-source models. A common pattern is *retrieve, then rerank a short list with an LLM*, which is the structure of S7 and S8 in this project."));
C.push(H2("2.5 Code summaries for localization"));
C.push(P("Meta-RAG [8] summarizes large codebases and uses the summaries in a retrieval-augmented localization pipeline, reporting 84.67% file-level and 53.0% function-level accuracy on SWE-bench Lite. This is the closest prior idea to RQ4. The difference here is that the summaries are written for human onboarding, are restricted to cited, validated sentences, and are used only as one reranker feature."));
C.push(H2("2.6 Rank fusion and learning to rank"));
C.push(P("BM25 [10] remains a strong lexical ranking function. Reciprocal Rank Fusion [11] combines rankings without score normalization and is a robust default for hybrid search. LambdaRank and LambdaMART [12], usually implemented with gradient-boosted trees [13], optimize ranking metrics directly and are well suited to combining heterogeneous features."));
C.push(...table("Selected related work (results as reported in the cited papers; not directly comparable).",
  ["Work", "Approach", "Benchmark", "Reported result (context only)"],
  [["BugLocator [3]", "Revised vector space model + similar bugs", "Java projects", "Better than earlier IR baselines"],
    ["Ye et al. [4]", "Learning to rank with domain features", "Java projects", "Better than two IR baselines"],
    ["Agentless [2]", "Hierarchical LLM localization, then repair", "SWE-bench Lite", "Repair rate 27–32% (version-dependent)"],
    ["LocAgent [7]", "Graph-guided LLM agent", "SWE-bench Lite", "High file-level accuracy (configuration-dependent)"],
    ["SweRank [6]", "Code-ranking retriever + LLM reranker", "SWE-bench Lite", "State-of-the-art localization (paper)"],
    ["Meta-RAG [8]", "Code summaries for RAG localization", "SWE-bench Lite", "84.67% file, 53.0% function"],
    ["BLAgent [9]", "LLM reranking of a filtered set", "SWE-bench Lite", ">78% file Acc@1 (open-source LLMs)"]],
  [17, 35, 18, 30], { note: "Metrics, label definitions and LLMs differ across papers; the numbers are context, not a ranking." }));
C.push(H2("2.7 Gaps and opportunities"));
for (const g of [
  "**Cost is rarely reported next to accuracy.** Many LLM-based results do not state tokens per issue or variability between runs. → Objective O4 and the repeated-run experiment.",
  "**Uncertainty is rarely quantified.** Single point estimates on 300 issues hide intervals of roughly ±5 percentage points. → Objective O3.",
  "**Cheap learned rerankers are under-explored on SWE-bench.** Classic learning to rank [4] is rarely compared with LLM reranking on the same candidates. → RQ3.",
  "**Human-oriented summaries are not tested as machine features.** → RQ4."]) C.push(B(g));

// ---------- 3 Methodology
C.push(H1("3. Methodology"));
C.push(P("All systems share one index per repository commit. Each Python file at the issue's base commit is parsed into syntax-tree chunks (one per function, method and class, plus one for remaining module-level code). Gold labels are derived from the patch: each removed line, or insertion point, is mapped to the innermost chunk containing it. Figure 1 shows how the systems are composed."));
C.push(...figure("fig01_method_overview.png", "Composition of the evaluated systems. Grey inputs are static-analysis features; the orange step is the only one that calls an LLM.", {
  measured: "Not a measurement: a structural diagram of the pipeline.",
  shows: "Which components each system uses. S1 and S2/S4 are single retrievers, S3/S5 fuse two rankings, S6/S6b rerank the fused top 50, and S7/S8 send the top 10 to an LLM.",
  why: "Each later system adds one component to an earlier one, so differences between neighbouring systems isolate the effect of that component.",
  means: "Comparisons such as S6 vs S5 measure the reranker alone, and S8 vs S6 measures the LLM step alone.",
  limits: "Components are not fully independent: for example, S6 uses S5's candidates, so S6 cannot recover gold items that S5 did not retrieve (see Section 7.4).",
}, 0.6));
C.push(...table("Evaluated systems.",
  ["System", "Pipeline", "Trained on", "LLM"],
  [["S1", "BM25 over code-aware tokens", "—", "No"], ["S2", "CodeRankEmbed (off-the-shelf) + exact vector search", "Public pre-training", "No"],
    ["S3", "Reciprocal Rank Fusion of S1 and S2 (k = 60)", "—", "No"], ["S4", "CodeRankEmbed fine-tuned contrastively", "2,571 triples, 16 repos", "No"],
    ["S5", "Reciprocal Rank Fusion of S1 and S4", "—", "No"], ["S6", "LambdaRank on S5 top 50, 21 features", "Other test repos (leave-one-repo-out)", "No"],
    ["S6b", "S6 + similarity to onboarding package summaries", "As S6", "Summaries only"], ["S7", "Gemini 3.5 Flash-Lite reranks S5 top 10", "—", "Yes"],
    ["S8", "Gemini 3.5 Flash-Lite reranks S6 top 10", "—", "Yes"], ["A1", "S5 with maintainer hints added to the query (ablation)", "—", "No"]],
  [9, 50, 28, 13], { center: [3] }));

// ---------- 4 DoE
C.push(H1("4. Design of experiments"));
C.push(P("The experiment was designed before the test runs: research questions, systems, metrics, the random seed and the list of paired comparisons were written into configuration files (configs/experiments.yaml) and the project requirements document. Two comparisons were added afterwards (S4 vs S2 and S8 vs S6); they are reported and marked as added."));
C.push(H2("4.1 Hypotheses"));
C.push(...table("Hypotheses (H1: expected effect; H0: no difference). Tested with paired comparisons on the same 300 issues.",
  ["", "Alternative hypothesis (H1)", "Primary metric", "Comparison"],
  [["H1", "Fusing BM25 with dense retrieval ranks fix locations better than either alone", "File Acc@5, Function Acc@10", "S3 vs S1, S3 vs S2"],
    ["H2", "Fine-tuning on disjoint repositories improves dense retrieval on unseen repositories", "File Acc@5", "S4 vs S2; S5 vs S3"],
    ["H3", "A learned reranker improves on its input ranking, and an LLM reranker improves the top of the list", "Function Acc@10; File Acc@1", "S6 vs S5; S7/S8 vs S6"],
    ["H4", "Adding onboarding summaries as a feature improves the learned reranker", "Function Acc@10", "S6b vs S6"]],
  [6, 50, 22, 22]));
C.push(H2("4.2 Variables"));
C.push(...table("Variables in the experiment.",
  ["Type", "Variable", "Values / how it is handled"],
  [["Independent", "Retrieval method", "BM25, dense, fused"], ["Independent", "Encoder training", "Off-the-shelf vs fine-tuned"],
    ["Independent", "Reranker", "None, LambdaRank, LambdaRank + summaries, LLM"], ["Dependent", "Ranking quality", "File Acc@1/3/5, MRR; Function Acc@5/10, Recall@10, MRR"],
    ["Dependent", "Cost", "LLM tokens per issue, seconds per issue, GPU memory, wall-clock time"],
    ["Controlled", "Data", "Same 300 issues and base commits for every system"], ["Controlled", "Randomness", "Seed 42 for sampling, training and bootstrap"],
    ["Controlled", "Software", "Pinned package versions (uv.lock); LLM temperature 0"], ["Controlled", "Hardware", "One machine: GTX 1660 SUPER 6 GB, 6-core CPU"],
    ["Confounder (noted)", "Repository mix", "django (114) and sympy (77) are 64% of issues"],
    ["Confounder (noted)", "LLM non-determinism", "Measured by repeated runs (Section 7.3)"]],
  [20, 25, 55]));
C.push(H2("4.3 Datasets"));
C.push(...table("Datasets.",
  ["Dataset", "Size", "Repositories", "Use"],
  [["SWE-bench Lite test", "300 issues", "12 (django 114, sympy 77, others 3–23)", "All reported results"],
    ["SWE-bench Lite dev", "23 issues", "6 other repositories", "Second dataset, sanity check"],
    ["Training triples (from SWE-bench train)", "2,571", "16 (disjoint from test and dev)", "Encoder fine-tuning"],
    ["Validation triples", "429", "2 (meson, numpy), held out", "Fine-tuning validation"]],
  [30, 14, 34, 22], { center: [1], note: "Disjointness of training and evaluation repositories is asserted in code and unit-tested." }));
C.push(H2("4.4 Baselines and metrics"));
C.push(P("BM25 (S1) is the lexical baseline and the off-the-shelf encoder (S2) is the dense baseline. All metrics are computed per issue and averaged, so each is the share of the 300 issues that meet a condition."));
C.push(...table("Evaluation metrics.",
  ["Metric", "Definition", "Interpretation"],
  [["File Acc@k", "1 if any gold file is among the top k ranked files", "Would a developer find a correct file in the first k?"],
    ["Function Acc@k", "1 if any gold function chunk is among the top k chunks", "Same, at function level"],
    ["Function Recall@10", "Share of gold function chunks found in the top 10", "Coverage for multi-function fixes"],
    ["MRR", "Mean of 1 / rank of the first gold item (0 if absent)", "Rewards putting the answer first"],
    ["Tokens / issue", "LLM input + output tokens (from API usage metadata)", "Direct cost driver of LLM systems"]],
  [20, 45, 35]));
C.push(H2("4.5 Protocol"));
for (const s of ["Each system is run once on all 300 issues with fixed seeds; outputs are stored per issue (runs/*.jsonl).",
  "The learned reranker is evaluated with leave-one-repo-out cross-validation: trained on 11 repositories, tested on the 12th.",
  "Hyperparameters were fixed in advance (not tuned on test data).",
  "Repeated runs and sensitivity analyses (Section 7) are added to estimate variability that a single run cannot show."]) C.push(NUM(s));

// ---------- 5 Statistical validity
C.push(H1("5. Statistical validity"));
C.push(H2("5.1 Sample size and precision"));
C.push(P("With 300 issues, the 95% confidence interval of an accuracy near 50% has a half-width of about ±5.7 percentage points (1.96 × √(0.25/300)); near 85% it is about ±4.0 points. Differences between systems smaller than about 3 points are therefore hard to establish with this sample, even with a paired design."));
C.push(H2("5.2 Paired design"));
C.push(P("Every system is evaluated on the same issues, so comparisons are paired. Paired comparisons are more sensitive than comparing two separate intervals, because issue difficulty affects both systems in the same way. Two paired methods are used: a bootstrap confidence interval of the difference [16] and the exact McNemar test [17], which uses only the issues that one system solves and the other does not."));
C.push(H2("5.3 Multiple comparisons"));
C.push(P("Ten paired comparisons are reported. At a 0.05 level, about one result could appear significant by chance alone, so p-values between 0.01 and 0.05 are treated as weaker evidence. No correction method is applied, to keep the analysis simple; instead, both the interval and the counts of discordant issues are reported."));
C.push(H2("5.4 Data quality"));
for (const s of ["Labels come from patches. A function counts as gold if the patch touches it; some patches also touch incidental code, which inflates the gold set for a few issues.",
  "All 300 test issues produced at least one gold function (0 unmappable). Three labels were checked by hand against their patches and matched.",
  "SWE-bench Lite contains issues with missing or misleading information [2]; these affect every system equally but cap achievable accuracy."]) C.push(B(s));
C.push(H2("5.5 Threats to validity"));
C.push(...table("Threats to validity and how they were handled.",
  ["Threat", "Type", "Mitigation / status"],
  [["Two repositories dominate the test set", "External", "Per-repository results reported (Section 9.4)"],
    ["Pre-training contamination (models may have seen these repositories)", "Internal", "Not controllable; stated as a limitation"],
    ["LLM output varies between runs", "Reliability", "Measured with 3 repeated runs on 50 issues"],
    ["Free-tier LLM model may change", "Reproducibility", "Model id and all responses cached and logged"],
    ["Hyperparameters fixed rather than tuned", "Construct", "Sensitivity analysis of the fusion constant and candidate depth"],
    ["Single hardware platform", "External", "Latency figures apply only to this machine"]],
  [44, 16, 40]));

// ---------- 6 Data collection
C.push(H1("6. Data collection and management"));
C.push(P("Every run writes machine-readable records. Table 10 lists the datasets used in this report; all are in reports/research/data and are loaded into the companion workbook."));
C.push(...table("Collected data.",
  ["File", "Rows", "Contents"],
  [["per_instance_metrics.csv", "3,161", "One row per system × issue: all metrics, tokens, seconds (test and dev)"],
    ["llm_calls.csv", "943", "Every Gemini call: tokens in/out, seconds, JSON validity, timestamp"],
    ["llm_repeats.csv", "150", "50 issues × 3 repeated LLM runs: ranking, top-1, accuracy"],
    ["latency_repeats.csv", "450", "50 issues × 3 repeats × 3 stages, milliseconds"],
    ["stage_durations.csv", "90", "Start, end, minutes, exit code of every pipeline step (from logs)"],
    ["ltr_seed_iterations.csv / rrf_k_sensitivity.csv / candidate_depth.csv", "5 / 6 / 6", "Iteration and sensitivity results"],
    ["bootstrap_samples.csv", "1,000", "Resampled differences for four key comparisons"],
    ["events_and_errors.csv", "8", "Incidents, causes and resolutions"],
    ["manifest.json", "—", "Git commit, package versions, dataset id, configuration snapshot"]],
  [36, 10, 54], { center: [1] }));
C.push(H2("6.1 Validation and storage"));
for (const s of ["**Content-addressed caches.** Code chunks, embeddings and LLM responses are cached under hashes of their exact inputs, so a cache entry cannot silently belong to different input.",
  "**Schema validation.** Results are typed records (pydantic) checked on read and write.",
  "**Leakage guard.** Every LLM prompt is checked against gold patches and test patches before sending; one false alarm occurred and is logged (Table 11).",
  "**Logs.** Each pipeline step records start and end timestamps and its exit code."]) C.push(B(s));
C.push(H2("6.2 Errors and incidents"));
C.push(...table("Incidents recorded during the project.",
  ["Date", "Component", "Event", "Resolution"],
  [["2026-10-21", "Encoder", "Model failed to load under the installed library versions", "Added dependency and a compatibility shim"],
    ["2026-10-21", "Encoder", "Half-precision encoding 4.3× slower than full precision on this GPU", "Full precision used locally"],
    ["2026-10-25", "Fine-tuning", "~15 min per step; run stopped at step 31 of 41", "Smaller mini-batch (same gradients); 37 min total"],
    ["2026-11-11", "Static analysis", "Recursion error on a deeply nested file", "Counted as parse failure; regression test added"],
    ["2026-11-14", "LLM", "Configured model no longer offered to new API keys", "Switched to gemini-3.5-flash-lite"],
    ["2026-11-14", "Leakage guard", "False alarm on one issue (gold line already in the code)", "Guard refined; real leakage still blocked"],
    ["2026-11-14", "LLM", "Free daily quota exhausted mid-run", "Stopped cleanly; resumed next day from cache"],
    ["2026-11-14", "LLM reranker", "1 of 300 outputs invalid in each of S7 and S8", "Fell back to input order (logged)"]],
  [13, 14, 42, 31]));
C.push(H2("6.3 Resource consumption"));
C.push(...table("Measured resource use.",
  ["Resource", "Measured value"],
  [["Cloned repositories (bare git)", "4.5 GB"], ["Embedding cache / chunk cache / BM25 indexes", "764 MB / 701 MB / 940 MB"],
    ["Fine-tuned model", "522 MB"], ["Peak GPU memory during fine-tuning (mini-batch 4 / 8)", "3.65 GB / 6.15 GB (8 exceeds the 6 GB card)"],
    ["Fine-tuning time", "37 min (41 steps)"], ["Encoding the test corpus with the fine-tuned model", "107 min (175,679 chunks)"],
    [`LLM calls (all experiments)`, `${N.llm_calls.n} calls, ${(N.llm_calls.tokens_total / 1e6).toFixed(2)} M tokens, $0 (free tier)`],
    ["Rebuilding all results from cache (make reproduce)", "9.1 min, 0 API calls"]], [55, 45]));

// ---------- 7 Iterations
C.push(H1("7. Iterations and repeated testing"));
C.push(P("A single run cannot show how much a result depends on chance or on settings. This section reports five kinds of repetition: across repositories, across random seeds, across repeated LLM calls, across parameter settings, and across a second dataset."));
C.push(H2("7.1 Across repositories (leave-one-repo-out folds)"));
const fr = N.folds.rows;
C.push(P(`The reranker was trained 12 times, each time leaving out one repository and testing on it. Across the 12 folds, S6 was higher than its input S5 in ${N.folds.higher}, equal in ${N.folds.equal} and lower in ${N.folds.lower} (Figure 2).`));
C.push(...figure("fig07_loro_folds.png", "Change in function Acc@10 from the learned reranker (S6 − S5) on each held-out repository.", {
  measured: "For each of the 12 repositories, function Acc@10 of S6 minus that of S5 on that repository's issues, after training the reranker on the other 11.",
  shows: "Gains on the five largest repositories (django +4.4, sympy +6.5, scikit-learn +13.0, sphinx +18.8, matplotlib +4.3 points); no change on four small ones; losses on pytest (−5.9), astropy (−16.7) and seaborn (−25.0).",
  why: "The losses are on repositories with 4–17 issues, where one or two issues change the percentage by 6–25 points. Larger repositories also contribute more training data to the other folds.",
  means: "The reranker's average gain is driven by the large repositories; on small repositories its effect is not established.",
  limits: "Per-repository percentages for n < 10 are unstable; no per-fold confidence intervals are shown because they would be very wide.",
}));
C.push(H2("7.2 Across random seeds"));
C.push(P(`The deterministic reranker gives the same output on every run, so a stochastic variant (80% row and feature subsampling) was trained with 5 seeds to estimate sensitivity to training randomness (Figure 3). Function Acc@10 ranged from ${pct(seeds["func_acc@10"].min)} to ${pct(seeds["func_acc@10"].max)} (SD ${(100 * seeds["func_acc@10"].sd).toFixed(1)} points) and file Acc@1 from ${pct(seeds["file_acc@1"].min)} to ${pct(seeds["file_acc@1"].max)}.`));
C.push(...figure("fig10_ltr_seed_iterations.png", "Scores of the stochastic LambdaRank variant over 5 seeds (dots) and of the deterministic S6 reported in the main results (line).", {
  measured: "Four metrics on the 300 test issues for 5 trainings that differ only in random seed.",
  shows: "Seed-to-seed spread is about 1 percentage point. The stochastic variant scores slightly higher than S6 on function Acc@10 and slightly lower on file Acc@1.",
  why: "Subsampling acts as regularization, which can help some metrics and hurt others; with 300 issues, one issue equals 0.33 points.",
  means: "Training randomness is a small source of variation compared with the confidence intervals (about ±5 points). The reported S6 is a typical, not a best-case, configuration.",
  limits: "Only 5 seeds; the variant is not identical to S6, so it estimates rather than measures S6's own seed sensitivity.",
}, 0.65));
C.push(H2("7.3 Repeated LLM runs"));
C.push(P(`The S7 prompt for 50 randomly chosen issues was sent three times with temperature 0 and identical input (Figure 4). The first-ranked answer was the same in all three runs for ${pct(rep.top1_identical_all, 0)} of issues, and the full top-10 order was identical for ${pct(rep.full_ranking_identical_all, 0)}. File Acc@1 on this sample was ${pct(rep.acc_by_repeat.gold_file_top1["0"], 0)}, ${pct(rep.acc_by_repeat.gold_file_top1["1"], 0)} and ${pct(rep.acc_by_repeat.gold_file_top1["2"], 0)} in the three runs.`));
C.push(...figure("fig11_llm_repeat_runs.png", "Repeatability of the Gemini reranker: accuracy in three identical runs (left) and agreement between runs (right), 50 issues.", {
  measured: "For each of 50 issues, the LLM ranking of the same 10 candidates in three independent API calls with identical prompts.",
  shows: "Accuracy changed by up to 4 points between runs. The top answer was stable for most issues, but the full order changed for more than half.",
  why: "Even at temperature 0, hosted LLMs are not guaranteed to be deterministic (batching and floating-point effects on the provider side).",
  means: "S7 and S8 results from a single run include roughly ±2 points of run-to-run variation in addition to sampling uncertainty. The LLM's large Acc@1 gain (+16 points) is much bigger than this variation.",
  limits: "50 issues and 3 runs only; one model version on one day.",
}));
C.push(H2("7.4 Parameter sensitivity"));
C.push(P(`Two settings were varied on cached scores without re-training. The fusion constant k changed file Acc@5 by at most ${(100 * (rrf[60]["file_acc@5"] - rrf[1]["file_acc@5"])).toFixed(1)} points between k = 1 and k ≥ 60 (Figure 5). The candidate depth sets a ceiling for any reranker: the gold function is among the top 50 candidates for ${pct(depth[50].gold_function_in_top)} of issues and among the top 200 for ${pct(depth[200].gold_function_in_top)} (Figure 6).`));
C.push(...figure("fig09_rrf_k_sensitivity.png", "Sensitivity of the fused ranking (S5) to the Reciprocal Rank Fusion constant k.", {
  measured: "S5 accuracy for k = 1, 10, 30, 60, 100 and 300 on all 300 issues.",
  shows: "File-level accuracy is flat for k ≥ 30. Function Acc@10 is highest at k = 1 (64.3%) and slightly lower at k = 60 (62.3%).",
  why: "Small k gives much more weight to the very top ranks of each retriever, which helps when one retriever's first results are reliable.",
  means: "The configured value (60, the common default [11]) is reasonable for files but not optimal for functions. The effect is small relative to the confidence intervals.",
  limits: "Measured on the test set itself, so choosing k from this figure would be tuning on test data; it is reported as sensitivity only.",
}, 0.65));
C.push(...figure("fig08_candidate_depth.png", "Share of issues whose gold function (or file) appears among the top-k candidates of S5.", {
  measured: "Whether any gold function chunk is within the first k fused candidates, and whether any gold file is within the first k ranked files, for k from 5 to 200.",
  shows: `Function coverage rises from ${pct(depth[5].gold_function_in_top, 0)} at k = 5 to ${pct(depth[50].gold_function_in_top, 0)} at k = 50 and ${pct(depth[200].gold_function_in_top, 0)} at k = 200; file coverage is above 95% from k = 50.`,
  why: "Many fixes touch functions whose text shares little with the issue description (see the error analysis in Section 9.7).",
  means: "No reranker working on 50 candidates can exceed about 81% function accuracy; raising the depth to 100 would raise this ceiling by about 6 points.",
  limits: "A larger candidate set also makes reranking harder and slower; this trade-off was not tested.",
}, 0.65));
C.push(H2("7.5 Second dataset"));
C.push(P("The 23-issue dev split comes from six repositories not used anywhere else. Its intervals are wide (Figure 7), so it serves only as a consistency check: the ordering S1 < S5 ≈ S6 is the same on both datasets, while S2 and S4 swap positions on dev."));
C.push(...figure("fig17_dev_vs_test.png", "File Acc@5 on the test set (300 issues) and the dev set (23 issues) with 95% bootstrap intervals.", {
  measured: "File Acc@5 of S1–S6 on two disjoint datasets.",
  shows: "Similar levels and ordering, but the dev intervals span about 30 points.",
  why: "With 23 issues, a single issue changes the result by 4.3 points.",
  means: "The dev results do not contradict the test results, but they cannot confirm small differences.",
  limits: "The dev set is too small for paired tests to be informative.",
}, 0.75));

// ---------- 8 Probability & uncertainty
C.push(H1("8. Probability and uncertainty"));
C.push(P("Two questions are answered here: how precisely is each result known, and how likely is it that an observed difference arose from the particular issues in the sample rather than from the method?"));
C.push(H2("8.1 Bootstrap resampling"));
C.push(P("The bootstrap [16] resamples the 300 issues with replacement 1,000 times and recomputes the statistic each time. The spread of these values approximates the sampling uncertainty. Figure 8 shows the resampled distributions of four key differences."));
C.push(...figure("fig05_bootstrap_distributions.png", "Bootstrap distributions of four paired differences (1,000 resamples). Grey band: central 95%; dashed line: zero difference.", {
  measured: "The difference in mean score between two systems, recomputed on 1,000 resampled sets of 300 issues.",
  shows: "For S8 − S6 (file Acc@1), no resample is near zero. For S4 − S2 and S6 − S5 the 95% band lies just above zero. For S6b − S6 the band includes zero.",
  why: "The width of each distribution reflects how many issues change outcome between the two systems; differences that rest on few issues are more uncertain.",
  means: "The LLM's top-1 gain is clearly beyond sampling noise; the fine-tuning and reranker gains are likely real but smaller; the summary feature's gain is not established.",
  limits: "The bootstrap treats issues as independent; issues from the same repository are related, so true uncertainty may be somewhat larger.",
}));
C.push(H2("8.2 Interpreting p-values"));
C.push(P("The McNemar test asks: among the issues where exactly one of two systems is correct, is the split more uneven than a fair coin would produce? For example, S6 was correct and S5 wrong on 22 issues, and the reverse on 8; a split this uneven or more has probability 0.016 under the assumption of no difference. This is evidence of a difference, not proof, and it does not measure its size; the size is given by the difference and its interval."));
C.push(H2("8.3 Sources of uncertainty compared"));
C.push(...table("Approximate size of each source of variation (percentage points).",
  ["Source", "Size", "Evidence"],
  [["Sampling of 300 issues (95% CI half-width)", "≈ ±4 to ±6", "Bootstrap intervals, Figure 9"],
    ["LLM run-to-run variation (File Acc@1)", "≈ ±2", "Repeated runs, Section 7.3"],
    ["Reranker training seed", "≈ ±0.5 to ±1", "5 seeds, Section 7.2"],
    ["Fusion constant k (k ≥ 30)", "≈ ±0.5 (file), ≈ ±1 (function)", "Section 7.4"],
    ["Single repository with n < 10", "up to ±25", "Leave-one-repo-out folds, Section 7.1"]], [45, 25, 30], { center: [1] }));

// ---------- 9 Results
C.push(H1("9. Results and comparative analysis"));
C.push(H2("9.1 Main results"));
const mrow = (s, name) => [s.system, name, pct(s["file_acc@1"].mean), `${pct(s["file_acc@5"].mean)} [${pct(s["file_acc@5"].low, 0)}–${pct(s["file_acc@5"].high, 0)}]`,
  `${pct(s["func_acc@10"].mean)} [${pct(s["func_acc@10"].low, 0)}–${pct(s["func_acc@10"].high, 0)}]`, s.func_mrr.mean.toFixed(3), Math.round(s.tokens).toLocaleString("en")];
C.push(...table("Results on SWE-bench Lite test (300 issues). Brackets: 95% bootstrap confidence interval.",
  ["System", "Pipeline", "File Acc@1", "File Acc@5", "Function Acc@10", "Function MRR", "Tokens / issue"],
  [mrow(S1, "BM25"), mrow(S2, "Dense"), mrow(S3, "RRF(S1,S2)"), mrow(S4, "Dense, fine-tuned"), mrow(S5, "RRF(S1,S4)"),
    mrow(S6, "LambdaRank"), mrow(S6b, "+ summaries"), mrow(S7, "S5 → LLM"), mrow(S8, "S6 → LLM"), mrow(A1, "S5 + hints*")],
  [8, 16, 11, 18, 18, 11, 11], { center: [2, 3, 4, 5, 6], note: "*A1 uses maintainer hints that the other systems do not see; it is an ablation, not a competitor. S7/S8 reorder only the top 10, so their Acc@10 equals that of their input (S5/S6)." }));
C.push(...figure("fig02_main_results_ci.png", "Main results with 95% bootstrap confidence intervals (share of the 300 test issues).", {
  measured: "Three ranking metrics per system on the same 300 issues; bars are 95% bootstrap intervals.",
  shows: "File Acc@5 rises from 71.0% (BM25) to 86.7% (S6); file Acc@1 jumps from about 60% to about 76% only when the LLM reranker is added; function Acc@10 is highest for S6b (69.0%).",
  why: "Each retrieval improvement adds more correct candidates near the top; the LLM reads the actual code of the top 10 and is good at choosing the single most likely one, but cannot add candidates outside the top 10.",
  means: "Cheap components achieve most of the top-5 accuracy; the LLM mainly improves the first answer.",
  limits: "Intervals of neighbouring systems overlap heavily, so differences must be judged with paired tests (Table 15, Figure 10), not by eye.",
}));
C.push(H2("9.2 Paired comparisons"));
const crow = (a, b, m, rq) => { const r = cmp(a, b, m); return [rq, `${a} − ${b}`, m.replace("_", " "), ci(r), `${r.a_only} / ${r.b_only}`, pv(r.mcnemar_p),
  (r.low > 0 || r.high < 0) ? "Supported" : "Not established"]; };
C.push(...table("Paired comparisons. Difference in percentage points [95% bootstrap CI]; b / c = issues solved only by A / only by B.",
  ["RQ", "A − B", "Metric", "Difference [95% CI]", "b / c", "McNemar", "Reading"],
  [crow("S2", "S1", "file_acc@5", "RQ1"), crow("S3", "S2", "file_acc@5", "RQ1"), crow("S3", "S2", "func_acc@10", "RQ1"),
    crow("S4", "S2", "file_acc@5", "RQ2*"), crow("S5", "S3", "file_acc@5", "RQ2"), crow("S6", "S5", "func_acc@10", "RQ3"),
    crow("S6", "S7", "func_acc@10", "RQ3"), crow("S7", "S6", "file_acc@1", "RQ3"), crow("S8", "S6", "file_acc@1", "RQ3*"), crow("S6b", "S6", "func_acc@10", "RQ4")],
  [7, 11, 16, 26, 10, 13, 17], { center: [3, 4, 5], note: "*Comparison added after the experiment design was fixed. S6 − S5 and S6 − S7 on function Acc@10 are identical because S7 only reorders S5's top 10." }));
C.push(...figure("fig04_paired_differences.png", "Paired differences with 95% bootstrap intervals. Filled markers: interval excludes zero.", {
  measured: "For each planned comparison, the mean per-issue difference between two systems and its bootstrap interval.",
  shows: "Seven differences exclude zero; hybrid vs dense (S3 − S2) and the summary feature (S6b − S6) include zero.",
  why: "Fine-tuning and reranking change the outcome of 20–40 issues mostly in one direction; fusion with BM25 changes outcomes in both directions about equally.",
  means: "The evidence supports the fine-tuning, learned-reranker and LLM-top-1 effects under the tested conditions; it does not establish that fusion helps over a strong dense model or that summaries help.",
  limits: "Ten comparisons are made; borderline intervals (close to zero, e.g. S4 − S2) should be read cautiously.",
}));
C.push(H2("9.3 Accuracy and cost"));
C.push(P(`Figures 11 and 12 relate accuracy to measured cost. Retrieval steps take milliseconds per issue on this machine (median BM25 scoring ${lat.bm25_scoring.median.toFixed(1)} ms, query encoding ${lat.query_encoding_gpu.median.toFixed(0)} ms, vector search ${lat.faiss_search.median.toFixed(0)} ms), while an LLM call takes a median of ${N.llm_calls.seconds_median.toFixed(1)} s and about ${Math.round(N.llm_calls.tokens_in_mean).toLocaleString("en")} input tokens.`));
C.push(...figure("fig03_accuracy_vs_tokens.png", "File accuracy against LLM tokens per issue for five key systems.", {
  measured: "Mean tokens per issue (from the LLM API's usage metadata) and file Acc@1 / Acc@5.",
  shows: "S6 reaches nearly the same file Acc@5 as S8 at zero tokens; S8 adds about 16 points of file Acc@1 for about 6,000 tokens per issue.",
  why: "The LLM's advantage is in choosing among already-retrieved candidates, which affects the first position much more than the top five.",
  means: "If a developer will look at a short list, the zero-token system is sufficient; if only one suggestion is shown, the LLM step adds clear value.",
  limits: "Token counts depend on prompt design (10 candidates, 60 lines each); tokens were free here but would have a price on paid tiers.",
}, 0.65));
C.push(...figure("fig13_latency.png", "Time per issue for retrieval stages (50 issues × 3 repeats) and per Gemini call (943 calls).", {
  measured: "Wall-clock time of each stage, repeated three times per issue; LLM call time recorded by the client.",
  shows: "BM25 takes about 1 ms, encoding and vector search tens of milliseconds, and an LLM call about 5 s — roughly 100× the rest combined.",
  why: "The LLM call includes network latency and generation on a shared free-tier service; vector search time grows with repository size (up to 63k chunks in this set).",
  means: "LLM reranking dominates latency; the non-LLM pipeline is fast enough for interactive use on this machine.",
  limits: "One machine and one network; free-tier latency can change; first-call model loading is excluded.",
}));
C.push(H2("9.4 Results per repository"));
C.push(...figure("fig06_per_repository.png", "File Acc@5 within each repository for BM25 (S1), the learned reranker (S6) and the LLM pipeline (S8).", {
  measured: "File Acc@5 restricted to each repository's issues (n shown in brackets).",
  shows: "S6/S8 are above S1 on the 8 largest repositories; on flask (n = 3) and requests (n = 6) BM25 is higher.",
  why: "Small repositories have few issues, and in these two the issue texts quote file or function names directly, which favours exact lexical matching.",
  means: "The overall improvement is consistent where the sample is large; results for repositories with fewer than 10 issues should not be generalized.",
  limits: "64% of issues come from django and sympy, so overall averages mostly reflect these two codebases.",
}));
C.push(H2("9.5 What the learned reranker relies on"));
C.push(...figure("fig15_feature_importance.png", "Feature importance of the LambdaRank reranker (share of split gain, mean ± SD over 12 folds).", {
  measured: "LightGBM's total split gain per feature, normalized per fold and averaged across the 12 leave-one-repo-out folds.",
  shows: "The fused rank and score carry about a third of the gain, followed by chunk length, the fine-tuned dense rank and import-graph PageRank; explicit mentions of names in the issue carry little.",
  why: "Retrieval scores already capture most name matching; chunk length and centrality add information that retrieval scores do not contain.",
  means: "The reranker mainly re-weights retrieval evidence with a few structural priors (larger, more central code is more often changed).",
  limits: "Gain importance is a model-internal measure and does not prove causal influence; correlated features share credit.",
}, 0.75));
C.push(H2("9.6 Fine-tuning"));
C.push(P(`Fine-tuning ran for ${N.finetune.steps} steps on ${N.finetune.train_pairs.toLocaleString("en")} training triples. The mean loss of the first five steps was ${N.finetune.loss_first5.toFixed(2)} and of the last five ${N.finetune.loss_last5.toFixed(2)}. On 429 held-out validation pairs from two unseen repositories, Acc@10 rose from ${pct(fvl["accuracy@10"].before)} to ${pct(fvl["accuracy@10"].after)} (Figure 15).`));
C.push(...figure("fig12_finetuning.png", "Fine-tuning: training loss per step (left) and validation scores before and after (right).", {
  measured: "Contrastive loss per optimizer step (64 triples each); retrieval of the correct function among validation candidates before and after training.",
  shows: "Loss falls in the first ~10 steps and then fluctuates around 1.7; validation Acc@10 improves by 6 points and Acc@1 by less than 1 point.",
  why: "One epoch of 41 steps is short; the model mainly learns the issue-to-code style of the data rather than finer distinctions.",
  means: "Even small, one-epoch fine-tuning on other repositories transfers to unseen ones (confirmed on the test set by S4 vs S2).",
  limits: "One run, one epoch, one seed; longer training or more data was not tested because of the 6 GB GPU.",
}));
C.push(H2("9.7 Error analysis"));
C.push(P("Twenty S6 failures (correct file not in the top five), sampled at random, were read against their gold patches (Figure 16). Fifteen of them are cases where the issue describes a symptom in one component while the fix is in another, often a lower-level module the issue never names."));
C.push(...figure("fig16_error_categories.png", "Categories of 20 randomly sampled S6 failures.", {
  measured: "One category per failure, assigned by reading the issue and the gold patch.",
  shows: "Root causes in shared lower-level modules (8) and fixes in a different component (7) dominate; noisy issue text and naming confusion are rare.",
  why: "All tested systems rank code by similarity to the issue text, so they find where the symptom is described, not where its cause is.",
  means: "Following import and call relations from the top candidates is the most promising next step.",
  limits: "20 cases and one rater (the analysis was performed by the author's AI assistant and should be confirmed); categories are subjective.",
}, 0.75));
C.push(H2("9.8 Onboarding component"));
C.push(...table("Onboarding evaluation (three demonstration repositories).",
  ["Measure", "Result", "Interpretation"],
  [["Diagram faithfulness", "90 diagrams, 2,428 nodes and edges, 100% re-derived from the code graphs", "No diagram element was invented"],
    ["Citation validity", "107 of 108 LLM summary sentences kept by the strict validator", "Sentences cite lines inside symbols the model was shown"],
    ["Summary rating (29 summaries)", "25 correct, 4 partly correct, 0 wrong", "Single rater; partly = accurate but shallow"],
    ["Ask-the-codebase retrieval", "Correct file in top 5 for 14 of 15 questions", "Small hand-written question set"]],
  [24, 42, 34], { note: "These measure faithfulness and grounding of the generated material, not whether it helps people learn a codebase faster." }));

// ---------- 10 Visualisation & dashboards
C.push(H1("10. Visualisation and dashboards"));
C.push(P("Two kinds of visual monitoring were used. During the experiments, each pipeline step wrote timestamped start and end records, which were followed as they happened; Figure 17 reconstructs that progress from the logs. After the experiments, the companion workbook provides a dashboard whose charts and headline values are formulas over the raw data, so they update when data are changed or added."));
C.push(...figure("fig14_stage_durations.png", "Duration of the 14 longest pipeline steps, in execution order; orange: a step that failed and was rerun.", {
  measured: "Wall-clock minutes between the logged start and end of each step (from data/pipeline.log and data/llm_pipeline.log).",
  shows: "Encoding the test corpus with the fine-tuned model (107 min) and fine-tuning (37 min) dominate; the LLM reranking runs took 11–25 min; one reranker run failed and was repeated.",
  why: "Encoding 175,679 code chunks with a transformer is the heaviest computation; LLM steps are limited by the free tier's request rate.",
  means: "After this one-time cost, all results can be rebuilt from cache in about 9 minutes.",
  limits: "Steps that ran before the logging script, and steps shorter than about 2 minutes, are not shown.",
}));
C.push(...table("Workbook sheets (BugLens_Research_Analysis.xlsx).",
  ["Sheet", "Content", "Calculation"],
  [["Dashboard", "Headline values and five charts", "Links to the sheets below"], ["Summary", "Per-system mean, SD, SE, 95% CI", "AVERAGEIFS, SUMPRODUCT"],
    ["Comparisons", "Paired differences, CI, McNemar p", "SUMPRODUCT, BINOMDIST"], ["Per_Repo", "Accuracy per repository", "AVERAGEIFS, COUNTIFS"],
    ["Iterations", "Seeds, folds, repeated LLM runs", "AVERAGE, STDEV, agreement flags"], ["Sensitivity", "Fusion constant, candidate depth", "MAX − MIN"],
    ["FineTune", "Loss per step, validation", "Moving average"], ["Timing", "Latency, LLM cost, stage durations", "MEDIAN, PERCENTILE, SUM"],
    ["Bootstrap", "1,000 resamples, histogram", "PERCENTILE, COUNTIFS"], ["Errors", "Incidents, misses, failure categories", "SUMIFS"],
    ["Reproducibility", "Versions, commit, commands", "—"]], [18, 47, 35],
  { note: "All 767 formulas were recalculated in Microsoft Excel with zero errors. Excel's normal-approximation intervals agree with the Python bootstrap intervals to within about half a point." }));

// ---------- 11 Reproducibility
C.push(H1("11. Reproducibility and evidence"));
C.push(P("The research process can be repeated from the public repository. Table 18 lists the evidence kept for verification."));
C.push(...table("Evidence for independent verification.",
  ["Evidence", "Where"],
  [["Code version", "Git commit recorded in every run's metadata and in manifest.json"], ["Configuration", "configs/default.yaml, configs/experiments.yaml (snapshot in each run)"],
    ["Package versions", "Exact pins in pyproject.toml and uv.lock"], ["Dataset", "princeton-nlp/SWE-bench_Lite (identifier logged on load)"],
    ["Per-issue outputs", "runs/<system>_<split>.jsonl"], ["LLM responses", "data/cache/llm/*.json (cached; reruns use 0 API calls)"],
    ["Logs", "data/pipeline.log, data/llm_pipeline.log"], ["Analysis", "reports/research/data/*.csv and the workbook"]], [28, 72]));
C.push(P("**Determinism check.** All results were rebuilt from cache with one command (make reproduce) in 9.1 minutes with 0 LLM calls. Rankings and metrics for all nine systems were identical to the stored results; only timing fields differed."));
C.push(P("**What would not reproduce exactly.** Running the LLM steps from scratch (without the cache) would give slightly different S7/S8 results, as Section 7.3 shows; the free-tier model may also be withdrawn, as happened once during the project."));

// ---------- 12 Discussion
C.push(H1("12. Discussion, findings and limitations"));
C.push(H2("12.1 Hypotheses"));
C.push(...table("Hypothesis outcomes under the tested conditions.",
  ["", "Outcome", "Evidence"],
  [["H1 (hybrid)", "Partly supported", `Hybrid beats BM25 (dense alone already does: ${ci(cmp("S2", "S1", "file_acc@5"))}); no established gain over dense alone (${ci(cmp("S3", "S2", "file_acc@5"))} file, ${ci(cmp("S3", "S2", "func_acc@10"))} function)`],
    ["H2 (fine-tuning)", "Supported", `S4 − S2 ${ci(cmp("S4", "S2", "file_acc@5"))}; S5 − S3 ${ci(cmp("S5", "S3", "file_acc@5"))} (file Acc@5)`],
    ["H3 (rerankers)", "Supported, split by rank", `Learned: S6 − S5 ${ci(cmp("S6", "S5", "func_acc@10"))} function Acc@10. LLM: S8 − S6 ${ci(cmp("S8", "S6", "file_acc@1"))} file Acc@1, no gain at Acc@10`],
    ["H4 (summaries)", "Not supported", `S6b − S6 ${ci(cmp("S6b", "S6", "func_acc@10"))}; direction positive, interval includes zero`]],
  [16, 22, 62]));
C.push(H2("12.2 Interpretation"));
for (const s of [
  "**Most of the top-5 accuracy comes from cheap components.** BM25 → fine-tuned dense → fusion → learned reranker raised file Acc@5 from 71.0% to 86.7% without any LLM call.",
  "**The LLM changes the first answer, not the shortlist.** Its value is in ranking the correct candidate first (+16 points file Acc@1), at ~5–6k tokens per issue and ~5 s per call.",
  "**Domain fine-tuning transfers.** Training on 16 unrelated repositories improved results on 12 unseen ones.",
  "**The main remaining errors are structural.** Most failures are fixes located away from where the symptom is described, which no text-similarity method in this study addresses."]) C.push(B(s));
C.push(H2("12.3 Limitations"));
for (const s of ["One benchmark (SWE-bench Lite), Python only, with two repositories providing 64% of issues.",
  "Mostly single-file fixes; multi-file localization is under-represented.",
  "One run per system; variability was estimated by targeted repetitions, not by repeating every system.",
  "One LLM (gemini-3.5-flash-lite, free tier) on specific dates; other models may behave differently.",
  "Possible pre-training contamination of the encoder and the LLM with these public repositories.",
  "Generated patches (30, of which 27 produced valid diffs) were not executed against tests, so no repair rate is claimed.",
  "Summary ratings and error categories were produced by one rater (the author's AI assistant) and should be confirmed by the author.",
  "No user study: the onboarding results concern faithfulness, not usefulness to people."]) C.push(B(s));
C.push(H2("12.4 Practical impact"));
C.push(P("Under the tested conditions, a team could run the zero-token pipeline (S6) locally to obtain a short list of likely files for a new issue in well under a second per issue on a consumer GPU, and add an LLM step when a single best suggestion is wanted. These are measured outcomes on a public benchmark; benefit in day-to-day development has not been measured."));

// ---------- 13 Conclusion
C.push(H1("13. Conclusion and future work"));
C.push(P(`This study measured nine localization pipelines on the same 300 SWE-bench Lite issues with paired statistics, repeated runs and sensitivity checks. Fine-tuning a code encoder on unrelated repositories and adding a learned reranker produced measurable improvements (file Acc@5 ${pct(S6["file_acc@5"].mean)}, function Acc@10 ${pct(S6["func_acc@10"].mean)}) without LLM calls. An LLM reranker improved the first-ranked answer substantially (file Acc@1 ${pct(S8["file_acc@1"].mean)}) but not the top-10 list, and its outputs varied between identical runs. Onboarding summaries did not measurably improve ranking.`));
C.push(H2("Future work"));
for (const s of ["Expand candidates along import and call relations to address 'symptom ≠ fix site' failures (15 of 20 analysed).",
  "Repeat all systems over several seeds and LLM runs to report run-level confidence intervals.",
  "Evaluate on the full SWE-bench and on multi-file fixes.",
  "Execute the generated patches with the official test harness to measure repair rates.",
  "Run a small user study to test whether the onboarding material helps developers."]) C.push(B(s));

// ---------- References
C.push(H1("References"));
const refs = [
  "C. E. Jimenez, J. Yang, A. Wettig, S. Yao, K. Pei, O. Press and K. Narasimhan, \"SWE-bench: Can language models resolve real-world GitHub issues?\" in Proc. ICLR, 2024.",
  "C. S. Xia, Y. Deng, S. Dunn and L. Zhang, \"Agentless: Demystifying LLM-based software engineering agents,\" arXiv:2407.01489, 2024 (FSE 2025).",
  "J. Zhou, H. Zhang and D. Lo, \"Where should the bugs be fixed? More accurate information retrieval-based bug localization based on bug reports,\" in Proc. ICSE, 2012, pp. 14–24.",
  "X. Ye, R. Bunescu and C. Liu, \"Learning to rank relevant files for bug reports using domain knowledge,\" in Proc. FSE, 2014, pp. 689–699.",
  "T. Suresh et al., \"CoRNStack: High-quality contrastive data for better code retrieval and reranking,\" arXiv:2412.01007, 2024.",
  "R. G. Reddy, T. Suresh, J. Doo, Y. Liu, X. P. Nguyen, Y. Zhou, S. Yavuz, C. Xiong, H. Ji and S. Joty, \"SweRank: Software issue localization with code ranking,\" arXiv:2505.07849, 2025.",
  "Z. Chen et al., \"LocAgent: Graph-guided LLM agents for code localization,\" arXiv:2503.09089, 2025.",
  "V. Tawosi, S. Alamir, X. Liu and M. Veloso, \"Meta-RAG on large codebases using code summarization,\" arXiv:2508.02611, 2025.",
  "M. A. Al Mamun and G. Uddin, \"BLAgent: Agentic RAG for file-level bug localization,\" arXiv:2605.17965, 2026.",
  "S. Robertson and H. Zaragoza, \"The probabilistic relevance framework: BM25 and beyond,\" Found. Trends Inf. Retr., vol. 3, no. 4, pp. 333–389, 2009.",
  "G. V. Cormack, C. L. A. Clarke and S. Büttcher, \"Reciprocal rank fusion outperforms Condorcet and individual rank learning methods,\" in Proc. SIGIR, 2009, pp. 758–759.",
  "C. J. C. Burges, \"From RankNet to LambdaRank to LambdaMART: An overview,\" Microsoft Research, Tech. Rep. MSR-TR-2010-82, 2010.",
  "G. Ke et al., \"LightGBM: A highly efficient gradient boosting decision tree,\" in Proc. NeurIPS, 2017.",
  "N. Reimers and I. Gurevych, \"Sentence-BERT: Sentence embeddings using Siamese BERT-networks,\" in Proc. EMNLP, 2019.",
  "L. Gao, Y. Zhang, J. Han and J. Callan, \"Scaling deep contrastive learning batch size under memory limited setup,\" in Proc. RepL4NLP Workshop, 2021.",
  "B. Efron and R. J. Tibshirani, An Introduction to the Bootstrap. New York: Chapman & Hall, 1993.",
  "Q. McNemar, \"Note on the sampling error of the difference between correlated proportions or percentages,\" Psychometrika, vol. 12, no. 2, pp. 153–157, 1947.",
];
refs.forEach((r, i) => C.push(new Paragraph({ spacing: { after: 80 }, indent: { left: 540, hanging: 540 },
  children: [new TextRun({ text: `[${i + 1}]\t`, size: 19, font: FONT }), new TextRun({ text: r, size: 19, font: FONT })],
  tabStops: [{ type: "left", position: 540 }] })));
C.push(new Paragraph({ spacing: { before: 200 }, children: runs("*Formatting of figures and tables follows common university and IEEE guidance: table captions above, figure captions below, no chart titles, full axis labels with units, minimal gridlines, and colour choices that remain distinguishable in black-and-white print.*", { size: 17, color: "404040" }) }));

// ================================================================== document
const doc = new Document({
  creator: "BugLens project", title: "BugLens research report", features: { updateFields: true },
  styles: {
    default: { document: { run: { font: FONT, size: 21 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 30, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 120, after: 200 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true, color: "1F3864" }, paragraph: { spacing: { before: 240, after: 100 }, keepNext: true, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 21, bold: true }, paragraph: { spacing: { before: 160, after: 80 }, keepNext: true, outlineLevel: 2 } },
      { id: "TOC1", name: "toc 1", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 19, bold: true }, paragraph: { spacing: { before: 40, after: 0 } } },
      { id: "TOC2", name: "toc 2", basedOn: "Normal", next: "Normal",
        run: { font: FONT, size: 18 }, paragraph: { spacing: { before: 0, after: 0 }, indent: { left: 300 } } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 400, hanging: 260 } } } }] },
    { reference: "numbers", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 400, hanging: 300 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1418, bottom: 1418, left: 1418, right: 1418, header: 708, footer: 708 } },
      titlePage: true },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: "BugLens — research report", size: 16, color: "7F7F7F", font: FONT })] })] }),
      first: new Header({ children: [new Paragraph({ children: [] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 18, font: FONT })] })] }),
      first: new Footer({ children: [new Paragraph({ children: [] })] }) },
    children: C,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("saved", OUT, `${tableNo} tables, ${figNo} figures`); });
