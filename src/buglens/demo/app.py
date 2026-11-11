"""Gradio demo: Localize tab + Onboard tab — PRD Section 11.

Concept: the demo is a thin view over cached artifacts. The Localize tab shows
a system's ranked functions for a SWE-bench Lite instance (or for an issue you
paste, ranked live against a pre-indexed repo) and colours the predicted
packages on the architecture diagram. The Onboard tab browses the generated
diagrams and guide and offers "Ask the codebase". Everything runs on CPU; the
Gemini key is optional (without it, Ask returns retrieved chunks only).
"""

from __future__ import annotations

import json
import os
import re
import time

import gradio as gr
import numpy as np

from buglens.config import Config, load_config
from buglens.data.repos import read_files
from buglens.schemas import Candidate, RankedResult
from buglens.utils import read_jsonl, repo_slug

DEVICE = os.environ.get("BUGLENS_DEVICE", "cpu")
_BASE_ENCODERS: dict[str, object] = {}


# ------------------------------------------------------------------ helpers
def svg_html(svg: str) -> str:
    if not svg:
        return "<p><em>No diagram.</em></p>"
    svg = re.sub(r"^<\?xml[^>]*>\s*", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>\s*", "", svg)
    # Graphviz writes fixed width/height in pt; drop them so the viewBox scales to the page.
    svg = re.sub(r'(<svg[^>]*?)\swidth="[^"]*"\s+height="[^"]*"',
                 r'\1 style="width:100%;height:auto;max-height:900px"', svg, count=1)
    return f'<div style="overflow:auto;background:white">{svg}</div>'


def read_svg(path) -> str:
    return path.read_text(encoding="utf-8") if path and path.exists() else ""


class DemoState:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.runs: dict[str, dict[str, RankedResult]] = {}
        from buglens.data.swebench import load_split

        self.instances = {i.instance_id: i for i in load_split(cfg, "test")}
        self.labels = None

    def run(self, system: str) -> dict[str, RankedResult]:
        if system not in self.runs:
            path = self.cfg.path("runs") / f"{system}_test.jsonl"
            self.runs[system] = ({r.instance_id: r for r in read_jsonl(path, RankedResult)}
                                 if path.exists() else {})
        return self.runs[system]

    def gold(self, iid: str):
        if self.labels is None:
            from buglens.data.prepare import load_labels

            self.labels = load_labels(self.cfg, "test")
        return self.labels.get(iid)

    def systems(self) -> list[str]:
        return [s for s in ("S1", "S5", "S6")
                if (self.cfg.path("runs") / f"{s}_test.jsonl").exists()]

    def onboard_repos(self) -> list[str]:
        return [r for r in self.cfg.onboard.repos
                if (self.cfg.path("onboarding") / repo_slug(r) / "bundle.json").exists()]


def _table(result: RankedResult, gold_funcs: set[str], k: int = 10) -> list[list]:
    rows = []
    for c in sorted(result.functions, key=lambda c: c.rank)[:k]:
        score = next((c.scores[s] for s in ("llm", "ltr", "rrf", "dense_ft", "dense", "bm25")
                      if s in c.scores), 0.0)
        rows.append([c.rank, c.chunk_id, round(float(score), 4),
                     "✅" if c.chunk_id in gold_funcs else ""])
    return rows


def chunk_source(cfg: Config, repo: str, commit: str, chunk_id: str) -> str:
    if not chunk_id:
        return ""
    from buglens.chunking.corpus import load_corpus

    corpus = load_corpus(cfg, repo, commit)
    chunk = next((c for c in corpus.chunks if c.chunk_id == chunk_id), None)
    if chunk is None:
        return f"# {chunk_id} not found"
    text = read_files(cfg, repo, commit, [chunk.path]).get(chunk.path, "")
    lines = text.splitlines()[chunk.start_line - 1:chunk.end_line]
    return f"# {chunk.path}:{chunk.start_line}-{chunk.end_line}\n" + "\n".join(lines)


# ------------------------------------------------------------------ live ranking
def live_rank(cfg: Config, repo: str, issue: str, system: str) -> RankedResult:
    """Rank an arbitrary issue against a pre-indexed repo at its onboarding commit."""
    from buglens.analysis.repo_analysis import pagerank_by_path
    from buglens.chunking.corpus import load_corpus
    from buglens.onboard.ask import get_encoder, hybrid_scores
    from buglens.onboard.summarize import onboarding_commit
    from buglens.retrieval.fusion import files_from_chunks
    from buglens.retrieval.run import build_candidates

    t0 = time.perf_counter()
    commit = onboarding_commit(cfg, repo)
    corpus = load_corpus(cfg, repo, commit)
    if system == "S1":
        comp = hybrid_scores(cfg, corpus, issue, None)
    else:
        enc = get_encoder(cfg, DEVICE)
        comp = hybrid_scores(cfg, corpus, issue, enc)
        comp["dense_ft"] = comp.pop("dense")
    cands = build_candidates(corpus, comp, cfg.retrieval.top_n, cfg.retrieval.rrf_k)
    if system == "S6":
        cands = _live_ltr(cfg, corpus, issue, cands, comp, pagerank_by_path(cfg, repo, commit))
    return RankedResult(instance_id="(pasted issue)", system=system, functions=cands,
                        files=files_from_chunks([c.path for c in cands]),
                        seconds=time.perf_counter() - t0)


def _live_ltr(cfg, corpus, issue, cands, comp, pr) -> list[Candidate]:
    import lightgbm as lgb

    from buglens.rerank.features import BASE_FEATURES, candidate_features
    from buglens.retrieval.dense import DenseEncoder, faiss_scores
    from buglens.schemas import Instance

    model_path = cfg.path("models") / "ltr_S6.txt"
    if not model_path.exists():
        raise gr.Error("S6 model not trained yet (run `buglens rerank --system S6`).")
    r = cfg.retrieval
    model_id = r.dense_model_fallback if r.use_fallback_model else r.dense_model
    if model_id not in _BASE_ENCODERS:
        _BASE_ENCODERS[model_id] = DenseEncoder(cfg, model_id, device=DEVICE)
    base = _BASE_ENCODERS[model_id]
    comp = dict(comp)
    comp["dense"] = faiss_scores(base.corpus_matrix(corpus), base.encode_queries([issue])[0])
    inst = Instance(instance_id="live", repo=corpus.repo, base_commit=corpus.commit,
                        problem_statement=issue, patch="", split="test")
    feats = candidate_features(inst, corpus, cands, comp, pr)
    x = np.array([[f[k] for k in BASE_FEATURES] for f in feats], dtype=float)
    scores = lgb.Booster(model_file=str(model_path)).predict(x)
    order = sorted(range(len(cands)), key=lambda i: (-scores[i], cands[i].rank))
    out = []
    for rank, i in enumerate(order, start=1):
        c = cands[i]
        out.append(Candidate(chunk_id=c.chunk_id, path=c.path,
                             scores={**c.scores, "ltr": float(scores[i])}, rank=rank))
    return out


# ------------------------------------------------------------------ app
def build_app(cfg: Config | None = None) -> gr.Blocks:
    cfg = cfg or load_config()
    st = DemoState(cfg)
    systems = st.systems() or ["S1"]
    instance_ids = sorted(st.run(systems[0]).keys()) or sorted(st.instances)
    # Open on a small repo so the first page load is fast (flask analysis is ~1 s).
    default_iid = next((i for i in instance_ids if i.startswith("pallets__flask")),
                       instance_ids[0] if instance_ids else None)
    repos = st.onboard_repos()

    def localize(iid: str, system: str):
        if not iid:
            return [], gr.update(choices=[], value=None), "", "<p>Select an instance.</p>", ""
        res = st.run(system).get(iid)
        if res is None:
            raise gr.Error(f"No {system} result for {iid}.")
        inst = st.instances[iid]
        gold = st.gold(iid)
        from buglens.onboard.highlight import highlighted_block

        svg, _, marks = highlighted_block(cfg, inst.repo, inst.base_commit, res, gold)
        table = _table(res, set(gold.functions) if gold else set())
        ids = [row[1] for row in table]
        info = (f"**{iid}** · {inst.repo} @ `{inst.base_commit[:10]}` · gold files: "
                + ", ".join(f"`{f}`" for f in (gold.files if gold else [])))
        return (table, gr.update(choices=ids, value=ids[0] if ids else None),
                chunk_source(cfg, inst.repo, inst.base_commit, ids[0]) if ids else "",
                svg_html(svg), info + "\n\n" + inst.problem_statement[:3000])

    def show_source(iid: str, chunk_id: str):
        if not iid or not chunk_id:
            return ""
        inst = st.instances[iid]
        return chunk_source(cfg, inst.repo, inst.base_commit, chunk_id)

    def localize_pasted(repo: str, issue: str, system: str):
        if not repo or not issue.strip():
            raise gr.Error("Pick a pre-indexed repo and paste an issue.")
        from buglens.onboard.highlight import highlighted_block
        from buglens.onboard.summarize import onboarding_commit

        res = live_rank(cfg, repo, issue, system)
        commit = onboarding_commit(cfg, repo)
        svg, _, _ = highlighted_block(cfg, repo, commit, res, None)
        table = _table(res, set())
        src = chunk_source(cfg, repo, commit, table[0][1]) if table else ""
        return table, src, svg_html(svg)

    def onboard_repo(repo: str):
        if not repo:
            return "", gr.update(), gr.update(), gr.update(), ""
        base = cfg.path("onboarding") / repo_slug(repo)
        bundle = json.loads((base / "bundle.json").read_text(encoding="utf-8"))
        guide = (base / "guide.md").read_text(encoding="utf-8")
        guide = re.sub(r"!\[[^\]]*\]\(diagrams/[^)]*\)", "_(diagram shown above)_", guide)
        guide = re.sub(r"\]\((diagrams/[^)]*)\)", r"](#)", guide)
        pk = sorted(bundle["package_diagrams"])
        mods = sorted(bundle["class_diagrams"])
        eps = sorted(bundle["callflow_diagrams"])
        return (svg_html(read_svg(base / bundle["block_svg"])),
                gr.update(choices=pk, value=pk[0] if pk else None),
                gr.update(choices=mods, value=mods[0] if mods else None),
                gr.update(choices=eps, value=eps[0] if eps else None), guide)

    def diagram_of(repo: str, kind: str, key: str):
        if not repo or not key:
            return "<p><em>No diagram.</em></p>"
        base = cfg.path("onboarding") / repo_slug(repo)
        bundle = json.loads((base / "bundle.json").read_text(encoding="utf-8"))
        rel = bundle[kind].get(key)
        return svg_html(read_svg(base / rel)) if rel else "<p><em>No diagram.</em></p>"

    def ask_box(repo: str, question: str):
        if not repo or not question.strip():
            raise gr.Error("Pick a repo and type a question.")
        from buglens.onboard.ask import ask, get_encoder

        ans = ask(cfg, repo, question, encoder=get_encoder(cfg, DEVICE))
        return ans.markdown(), svg_html(ans.neighbourhood_svg)

    with gr.Blocks(title="BugLens") as app:
        gr.Markdown("# BugLens — bug localization + codebase onboarding\n"
                    "Static-analysis diagrams (never drawn by an LLM) and cited answers.")
        with gr.Tab("Localize"):
            with gr.Row():
                iid = gr.Dropdown(instance_ids, label="SWE-bench Lite instance",
                                  value=default_iid)
                system = gr.Radio(systems, value=systems[-1], label="System")
            info = gr.Markdown()
            with gr.Row():
                table = gr.Dataframe(headers=["rank", "chunk", "score", "gold"],
                                     label="Top-10 predicted functions", interactive=False,
                                     column_widths=["8%", "64%", "16%", "12%"], wrap=True)
                with gr.Column():
                    pick = gr.Dropdown([], label="Show source of")
                    code = gr.Code(language="python", label="Source")
            arch = gr.HTML(label="Architecture (predicted packages highlighted)")
            with gr.Accordion("…or paste an issue for a pre-indexed repo", open=False):
                with gr.Row():
                    p_repo = gr.Dropdown(repos, label="Repository",
                                         value=repos[0] if repos else None)
                    p_sys = gr.Radio(["S1", "S5", "S6"], value="S5", label="System")
                p_issue = gr.Textbox(lines=6, label="Issue text")
                p_btn = gr.Button("Localize")
                p_table = gr.Dataframe(headers=["rank", "chunk", "score", "gold"],
                                       interactive=False,
                                       column_widths=["8%", "64%", "16%", "12%"], wrap=True)
                p_code = gr.Code(language="python")
                p_arch = gr.HTML()
            iid.change(localize, [iid, system], [table, pick, code, arch, info])
            system.change(localize, [iid, system], [table, pick, code, arch, info])
            pick.change(show_source, [iid, pick], code)
            p_btn.click(localize_pasted, [p_repo, p_issue, p_sys], [p_table, p_code, p_arch])
        with gr.Tab("Onboard"):
            repo = gr.Dropdown(repos, label="Repository", value=repos[0] if repos else None)
            block = gr.HTML(label="Architecture")
            with gr.Row():
                pkg = gr.Dropdown([], label="Package drill-down")
                mod = gr.Dropdown([], label="Class diagram (module)")
                ep = gr.Dropdown([], label="Call flow (entry point)")
            sub = gr.HTML()
            with gr.Row():
                question = gr.Textbox(label="Ask the codebase",
                                      placeholder="where are blueprints registered?")
                ask_btn = gr.Button("Ask")
            answer = gr.Markdown()
            neigh = gr.HTML()
            guide = gr.Markdown()
            repo.change(onboard_repo, repo, [block, pkg, mod, ep, guide])
            pkg.change(lambda r, k: diagram_of(r, "package_diagrams", k), [repo, pkg], sub)
            mod.change(lambda r, k: diagram_of(r, "class_diagrams", k), [repo, mod], sub)
            ep.change(lambda r, k: diagram_of(r, "callflow_diagrams", k), [repo, ep], sub)
            ask_btn.click(ask_box, [repo, question], [answer, neigh])
        app.load(localize, [iid, system], [table, pick, code, arch, info])
        app.load(onboard_repo, repo, [block, pkg, mod, ep, guide])
    app.queue(default_concurrency_limit=4)  # tabs load in parallel instead of one by one
    return app


def main() -> None:
    from buglens.onboard.diagrams import ensure_dot

    ensure_dot()
    build_app().launch()


if __name__ == "__main__":
    main()
