"""BugLens command-line interface (PRD Section 10).

Concept: one CLI command per pipeline stage, each reading and writing files on
disk (data -> index -> retrieve -> rerank -> eval -> report). Stages communicate
only through cached artifacts, so any stage can be rerun alone, the expensive
ones (GPU fine-tuning, LLM calls) run once and are reused, and `make reproduce`
rebuilds every number from the cache in minutes. Commands not built yet print
the milestone that will implement them.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

app = typer.Typer(
    help="BugLens: bug localization on SWE-bench Lite + codebase onboarding.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

ConfigOpt = Annotated[Path, typer.Option("--config", help="Path to config YAML.")]
RepoOpt = Annotated[str, typer.Option("--repo", help="GitHub repo, e.g. pallets/flask.")]
DEFAULT_CFG = Path("configs/default.yaml")


class Split(StrEnum):
    test = "test"
    dev = "dev"
    train = "train"


class Retriever(StrEnum):
    bm25 = "bm25"
    dense = "dense"


def _todo(milestone: str) -> None:
    console.print(f"[yellow]Not implemented yet[/yellow] (planned for {milestone}).")
    raise typer.Exit(code=1)


# ---------------- Localize ----------------
@app.command()
def data(split: Annotated[Split, typer.Option()] = Split.test, config: ConfigOpt = DEFAULT_CFG):
    """Load SWE-bench split, clone repos, build gold labels."""
    _todo("M1")


@app.command()
def index(
    split: Annotated[Split, typer.Option()] = Split.test,
    retriever: Annotated[Retriever, typer.Option()] = Retriever.bm25,
    model: Annotated[str | None, typer.Option(help="Model id or local path.")] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Build per-commit BM25 or dense indexes."""
    _todo("M2/M3")


@app.command()
def retrieve(
    system: Annotated[str, typer.Option(help="S1..S5 or A1")],
    split: Annotated[Split, typer.Option()] = Split.test,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Run a retrieval system and write runs/<system>_<split>.jsonl."""
    _todo("M2/M3/M5")


@app.command()
def pairs(config: ConfigOpt = DEFAULT_CFG):
    """Build contrastive training pairs from SWE-bench train."""
    _todo("M4")


@app.command()
def finetune(config: ConfigOpt = DEFAULT_CFG):
    """Fine-tune the dense encoder (usually on Kaggle)."""
    _todo("M4")


@app.command()
def rerank(
    system: Annotated[str, typer.Option(help="S6 or S6b")],
    split: Annotated[Split, typer.Option()] = Split.test,
    config: ConfigOpt = DEFAULT_CFG,
):
    """LambdaRank reranking with leave-one-repo-out CV."""
    _todo("M6/M8")


@app.command()
def llm(
    system: Annotated[str, typer.Option(help="S7 or S8")],
    split: Annotated[Split, typer.Option()] = Split.test,
    limit: Annotated[int | None, typer.Option()] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Gemini reranker over the top-10 candidates."""
    _todo("M8")


@app.command(name="eval")
def eval_(
    system: Annotated[str, typer.Option()],
    split: Annotated[Split, typer.Option()] = Split.test,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Compute file/function metrics for one system."""
    _todo("M2")


@app.command()
def report(config: ConfigOpt = DEFAULT_CFG):
    """Write reports/results.md, results.csv and figures."""
    _todo("M9")


@app.command()
def errors(
    system: Annotated[str, typer.Option()] = "S6",
    n: Annotated[int, typer.Option()] = 20,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Dump failure cases to reports/error_analysis.md."""
    _todo("M9")


# ---------------- Onboard ----------------
@app.command()
def analyze(
    repo: RepoOpt,
    commit: Annotated[str | None, typer.Option()] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Extract static facts and build import/inheritance/call graphs."""
    _todo("M5")


@app.command()
def diagrams(
    repo: RepoOpt,
    package: Annotated[str | None, typer.Option()] = None,
    module: Annotated[str | None, typer.Option()] = None,
    entry: Annotated[str | None, typer.Option()] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Render block / package / class / call-flow diagrams (SVG + Mermaid)."""
    _todo("M7")


@app.command()
def summarize(
    repo: RepoOpt,
    max_packages: Annotated[int, typer.Option()] = 30,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Grounded LLM package summaries + repo overview."""
    _todo("M8")


@app.command()
def guide(repo: RepoOpt, config: ConfigOpt = DEFAULT_CFG):
    """Assemble the cited onboarding guide."""
    _todo("M8")


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help='e.g. "where are blueprints registered?"')],
    repo: RepoOpt,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Answer "where is X?" with path:line citations."""
    _todo("M9")


@app.command()
def onboard(repo: RepoOpt, config: ConfigOpt = DEFAULT_CFG):
    """analyze + diagrams + summarize + guide for one repo."""
    _todo("M8")


@app.command(name="onboard-eval")
def onboard_eval(config: ConfigOpt = DEFAULT_CFG):
    """Faithfulness, citation validity, rating sheet, QA Acc@5."""
    _todo("M9")


@app.command()
def demo(config: ConfigOpt = DEFAULT_CFG):
    """Launch the Gradio demo (Localize + Onboard tabs)."""
    _todo("M9")


if __name__ == "__main__":
    app()
