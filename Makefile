# BugLens — make setup | test | lint | reproduce | onboard | demo
# Recipes are single commands so they work with both sh and cmd.exe make shells.

ONBOARD_REPOS = pallets/flask psf/requests django/django

.PHONY: setup test lint reproduce onboard demo

setup:
	uv sync

test:
	uv run pytest

lint:
	uv run ruff check src tests

reproduce:
	uv run buglens data --split test
	uv run buglens data --split dev
	uv run buglens retrieve --system S1 --split test
	uv run buglens retrieve --system S2 --split test
	uv run buglens retrieve --system S3 --split test
	uv run buglens retrieve --system S4 --split test
	uv run buglens retrieve --system S5 --split test
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
