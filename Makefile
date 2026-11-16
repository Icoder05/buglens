# BugLens — make setup | test | lint | reproduce | onboard | demo
# Recipes are single commands so they work with both sh and cmd.exe make shells.

.PHONY: setup test lint data index pairs minimal-loop finetune experiments reproduce onboard demo patches harness

setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check src tests

# ---- one-time, expensive steps (results are cached under data/) ----
data:
	uv run buglens data --split test
	uv run buglens data --split dev
	uv run buglens data --split train

index:
	uv run buglens index --split test --retriever bm25
	uv run buglens index --split test --retriever dense

pairs:
	uv run buglens pairs

minimal-loop:
	uv run python -m buglens.training.minimal_loop

finetune:
	uv run buglens finetune

# Full experiment run from scratch (hours: cloning, encoding, fine-tuning, LLM calls).
experiments: data index pairs finetune reproduce

# ---- fast: rebuilds every number from cached artifacts (< 10 minutes) ----
reproduce:
	uv run buglens data --split test
	uv run buglens retrieve --system S1 --split test
	uv run buglens retrieve --system S2 --split test
	uv run buglens retrieve --system S3 --split test
	uv run buglens retrieve --system S4 --split test
	uv run buglens retrieve --system S5 --split test
	uv run buglens retrieve --system A1 --split test
	uv run buglens rerank --system S6 --split test
	uv run buglens llm --system S7 --split test
	uv run buglens rerank --system S6b --split test
	uv run buglens report

onboard:
	uv run buglens onboard --repo pallets/flask
	uv run buglens onboard --repo psf/requests
	uv run buglens onboard --repo django/django
	uv run buglens onboard-eval

demo:
	uv run buglens demo

# ---- research report + workbook (needs Microsoft Word/Excel for TOC refresh, recalculation, PDF) ----
research:
	uv run python scripts/research/collect.py
	uv run python scripts/research/figures.py
	uv run python scripts/research/report_numbers.py
	uv run --with openpyxl==3.1.5 python scripts/research/build_workbook.py
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/research/excel_recalc.ps1 -Path reports/research/BugLens_Research_Analysis.xlsx
	cd scripts/research && npm install --no-audit --no-fund && node build_report.js
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/research/word_export.ps1 -Path reports/research/BugLens_Research_Report.docx

# ---- stretch M10 ----
patches:
	uv run buglens llm --system S8 --split test
	uv run buglens patch --system S8 --limit 30

# Official SWE-bench Docker harness (runs in a Linux container via the Docker socket).
# NOT run automatically: pulls tens of GB of images and takes hours.
harness:
	powershell -NoProfile -ExecutionPolicy Bypass -File scripts/run_harness.ps1
