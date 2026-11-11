# BugLens: Hybrid Retrieval, Learning to Rank and Static-Analysis Onboarding for Bug Localization

## 1. Introduction

When a GitHub issue arrives, a maintainer's first task is *localization*: which files and functions
must change? For a newcomer to the codebase the question is harder, because they do not yet know its
architecture. BugLens addresses both with one shared index of a Python repository:

- **Localize** ranks functions (and, derived from them, files) for an issue, at the commit where the
  bug existed. It is evaluated on SWE-bench Lite (300 test issues, 12 repositories).
- **Onboard** produces what a newcomer needs on day one: an architecture block diagram, drill-down
  diagrams, a cited onboarding guide and an "ask the codebase" box. Diagrams come only from static
  analysis; LLM-written sentences must cite `path:line`, enforced by a validator.

Research questions:

- **RQ1** Does hybrid retrieval (BM25 + dense) beat either alone?
- **RQ2** Does contrastive fine-tuning on SWE-bench-train improve dense retrieval on unseen repositories?
- **RQ3** Does a LambdaRank reranker with structural features close the gap to an LLM reranker, and at
  what token cost?
- **RQ4** Do package summaries written for human onboarding help machine localization as a reranker
  feature?

## 2. Related work

**SWE-bench** (Jimenez et al., 2024) pairs real GitHub issues with the fixing pull request and the
repository snapshot; SWE-bench Lite is a 300-instance subset of mostly single-file fixes. Agentic
systems (e.g. SWE-agent, Agentless) begin with a localization stage, often hierarchical (file →
function) and frequently LLM-driven. **Code retrieval** moved from lexical BM25 to bi-encoders trained
contrastively on code–text pairs; **CodeRankEmbed** (Suresh et al., 2024) is a 137M-parameter
asymmetric code embedding model trained with hard negatives. **Learning to rank** with gradient-boosted
trees (LambdaMART/LambdaRank) remains a strong way to fuse heterogeneous relevance signals.
**Code summarization** with LLMs is fluent but prone to unsupported claims; BugLens constrains it with
retrieval of static facts and a citation validator rather than trusting free text.

## 3. Method

### 3.1 Shared index
Each `(repo, commit)` is read straight from git objects (`git ls-tree`, `git cat-file --batch`).
Python files (tests, docs and `setup.py` excluded) are split with `ast` into function, method, class
and module chunks (60-line windows when a file does not parse). The same chunk list feeds BM25, dense
retrieval, reranker features and the onboarding tools. Gold labels map the patch's removed lines (and
insertion points) to the innermost chunk at `base_commit`.

### 3.2 Localize
- **S1 BM25** over a code-aware tokenizer (camelCase/snake_case splitting, full identifiers kept).
- **S2 Dense**: off-the-shelf CodeRankEmbed, FAISS exact inner product, content-addressed embedding cache.
- **S3 = RRF(S1, S2)** with k = 60.
- **S4 Dense (fine-tuned)**: CodeRankEmbed trained with cached multiple-negatives ranking loss
  (GradCache; batch 64) on 3,000 (issue, gold function, BM25 hard negative) triples from 18
  SWE-bench-train repositories, which are disjoint from the test repositories; validation is repo-disjoint.
- **S5 = RRF(S1, S4)**.
- **S6**: LightGBM LambdaRank over S5's top 50 with 21 features: retriever scores and ranks; mentions of
  the path, qualified name or name in the issue and in tracebacks; chunk size and kind; directory depth;
  and import-graph PageRank. Trained with leave-one-repo-out CV over the 12 test repositories.
- **S6b**: S6 plus `pkg_summary_sim`, the cosine between the issue and the onboarding summary of the
  candidate's package.
- **S7/S8**: Gemini Flash reranks the top 10 of S5/S6 from the issue and the first 60 lines of each
  candidate, returning schema-constrained JSON.

### 3.3 Onboard
Static facts per file (imports with relative-import resolution, classes and bases, functions and
signatures, call sites) give an import graph, an inheritance graph and an approximate call graph (names,
`self.method` via in-repo bases, module aliases). PageRank on the import graph ranks modules. Diagrams
(package block diagram, package drill-down, class diagram, call flow) are built as specs whose every
node and edge records the graph elements it represents; `verify_diagram` re-derives them and must
report 100% before an SVG or Mermaid file is written. Package summaries are generated from the top-10
symbols' signatures and docstrings only, and a strict validator keeps a sentence only if it cites a line
inside a symbol shown to the model. Summaries use each repository's earliest test commit, so RQ4 cannot
see future code.

## 4. Experimental setup
SWE-bench Lite test (300) for all reported numbers; dev (23, six other repositories) for sanity checks
only; the same instances for every system; seeds fixed (42). Metrics: file Acc@1/3/5 and MRR, function
Acc@5/10, Recall@10 and MRR. 95% bootstrap CIs (1,000 resamples), plus paired bootstrap and exact
McNemar tests for the planned comparisons. Hardware: one consumer GPU (GTX 1660 SUPER, 6 GB) and a
6-core CPU. LLM: Gemini Flash free tier. Total cost: $0.

## 5. Results
_Filled from `reports/results.md`._

## 6. Onboarding evaluation
_Filled from `reports/onboarding_eval.md`._

## 7. Error analysis
_Filled from `reports/error_analysis.md`._

## 8. Limitations and threats to validity
- SWE-bench Lite is biased towards single-file fixes; multi-file localization is under-tested.
- Python only, and static call graphs are approximate: dynamic dispatch, decorators and monkey-patching
  are unresolved and shown as such.
- Summaries were rated by one rater; free-tier model versions change over time.
- Pre-trained encoders and LLMs may have seen these popular repositories (possible contamination).
- The leave-one-repo-out reranker is trained on test-set repositories other than the held-out one; it
  never sees the evaluated repository, but hyperparameters were fixed a priori rather than tuned.
- No user study: the onboarding claims concern faithfulness and grounding, not developer speed.

## 9. Future work
A LoRA-tuned LLM reranker; a reinforcement-learning policy for repository navigation; execution feedback
from reproducing tests; multi-file bugs (full SWE-bench); a user study measuring onboarding time.

## References
- C. E. Jimenez et al. *SWE-bench: Can Language Models Resolve Real-World GitHub Issues?* ICLR 2024.
- T. Suresh et al. *CoRNStack: High-Quality Contrastive Data for Better Code Ranking* (CodeRankEmbed), 2024.
- C. Burges. *From RankNet to LambdaRank to LambdaMART: An Overview.* MSR-TR-2010-82.
- G. V. Cormack, C. L. A. Clarke, S. Büttcher. *Reciprocal Rank Fusion outperforms Condorcet and individual rank learning methods.* SIGIR 2009.
