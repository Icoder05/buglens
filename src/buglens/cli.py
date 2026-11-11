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


def _cfg(path: Path):
    from buglens.config import PROJECT_ROOT, load_config

    if not path.is_absolute() and not path.exists():
        path = PROJECT_ROOT / path
    return load_config(path)


# ---------------- Localize ----------------
@app.command()
def data(split: Annotated[Split, typer.Option()] = Split.test, config: ConfigOpt = DEFAULT_CFG):
    """Load SWE-bench split, clone repos, build gold labels."""
    from buglens.data.prepare import prepare_split

    prepare_split(_cfg(config), split.value)


@app.command()
def index(
    split: Annotated[Split, typer.Option()] = Split.test,
    retriever: Annotated[Retriever, typer.Option()] = Retriever.bm25,
    model: Annotated[str | None, typer.Option(help="Model id or local path.")] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Build per-commit BM25 or dense indexes."""
    from buglens.retrieval.index import build_index

    build_index(_cfg(config), split.value, retriever.value, model)


@app.command()
def retrieve(
    system: Annotated[str, typer.Option(help="S1..S5 or A1")],
    split: Annotated[Split, typer.Option()] = Split.test,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Run a retrieval system and write runs/<system>_<split>.jsonl."""
    from buglens.retrieval.run import run_retrieval

    run_retrieval(_cfg(config), system, split.value)


@app.command()
def pairs(config: ConfigOpt = DEFAULT_CFG):
    """Build contrastive training pairs from SWE-bench train."""
    from buglens.training.build_pairs import build_pairs

    build_pairs(_cfg(config))


@app.command()
def finetune(config: ConfigOpt = DEFAULT_CFG):
    """Fine-tune the dense encoder (usually on Kaggle)."""
    from buglens.training.finetune import finetune as run_finetune

    run_finetune(_cfg(config))


@app.command()
def rerank(
    system: Annotated[str, typer.Option(help="S6 or S6b")],
    split: Annotated[Split, typer.Option()] = Split.test,
    config: ConfigOpt = DEFAULT_CFG,
):
    """LambdaRank reranking with leave-one-repo-out CV."""
    from buglens.rerank.ltr import rerank as run_rerank

    run_rerank(_cfg(config), system, split.value)


@app.command()
def llm(
    system: Annotated[str, typer.Option(help="S7 or S8")],
    split: Annotated[Split, typer.Option()] = Split.test,
    limit: Annotated[int | None, typer.Option()] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Gemini reranker over the top-10 candidates."""
    from buglens.llm.rerank import llm_rerank

    llm_rerank(_cfg(config), system, split.value, limit)


@app.command()
def patch(
    system: Annotated[str, typer.Option(help="Localizer to use (S8, falls back to S6)")] = "S8",
    limit: Annotated[int, typer.Option()] = 30,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Stretch M10: Gemini patches from localized functions (SWE-bench predictions)."""
    from buglens.llm.patch import generate_patches

    generate_patches(_cfg(config), system, limit)


@app.command(name="eval")
def eval_(
    system: Annotated[str, typer.Option()],
    split: Annotated[Split, typer.Option()] = Split.test,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Compute file/function metrics for one system."""
    from buglens.eval.evaluate import eval_system

    eval_system(_cfg(config), system, split.value)


@app.command()
def report(config: ConfigOpt = DEFAULT_CFG):
    """Write reports/results.md, results.csv and figures."""
    from buglens.eval.report import make_report

    make_report(_cfg(config))


@app.command()
def errors(
    system: Annotated[str, typer.Option()] = "S6",
    n: Annotated[int, typer.Option()] = 20,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Dump failure cases to reports/error_analysis.md."""
    from buglens.eval.report import error_dump

    error_dump(_cfg(config), system, n)


# ---------------- Onboard ----------------
@app.command()
def analyze(
    repo: RepoOpt,
    commit: Annotated[str | None, typer.Option()] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Extract static facts and build import/inheritance/call graphs."""
    from buglens.onboard.pipeline import run_analyze

    run_analyze(_cfg(config), repo, commit)


@app.command()
def diagrams(
    repo: RepoOpt,
    package: Annotated[str | None, typer.Option()] = None,
    module: Annotated[str | None, typer.Option()] = None,
    entry: Annotated[str | None, typer.Option()] = None,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Render block / package / class / call-flow diagrams (SVG + Mermaid)."""
    from buglens.onboard.pipeline import run_diagrams

    run_diagrams(_cfg(config), repo, None, package, module, entry)


@app.command()
def summarize(
    repo: RepoOpt,
    max_packages: Annotated[int, typer.Option()] = 30,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Grounded LLM package summaries + repo overview."""
    from buglens.onboard.summarize import summarize_repo

    summarize_repo(_cfg(config), repo, max_packages)


@app.command()
def guide(repo: RepoOpt, config: ConfigOpt = DEFAULT_CFG):
    """Assemble the cited onboarding guide."""
    from buglens.onboard.pipeline import run_guide

    run_guide(_cfg(config), repo)


@app.command()
def ask(
    question: Annotated[str, typer.Argument(help='e.g. "where are blueprints registered?"')],
    repo: RepoOpt,
    config: ConfigOpt = DEFAULT_CFG,
):
    """Answer "where is X?" with path:line citations."""
    from rich.markdown import Markdown

    from buglens.onboard.ask import ask as run_ask

    ans = run_ask(_cfg(config), repo, question)
    console.print(Markdown(ans.markdown()))


@app.command()
def onboard(repo: RepoOpt, config: ConfigOpt = DEFAULT_CFG):
    """analyze + diagrams + summarize + guide for one repo."""
    from buglens.onboard.pipeline import run_onboard

    run_onboard(_cfg(config), repo)


@app.command(name="onboard-eval")
def onboard_eval(config: ConfigOpt = DEFAULT_CFG):
    """Faithfulness, citation validity, rating sheet, QA Acc@5."""
    from buglens.eval.onboard_eval import onboard_eval as run_onboard_eval

    run_onboard_eval(_cfg(config))


@app.command()
def demo(config: ConfigOpt = DEFAULT_CFG):
    """Launch the Gradio demo (Localize + Onboard tabs)."""
    from buglens.demo.app import main

    main()


if __name__ == "__main__":
    app()
