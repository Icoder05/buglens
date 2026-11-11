# Changelog

All deviations from the PRD are recorded here, with the reason.

## M0 — Skeleton (2026-10-20)

- Added: project skeleton, `configs/default.yaml`, `configs/experiments.yaml`, pydantic schemas
  (PRD Section 6, verbatim), Typer CLI with every Section 10 command stubbed, Makefile, smoke tests.
- Versions pinned exactly in `pyproject.toml` (resolved by `uv lock` on 2026-10-20, Python 3.11.15).
- Deviation: added `pyarrow` as an explicit dependency (needed for Parquet pairs, FR-T1).
- Deviation: added `make lint` target (ruff) alongside the PRD's targets.
- Note: `llm.model` in `default.yaml` is a placeholder (`gemini-2.5-flash`); it will be verified
  against the currently free Flash model before M8 (PRD Section 17.2).
- Note: system Graphviz `dot` is not yet installed on the dev machine; needed from M7.
