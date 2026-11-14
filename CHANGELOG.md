# Changelog

All deviations from the PRD are recorded here, with the reason.

## M1–M10 (2026-10-21)

### Environment / dependencies
- **sentence-transformers 6.1 + transformers 5.20** (latest resolvable with Gradio 6, which needs
  huggingface-hub ≥ 1.0). CodeRankEmbed's remote code calls
  `PreTrainedModel.get_extended_attention_mask`, removed in transformers 5; `retrieval/dense.py`
  re-adds the transformers-4 implementation (`_patch_transformers`). Verified: embeddings rank the
  relevant code first. Pinning transformers 4.x was impossible (conflicts with Gradio 6).
- Added `einops` (required by CodeRankEmbed's remote code).
- Torch on Windows comes from the PyTorch **cu126** index (GPU: GTX 1660 SUPER, 6 GB); Linux
  (Kaggle, HF Spaces) uses the PyPI wheel.
- **fp16 off by default** (`retrieval.fp16`, `training.fp16`): measured 4× *slower* than fp32 on
  the GTX 16xx (no tensor cores). The Kaggle notebook turns fp16 on for T4/P100.
- Fine-tuning ran on the **local GPU** instead of Kaggle (user decision); the Kaggle notebook
  (`notebooks/kaggle_finetune.ipynb`) is provided and runs the same `buglens finetune`.

### Data
- SWE-bench Lite **test has 12 repositories, not 11** (astropy, django, flask, matplotlib, pylint,
  pytest, requests, scikit-learn, seaborn, sphinx, sympy, xarray). Leave-one-repo-out uses 12 folds.
- Dataset ids `princeton-nlp/SWE-bench_Lite` and `princeton-nlp/SWE-bench` loaded as specified
  (fallback ids kept in config).
- Repositories are cloned with `git clone --bare` (full history, no working tree): files are read
  with `git ls-tree` / `git cat-file --batch` exactly as FR-D4 specifies, and Windows-invalid
  file names in some repos cannot break a checkout.
- Gold files include only `.py` files (non-Python files in a patch are not localization targets).
- `test_patch`, `FAIL_TO_PASS`, `PASS_TO_PASS` are stored separately
  (`data/cache/instances/<split>_gold_texts.json`) and used *only* by the LLM leakage guard.

### Chunking / labels
- Two chunks with the same qualname in one file (e.g. `@property` getter + `@x.setter`) get a
  `#2` suffix to keep chunk ids unique (`A.p`, `A.p#2`).
- The module chunk spans the whole file (lines 1..N) so that any line not inside a def/class maps
  to it; its *text* holds only the remaining top-level code.

### Retrieval / ranking
- File ranking derives from the top-N (50) candidate chunks (FR-R7), so a file outside the top-50
  chunks is unranked.
- Training pairs: added `training.max_pairs_per_repo` (300) and round-robin sampling across the
  eligible train repos so one big repo cannot dominate. Clone size uses the GitHub API `size`
  (follows renames).
- Reranker feature `import_pagerank` is PageRank × number of modules (1.0 = average module), so
  it is comparable across repos of different sizes. Missing retriever scores are NaN (LightGBM
  handles them natively).
- S6 on `--split dev` trains on all test repos and predicts dev (dev is never used for training);
  on `--split test` it uses leave-one-repo-out. A final model trained on all test repos is saved
  to `data/models/ltr_S6.txt` for the demo's live "paste an issue" mode.
- S6b uses LORO over all 12 repos with `pkg_summary_sim` = NaN for repos without summaries, and
  is reported against S6 only on the subset with summaries.

### Run-time fixes (2026-11-11 … 14)
- `training.mini_batch_size` 16 → **4**: with 16 the 6 GB GPU spilled into shared system memory
  (15 min/step, 10 h run). GradCache makes the mini-batch a memory knob only — the effective
  batch stays 64 and gradients are identical. Fine-tuning then took 37 min.
- `analysis/facts.py`: a sympy file parses but overflows Python's recursion limit while walking
  the AST; it now counts as a parse failure (FR-A3 "never crash"), with a regression test.
- Added comparison **S4 vs S2** to `experiments.yaml` (the most direct RQ2 test).
- Demo: opens on a flask instance, loads tabs concurrently, scales SVGs to the page.
- `buglens errors` never overwrites an `error_analysis.md` whose categories are filled in;
  `buglens data` never overwrites a filled `label_check.md`.

### LLM
- **Model `gemini-3.5-flash-lite`** (Flash class, free tier). Verified 2026-11-14 with ListModels
  and test calls: `gemini-2.5-flash` returns 404 for new keys; `gemini-3.5-flash` answered in 48 s
  or timed out (504); `gemini-3.5-flash-lite` answers in ~1 s with valid schema JSON.
- Client: 120 s request timeout; 504 is retried like 429/503; optional `thinking_level` (Gemini 3).
- Cache key is `sha1(model + schema + prompt)` (schema added so a schema change cannot return a
  stale answer).
- The leakage guard checks full gold texts **and** every added line (≥ 30 chars) of the
  instance's own gold patch/test patch, excluding lines already present in the issue/hints or on
  the patch's original side (those are public input or pre-existing code).
- A *daily* quota error stops a command immediately and saves partial results; reruns resume from
  the cache.

### Onboard
- Packages = first `pkg_depth` components of the **module path** (with `src/` or `lib/` layout
  roots stripped), so `src/flask/app.py` → `flask/app`, `django/db/models/query.py` → `django/db`.
- Calls to Python builtins (`print`, `len`, …) are ignored rather than counted as unresolved.
- Call-graph nodes for module-level code are `<module>.<module>`; class constructors resolve to
  the class node.
- On Graphviz diagrams, edges of weight 1 are unlabelled (the legend says so) to reduce clutter;
  Mermaid output keeps all labels. `verify_diagram` always checks the exact weights.
- Glossary = most frequent *name parts* across class/function/method names (split like the BM25
  tokenizer), each tied to a representative definition (an exact-name class if one exists).
- QA set for FR-Q4 lives in `configs/onboard_qa.yaml` (committed; `data/` is gitignored);
  `data/onboard_qa.yaml` overrides it if present.
- Rating sheet has an extra `repo` column.

### Added (not in PRD)
- `buglens patch` (M10) and `make patches` / `make harness` (harness is **not** run).
- `reports/label_check.md` for the M1 hand check of 3 instances' labels.
- `make lint`, `make minimal-loop`, `make experiments`.

## M0 — Skeleton (2026-10-20)

- Added: project skeleton, `configs/default.yaml`, `configs/experiments.yaml`, pydantic schemas
  (PRD Section 6, verbatim), Typer CLI with every Section 10 command stubbed, Makefile, smoke tests.
- Versions pinned exactly in `pyproject.toml` (resolved by `uv lock`, Python 3.11.15).
- Deviation: added `pyarrow` as an explicit dependency (needed for Parquet pairs, FR-T1).
