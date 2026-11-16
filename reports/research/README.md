# BugLens research report — files

| File | What it is |
| --- | --- |
| `BugLens_Research_Report.docx` | The research report (34 pages, 17 figures, 19 tables). Editable in Word. |
| `BugLens_Research_Report.pdf` | PDF copy of the report. |
| `BugLens_Research_Analysis.xlsx` | Companion workbook: raw data, every calculation as an Excel formula, native charts, dashboard. |
| `figures/` | The 17 report figures (PNG, 220 dpi). |
| `data/` | Tidy CSV/JSON data behind every number (per-issue metrics, LLM calls, repeats, timings, logs, manifest). |

## Rebuild everything

```
make research
```

This runs, in order: `scripts/research/collect.py` (data + repeat/sensitivity experiments, no LLM calls
except cached ones), `figures.py`, `report_numbers.py`, `build_workbook.py` (+ Excel recalculation),
`build_report.js` (+ Word table-of-contents refresh and PDF export).

The LLM repeated-run experiment (`scripts/research/llm_repeats.py`) makes ~100 new Gemini calls and is
run separately; its answers are cached, so rerunning it costs nothing.

## Formatting conventions

Table captions above tables, figure captions below figures, no chart titles (the caption explains),
full axis labels with units, minimal gridlines, colour-blind-safe palette with distinct markers, and a
five-part explanation under every figure (what was measured, what it shows, why, what it means,
limitations).
