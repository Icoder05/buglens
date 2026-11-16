# How to run BugLens

Tested on Windows 10 with an NVIDIA GTX 1660 SUPER (6 GB). Linux and macOS work the same way
(the GPU is optional for the demo).

## 1. Install (once)

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/), [git](https://git-scm.com/)
   and [Graphviz](https://graphviz.org/download/) (for the diagrams).
2. Clone and install:
   ```bash
   git clone https://github.com/Icoder05/buglens.git
   cd buglens
   make setup          # = uv sync: creates .venv with Python 3.11 and pinned packages
   ```
3. (Optional, only for LLM features) copy `.env.example` to `.env` and put a free key from
   https://aistudio.google.com/apikey in it: `GEMINI_API_KEY=...`

## 2. Check everything works (1 minute)

```bash
make test           # unit tests
make lint           # code style
```

## 3. Rebuild the experiments

The experiment data (`data/`, ~7 GB: cloned repositories, caches, fine-tuned model) is not stored in
git. Two ways to get the numbers:

| Goal | Command | Time |
| --- | --- | --- |
| Everything from scratch (clones repos, encodes code, fine-tunes, LLM calls) | `make experiments` | several hours, GPU recommended |
| Just the LLM steps (S7, S8, summaries, patches) after the above | `powershell -File scripts/llm_pipeline.ps1` | ~1 h, free Gemini quota |
| Rebuild every result table from the cache | `make reproduce` | ~9 minutes, 0 LLM calls |
| Onboarding diagrams + guides for flask, requests, django | `make onboard` | ~2 minutes |
| Research report + Excel workbook | `make research` | ~15 minutes (needs Word/Excel for TOC refresh, recalculation, PDF) |

Long runs are resumable: every step caches its results, so rerunning continues where it stopped
(`scripts/resume_pipeline.ps1` logs to `data/pipeline.log`).

## 4. Open the demo app

```bash
make demo           # then open http://127.0.0.1:7860
```

**Localize tab**
1. Pick an issue, e.g. `pallets__flask-4045`.
2. Choose a system: S1 (keyword search), S5 (hybrid), S6 (best without an LLM).
3. You see the top-10 predicted functions (✅ = the real fix), their source code, and the
   architecture diagram with predicted packages in yellow and the real fix outlined in red.
4. Or open "…or paste an issue", choose a repository and describe a bug in your own words.

**Onboard tab**
1. Pick flask, requests or django.
2. Browse the architecture diagram and the package / class / call-flow drop-downs.
3. Ask a question, e.g. *where are blueprints registered?* — you get an answer with `file:line`
   citations (needs a Gemini key; limited to 50 written answers per day), plus the retrieved code.
4. Scroll down for the full onboarding guide.

Stop the app with `Ctrl + C`.

## 5. Command reference

```text
buglens data       --split test|dev|train     load SWE-bench, clone repos, build gold labels
buglens index      --split test --retriever bm25|dense [--model PATH]
buglens retrieve   --system S1..S5|A1 --split test
buglens pairs                                  build fine-tuning triples
buglens finetune                               fine-tune the encoder
buglens rerank     --system S6|S6b --split test
buglens llm        --system S7|S8 --split test [--limit N]
buglens eval       --system S1 --split test
buglens report                                 reports/results.md + figures
buglens errors     --system S6 --n 20          failure sample for error analysis
buglens analyze | diagrams | summarize | guide | onboard  --repo pallets/flask
buglens ask        --repo pallets/flask "where are blueprints registered?"
buglens onboard-eval
buglens patch      --system S8 --limit 30      stretch: generate patches
buglens demo       [--share]
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `make` / `uv` not found | Reopen the terminal after installing; run from the `buglens` folder |
| Diagrams missing | Install Graphviz and make sure `dot -V` works |
| "Ask" shows only file locations | No Gemini key, or the daily limit / free quota is used up |
| Gemini model error 404 | Free models change; set `llm.model` in `configs/default.yaml` to a current Flash model |
| Out of GPU memory while fine-tuning | Lower `training.mini_batch_size` in `configs/default.yaml` |
| `--share` link fails on Windows | Windows Defender blocks Gradio's tunnel helper (`frpc`); allow it in Windows Security, or deploy to Hugging Face Spaces |
