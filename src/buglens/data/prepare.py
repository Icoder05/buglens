"""`buglens data`: load a split, clone its repositories, build gold labels.

Concept: data preparation is a one-time, cached step. Gold labels are computed
once per instance from the patch and stored in `data/cache/labels/<split>.jsonl`;
every later stage (training pairs, LTR labels, metrics) reads that file and
never touches the patch again, which keeps the patch away from retrieval code.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from buglens.config import Config
from buglens.data.labels import label_instance, original_lines
from buglens.data.repos import ensure_clone, ensure_commit, read_files
from buglens.data.swebench import assert_no_leakage, load_split, repos_of
from buglens.schemas import GoldLabels, Instance
from buglens.utils import console, read_jsonl, summary, track, write_jsonl


def labels_path(cfg: Config, split: str) -> Path:
    return cfg.path("cache") / "labels" / f"{split}.jsonl"


def build_labels(cfg: Config, instances: list[Instance]) -> tuple[list[GoldLabels], list[str]]:
    labels, problems = [], []
    for inst in track(instances, "gold labels"):
        ensure_commit(cfg, inst.repo, inst.base_commit)
        paths = list(original_lines(inst.patch))
        sources = read_files(cfg, inst.repo, inst.base_commit, paths)
        c = cfg.chunking
        lab, probs = label_instance(inst, sources, c.max_chars, c.window_lines, c.window_overlap)
        labels.append(lab)
        problems.extend(f"{inst.instance_id}: {p}" for p in probs)
        if not lab.functions:
            problems.append(f"{inst.instance_id}: UNMAPPABLE (no gold functions)")
    return labels, problems


def load_labels(cfg: Config, split: str) -> dict[str, GoldLabels]:
    path = labels_path(cfg, split)
    if not path.exists():
        prepare_split(cfg, split)
    return {lab.instance_id: lab for lab in read_jsonl(path, GoldLabels)}


LABEL_CHECK_IDS = ("pallets__flask-4045", "psf__requests-2317", "django__django-11099")


def write_label_check(cfg: Config, instances: list[Instance], labels: list[GoldLabels]) -> Path:
    """M1 acceptance: patch next to derived labels for 3 instances, for a hand check."""
    by_id = {i.instance_id: i for i in instances}
    lab = {x.instance_id: x for x in labels}
    ids = [i for i in LABEL_CHECK_IDS if i in by_id] or [i.instance_id for i in instances[:3]]
    md = ["# Gold-label hand check (M1)", "",
          "For each instance, compare the patch with the derived labels: gold files = modified "
          "non-test files; gold functions = innermost chunk containing each removed line or "
          "insertion point (at `base_commit`). Mark ✅/❌.", ""]
    for iid in ids:
        md += [f"## {iid}", "", f"- base_commit: `{by_id[iid].base_commit}`",
               f"- gold files: {', '.join(f'`{f}`' for f in lab[iid].files)}",
               f"- gold functions: {', '.join(f'`{f}`' for f in lab[iid].functions)}",
               "- your check: ", "", "```diff", by_id[iid].patch.rstrip(), "```", ""]
    out = cfg.path("reports") / "label_check.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    return out


def prepare_split(cfg: Config, split: str) -> list[Instance]:
    instances = load_split(cfg, split)
    repos = repos_of(instances)
    console.print(f"{split}: {len(instances)} instances, {len(repos)} repos")
    for repo, n in sorted(Counter(i.repo for i in instances).items()):
        console.print(f"  {repo}: {n}")
    if split == "train":
        test_repos = set(repos_of(load_split(cfg, "test")))
        dev_repos = set(repos_of(load_split(cfg, "dev")))
        assert_no_leakage(set(repos), test_repos)
        assert_no_leakage(set(repos), dev_repos)
        summary("data", split=split, instances=len(instances), repos=len(repos),
                leakage="none")
        return instances
    for repo in repos:
        ensure_clone(cfg, repo)
    labels, problems = build_labels(cfg, instances)
    write_jsonl(labels_path(cfg, split), labels)
    log = labels_path(cfg, split).with_suffix(".problems.txt")
    log.write_text("\n".join(problems), encoding="utf-8")
    if split == "test" and not (cfg.path("reports") / "label_check.md").exists():
        console.print(f"label hand-check sheet: {write_label_check(cfg, instances, labels)}")
    unmappable = sum(not lab.functions for lab in labels)
    summary("data", split=split, instances=len(instances), repos=len(repos),
            unmappable=unmappable, problems_log=str(log))
    return instances
