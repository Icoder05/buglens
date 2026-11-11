# BugLens results

SWE-bench Lite **test** (300 instances). Cells: mean [bootstrap 95% CI, 1000 resamples, seed 42].

**Finding.** The best system on all 300 instances is **S6** (S5 → LambdaRank): file Acc@5 0.867 [0.827, 0.903], function Acc@10 0.670 [0.613, 0.723], at 0 LLM tokens per issue.

## Main results

| system | pipeline | n | file_acc@1 | file_acc@3 | file_acc@5 | file_mrr | func_acc@5 | func_acc@10 | func_recall@10 | func_mrr | mean_tokens | mean_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | BM25 | 300 | 0.470 [0.417, 0.527] | 0.653 [0.600, 0.707] | 0.710 [0.660, 0.760] | 0.581 [0.535, 0.629] | 0.437 [0.383, 0.490] | 0.527 [0.470, 0.580] | 0.479 [0.425, 0.532] | 0.311 [0.272, 0.351] | 0.0 | 0.052 |
| S2 | Dense (CodeRankEmbed) | 300 | 0.513 [0.453, 0.573] | 0.727 [0.670, 0.773] | 0.793 [0.743, 0.840] | 0.634 [0.590, 0.680] | 0.463 [0.407, 0.523] | 0.560 [0.507, 0.620] | 0.510 [0.458, 0.565] | 0.327 [0.286, 0.372] | 0.0 | 0.005 |
| S3 | RRF(S1, S2) | 300 | 0.527 [0.470, 0.587] | 0.733 [0.680, 0.780] | 0.790 [0.740, 0.837] | 0.648 [0.604, 0.694] | 0.497 [0.443, 0.553] | 0.590 [0.537, 0.647] | 0.541 [0.488, 0.598] | 0.368 [0.326, 0.412] | 0.0 | 0.005 |
| S4 | Dense (fine-tuned) | 300 | 0.587 [0.527, 0.643] | 0.783 [0.733, 0.827] | 0.840 [0.797, 0.880] | 0.696 [0.650, 0.738] | 0.513 [0.457, 0.573] | 0.610 [0.550, 0.663] | 0.557 [0.498, 0.611] | 0.381 [0.337, 0.427] | 0.0 | 0.004 |
| S5 | RRF(S1, S4) | 300 | 0.593 [0.537, 0.647] | 0.810 [0.763, 0.850] | 0.853 [0.813, 0.893] | 0.708 [0.665, 0.750] | 0.547 [0.487, 0.600] | 0.623 [0.567, 0.677] | 0.579 [0.524, 0.635] | 0.405 [0.359, 0.446] | 0.0 | 0.005 |
| S6 | S5 → LambdaRank | 300 | 0.597 [0.543, 0.650] | 0.807 [0.760, 0.850] | 0.867 [0.827, 0.903] | 0.709 [0.665, 0.749] | 0.577 [0.523, 0.630] | 0.670 [0.613, 0.723] | 0.624 [0.570, 0.675] | 0.413 [0.369, 0.455] | 0.0 | 0.41 |

## Paired comparisons

Difference A − B on common instances; paired bootstrap 95% CI and two-sided p; exact McNemar on the binary metric.

| A vs B | metric | n | diff | bootstrap p | McNemar (A only / B only, p) |
| --- | --- | --- | --- | --- | --- |
| S2 vs S1 | file_acc@5 | 300 | +0.083 [+0.033, +0.130] | 0.002 | 40 / 15, p=0.001 |
| S2 vs S1 | func_acc@10 | 300 | +0.033 [-0.023, +0.093] | 0.260 | 44 / 34, p=0.308 |
| S3 vs S2 | file_acc@5 | 300 | -0.003 [-0.043, +0.037] | 0.910 | 17 / 18, p=1.000 |
| S3 vs S2 | func_acc@10 | 300 | +0.030 [-0.013, +0.070] | 0.190 | 24 / 15, p=0.200 |
| S4 vs S2 | file_acc@5 | 300 | +0.047 [+0.007, +0.087] | 0.032 | 27 / 13, p=0.038 |
| S4 vs S2 | func_acc@10 | 300 | +0.050 [-0.000, +0.100] | 0.064 | 36 / 21, p=0.063 |
| S5 vs S3 | file_acc@5 | 300 | +0.063 [+0.030, +0.100] | 0.002 | 23 / 4, p=0.000 |
| S5 vs S3 | func_acc@10 | 300 | +0.033 [-0.003, +0.070] | 0.118 | 23 / 13, p=0.132 |
| S6 vs S5 | file_acc@5 | 300 | +0.013 [-0.010, +0.037] | 0.366 | 9 / 5, p=0.424 |
| S6 vs S5 | func_acc@10 | 300 | +0.047 [+0.010, +0.083] | 0.008 | 22 / 8, p=0.016 |

## Ablation A1: hints appended to the query

| system | pipeline | n | file_acc@1 | file_acc@3 | file_acc@5 | file_mrr | func_acc@5 | func_acc@10 | func_recall@10 | func_mrr | mean_tokens | mean_seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A1 | S5 + hints in query | 300 | 0.643 [0.590, 0.697] | 0.840 [0.793, 0.880] | 0.890 [0.853, 0.927] | 0.749 [0.709, 0.789] | 0.613 [0.560, 0.667] | 0.697 [0.643, 0.750] | 0.649 [0.598, 0.696] | 0.468 [0.422, 0.513] | 0.0 | 0.016 |
| S5 | RRF(S1, S4) | 300 | 0.593 [0.537, 0.647] | 0.810 [0.763, 0.850] | 0.853 [0.813, 0.893] | 0.708 [0.665, 0.750] | 0.547 [0.487, 0.600] | 0.623 [0.567, 0.677] | 0.579 [0.524, 0.635] | 0.405 [0.359, 0.446] | 0.0 | 0.005 |

## Figures

![Accuracy vs tokens](figures/acc_vs_tokens.png)

![Per-repo Acc@5](figures/per_repo_acc5.png)

![LambdaRank feature importance](figures/feature_importance.png)

![Fine-tuning loss](figures/finetune_loss.png)

## Fine-tuning (RQ2) — validation on held-out repositories

2571 train / 429 val pairs (repo-disjoint).

| metric | before | after |
| --- | --- | --- |
| val_cosine_accuracy@1 | 0.231 | 0.238 |
| val_cosine_accuracy@10 | 0.538 | 0.599 |
| val_cosine_mrr@10 | 0.328 | 0.351 |
