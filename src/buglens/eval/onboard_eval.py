"""Evaluate the onboarding artifacts — FR-O1..O5.

Concept: onboarding output has no gold labels, so we measure what *can* be
measured objectively and make the rest cheap to judge by hand:
- diagram faithfulness: % of diagram nodes/edges re-derived from the graphs
  (by construction 100%; reported so a regression would be visible);
- citation validity: % of LLM sentences kept vs dropped by the validator;
- a human rating sheet (correct / partly / wrong) for 30 package summaries,
  which this command reads back once filled in;
- QA Acc@5: does the Ask retriever surface an acceptable file in its top 5?
No claim is made about onboarding *speed* (that would need a user study).
"""

from __future__ import annotations

import json

import pandas as pd
import yaml

from buglens.config import PROJECT_ROOT, Config
from buglens.onboard.summarize import load_summaries, onboarding_dir
from buglens.utils import console, md_table, summary

RATING_COLUMNS = ["repo", "package", "summary", "citations", "rating", "note"]
VALID_RATINGS = ("correct", "partly", "wrong")


def faithfulness(cfg: Config, repos: list[str]) -> list[dict]:
    rows = []
    for repo in repos:
        f = onboarding_dir(cfg, repo) / "diagrams" / "faithfulness.json"
        if not f.exists():
            continue
        data = json.loads(f.read_text())
        reps = [v for k, v in data.items() if isinstance(v, dict) and "nodes" in v]
        total = sum(r["nodes"] + r["edges"] for r in reps)
        ok = sum(r["nodes_verified"] + r["edges_verified"] for r in reps)
        rows.append({"repo": repo, "diagrams": len(reps), "elements": total,
                     "verified_pct": round(100.0 * ok / max(total, 1), 2)})
    return rows


def citation_validity(cfg: Config, repos: list[str]) -> list[dict]:
    rows = []
    for repo in repos:
        s = load_summaries(cfg, repo)
        if not s:
            continue
        st = s["stats"]
        ov = st.get("overview", {})
        total = st["sentences"] + ov.get("sentences", 0)
        kept = st["kept"] + ov.get("kept", 0)
        rows.append({"repo": repo, "packages": st["packages"], "sentences": total,
                     "kept": kept, "dropped": total - kept,
                     "kept_pct": round(100.0 * kept / max(total, 1), 1),
                     "valid_citation_pct": round(100.0 * st["valid_citations"]
                                                 / max(st["citations"], 1), 1),
                     "complete": s.get("complete", True)})
    return rows


def rating_sheet(cfg: Config, repos: list[str], per_repo: int = 10) -> pd.DataFrame | None:
    """Create reports/summary_ratings.csv (never overwrites ratings already filled in)."""
    path = cfg.path("reports") / "summary_ratings.csv"
    if path.exists():
        return pd.read_csv(path, keep_default_na=False)
    rows = []
    for repo in repos:
        s = load_summaries(cfg, repo)
        if not s:
            continue
        for p in s["packages"][:per_repo]:
            if not p["sentences"]:
                continue
            rows.append({"repo": repo, "package": p["package"],
                         "summary": " ".join(x["text"] for x in p["sentences"]),
                         "citations": "; ".join(f"{c['path']}:{c['line']}"
                                                for x in p["sentences"] for c in x["citations"]),
                         "rating": "", "note": ""})
    if not rows:
        return None
    df = pd.DataFrame(rows, columns=RATING_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    console.print(f"rating sheet created: {path} (fill `rating` with correct/partly/wrong)")
    return df


def rating_summary(df: pd.DataFrame | None) -> dict:
    if df is None or df.empty:
        return {"rows": 0, "rated": 0}
    rated = df[df["rating"].astype(str).str.strip().str.lower().isin(VALID_RATINGS)]
    counts = rated["rating"].str.strip().str.lower().value_counts()
    out = {"rows": len(df), "rated": len(rated)}
    for r in VALID_RATINGS:
        out[r] = round(100.0 * counts.get(r, 0) / max(len(rated), 1), 1)
    return out


def qa_accuracy(cfg: Config) -> list[dict] | None:
    path = cfg.path("data") / "onboard_qa.yaml"
    if not path.exists():
        path = PROJECT_ROOT / "configs" / "onboard_qa.yaml"
    if not path.exists():
        return None
    from buglens.chunking.corpus import load_corpus
    from buglens.onboard.ask import get_encoder, hybrid_search
    from buglens.onboard.summarize import onboarding_commit

    qa = yaml.safe_load(path.read_text(encoding="utf-8"))
    encoder = get_encoder(cfg)
    rows = []
    for repo, items in qa.items():
        corpus = load_corpus(cfg, repo, onboarding_commit(cfg, repo))
        for item in items:
            chunks = hybrid_search(cfg, corpus, item["q"], cfg.retrieval.top_n, encoder)
            files = list(dict.fromkeys(c.path for c in chunks))[:5]
            rows.append({"repo": repo, "question": item["q"],
                         "hit@5": int(bool(set(files) & set(item["files"]))),
                         "top5": ", ".join(files)})
    return rows


def onboard_eval(cfg: Config) -> str:
    repos = list(cfg.onboard.repos)
    faith = faithfulness(cfg, repos)
    cites = citation_validity(cfg, repos)
    sheet = rating_sheet(cfg, repos)
    ratings = rating_summary(sheet)
    qa = qa_accuracy(cfg)

    md = ["# Onboarding evaluation", "",
          "No claim is made about onboarding speed (no user study).", "",
          "## FR-O1 Diagram faithfulness", "",
          "Share of diagram nodes and edges re-derived from the static-analysis graphs.", ""]
    md += [md_table(faith) if faith else "_No diagrams yet._", ""]
    md += ["## FR-O2 Citation validity", "",
           "Sentences kept/dropped by the strict citation validator.", ""]
    md += [md_table(cites) if cites else "_No summaries yet (needs GEMINI_API_KEY)._", ""]
    md += ["## FR-O3 Human rating of package summaries", "",
           "Sheet: `reports/summary_ratings.csv` (fill `rating` with correct / partly / wrong, "
           "then rerun `buglens onboard-eval`). Single rater; the `note` column says who "
           "rated (Claude, pending the author's confirmation).", ""]
    if ratings.get("rated"):
        md.append(f"Rated {ratings['rated']}/{ratings['rows']}: correct {ratings['correct']}%, "
                  f"partly {ratings['partly']}%, wrong {ratings['wrong']}%.")
    else:
        md.append(f"_Not rated yet ({ratings.get('rows', 0)} rows in the sheet)._")
    md += ["", "## FR-O4 Ask-the-codebase retrieval (QA file Acc@5)", ""]
    if qa:
        qdf = pd.DataFrame(qa)
        md.append(f"Overall Acc@5: **{qdf['hit@5'].mean():.3f}** ({qdf['hit@5'].sum()}/"
                  f"{len(qdf)}).")
        per_repo = [{"repo": r, "acc@5": round(g["hit@5"].mean(), 3), "questions": len(g)}
                    for r, g in qdf.groupby("repo")]
        md += ["", md_table(per_repo), "", md_table(qa)]
    else:
        md.append("_No QA set found._")
    text = "\n".join(md) + "\n"
    out = cfg.path("reports") / "onboarding_eval.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    summary("onboard-eval", repos=len(faith), out=str(out),
            qa_acc5=f"{pd.DataFrame(qa)['hit@5'].mean():.3f}" if qa else "n/a")
    return text
