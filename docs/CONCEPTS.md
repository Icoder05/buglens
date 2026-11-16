# Key concepts in plain language

This page explains the ideas behind BugLens for readers who are not specialists in information
retrieval or machine learning. Each term links the idea to where it appears in the project.

## The task

**Bug localization.** A user reports a problem ("calling X with an empty list crashes"). Before
anyone can fix it, a developer must find *which files and functions* need to change. BugLens ranks
the code of a repository so that the place to fix appears near the top of the list.

**SWE-bench Lite.** A public benchmark of 300 real GitHub issues from 12 popular Python projects
(django, sympy, scikit-learn, …). For each issue we know the repository *as it was before the fix*
and the *actual fix* (the patch), so we can check whether a ranking found the right place.

**Gold label.** The "correct answer" for an issue: the files and functions the real patch changed.
BugLens derives these automatically from the patch (`src/buglens/data/labels.py`).

## How the code is searched

**Chunk.** A small searchable piece of code: one function, one method, one class, or the remaining
top-level code of a file. Chunks are cut along the Python syntax tree (`src/buglens/chunking/`).

**BM25 (system S1).** A classic keyword search: a chunk scores high if it contains the issue's
rare words often. Fast and strong when the issue names functions or files.

**Dense retrieval / embeddings (S2, S4).** A neural network turns the issue and each chunk into a
list of numbers (a vector). Text with similar *meaning* gets similar vectors, even if the words
differ. S2 uses a public code model (CodeRankEmbed); S4 uses the same model after **fine-tuning**,
i.e. extra training on issues and fixes from 16 other repositories.

**Rank fusion — RRF (S3, S5).** Combines two ranked lists by giving each chunk points for being near
the top of either list. Simple, needs no tuning of score scales.

**Learning to rank — LambdaRank (S6).** A small machine-learning model (gradient-boosted trees) that
re-orders the top 50 candidates using 21 signals: the search scores, whether the issue mentions the
function name, the size of the code, how central the file is in the project, and more.

**LLM reranker (S7, S8).** A large language model (Google Gemini 3.5 Flash-Lite) reads the issue and
the top 10 code candidates and puts them in order. More accurate for the *first* answer, but slower
and it costs tokens.

## How results are measured

**Acc@k ("accuracy at k").** The share of issues where a correct file (or function) appears in the
top *k* results. *File Acc@5 = 0.867* means: for 86.7% of the 300 issues, a correct file was among
the first five suggestions.

**MRR (mean reciprocal rank).** Rewards putting the answer first: 1 if the first suggestion is
correct, 1/2 if the second is, 1/3 if the third, and so on, averaged over issues.

**Tokens.** The units an LLM reads and writes; they drive LLM cost and time.

## How uncertainty is handled

**95% confidence interval (CI).** A range that reflects how much a result could change with a
different sample of issues. "86.7% [82.7–90.3]" means the true accuracy is plausibly anywhere in
that range.

**Bootstrap.** Computing the CI by re-sampling the 300 issues (with replacement) 1,000 times and
looking at how much the result moves.

**Paired comparison.** Two systems are compared on the *same* issues, which makes small differences
easier to detect. The **McNemar test** looks only at issues one system solved and the other did not,
and asks whether that split is more lopsided than chance would explain.

**Repeated runs.** Running the same experiment several times (different seeds, or the same LLM prompt
three times) to see how stable the result is.

## The onboarding part

**Static analysis.** Reading code without running it: which modules import which, which classes
inherit from which, which functions call which (`src/buglens/analysis/`).

**Architecture diagram.** Boxes = packages, arrows = imports. Every box and arrow is re-checked
against the analysed code before it is drawn, so no element is invented.

**Cited summary.** The LLM writes short descriptions of packages, but every sentence must cite a real
`file:line` that it was shown; sentences that fail this check are removed (`src/buglens/onboard/validate.py`).

**Leakage guard.** A safety check that stops the LLM from ever being shown the real fix, which would
make the evaluation meaningless (`src/buglens/llm/client.py`).
