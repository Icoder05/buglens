"""M0 smoke tests: config loads, schemas validate, CLI lists every PRD command."""

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from buglens.cli import app
from buglens.config import load_config, load_experiments
from buglens.schemas import Chunk, Instance, RankedResult

PRD_COMMANDS = [
    "data", "index", "retrieve", "pairs", "finetune", "rerank", "llm", "eval", "report",
    "errors", "analyze", "diagrams", "summarize", "guide", "ask", "onboard", "onboard-eval",
    "demo",
]


def test_config_loads():
    cfg = load_config()
    assert cfg.seed == 42
    assert cfg.retrieval.rrf_k == 60
    assert cfg.analysis.max_nodes == 15


def test_experiments_define_all_systems():
    exp = load_experiments()
    assert set(exp.systems) >= {"S1", "S2", "S3", "S4", "S5", "S6", "S6b", "S7", "S8", "A1"}
    assert ["S6b", "S6"] in exp.comparisons


def test_schemas_validate():
    Instance(instance_id="a__b-1", repo="a/b", base_commit="abc", problem_statement="x",
             patch="", split="test")
    with pytest.raises(ValidationError):
        Instance(instance_id="x", repo="a/b", base_commit="c", problem_statement="",
                 patch="", split="validation")
    with pytest.raises(ValidationError):
        Chunk(chunk_id="p::f", path="p", qualname="f", kind="lambda", start_line=1,
              end_line=2, text="", text_sha1="")
    r = RankedResult(instance_id="x", system="S1", functions=[], files=[], seconds=0.1)
    assert RankedResult.model_validate_json(r.model_dump_json()) == r


def test_cli_help_lists_commands():
    result = CliRunner().invoke(app, ["--help"], terminal_width=200)
    assert result.exit_code == 0
    for cmd in PRD_COMMANDS:
        assert cmd in result.output, cmd
