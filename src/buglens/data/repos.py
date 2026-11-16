"""Git repository cache: clone once, read any file at any commit without checkout.

Concept: SWE-bench needs the repository *as it was* at each instance's
`base_commit`, and one repo (django) has 114 different commits. Checking out
each commit would be slow and racy. Instead we ask git's object database
directly: `git ls-tree -r -l <commit>` lists every file (with blob id and size)
in that snapshot, and `git cat-file --batch` streams many blobs in one process.
Blob ids are content hashes, so an unchanged file has the same blob id in every
commit; downstream caches (chunks, facts) are keyed by blob id and reused.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from buglens.config import Config
from buglens.utils import compile_patterns, console, matches_any, repo_slug


@dataclass(frozen=True)
class TreeEntry:
    path: str
    blob: str
    size: int


def _git(repo_dir: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    proc = subprocess.run(
        ["git", "-c", "core.longpaths=true", *args],
        cwd=repo_dir,
        input=input_bytes,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo_dir}: {proc.stderr.decode()}")
    return proc.stdout


def repo_dir(cfg: Config, repo: str) -> Path:
    return cfg.path("repos") / repo_slug(repo)


def ensure_clone(cfg: Config, repo: str) -> Path:
    """Full clone (all history, no working tree) into data/repos/<owner>__<name>."""
    target = repo_dir(cfg, repo)
    if (target / "HEAD").exists() or (target / ".git").exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"cloning {repo} ...")
    tmp = target.with_name(target.name + ".partial")
    if tmp.exists():
        import shutil

        shutil.rmtree(tmp)
    subprocess.run(
        ["git", "-c", "core.longpaths=true", "clone", "--bare", "--quiet",
         f"https://github.com/{repo}.git", str(tmp)],
        check=True,
    )
    tmp.rename(target)
    return target


def ensure_commit(cfg: Config, repo: str, commit: str) -> None:
    """Fetch a commit that is not reachable from any branch (rare in SWE-bench)."""
    d = repo_dir(cfg, repo)
    probe = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=d,
                           capture_output=True)
    if probe.returncode != 0:
        console.print(f"[yellow]fetching unreachable commit {commit[:10]} for {repo}[/yellow]")
        _git(d, "fetch", "--quiet", "origin", commit)


def list_tree(cfg: Config, repo: str, commit: str) -> list[TreeEntry]:
    out = _git(repo_dir(cfg, repo), "ls-tree", "-r", "-l", "-z", commit)
    entries = []
    for record in out.split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, kind, blob, size = meta.split()
        if kind != b"blob" or mode == b"120000":  # skip symlinks and submodules
            continue
        entries.append(TreeEntry(path.decode("utf-8", "replace"), blob.decode(),
                                 int(size) if size != b"-" else 0))
    return entries


def list_py_files(cfg: Config, repo: str, commit: str, apply_exclusions: bool = True
                  ) -> list[TreeEntry]:
    """FR-D4/FR-D5: non-excluded .py files at a commit, sorted by path."""
    patterns = compile_patterns(cfg.exclusions.path_patterns)
    max_bytes = cfg.exclusions.max_file_bytes
    files = [e for e in list_tree(cfg, repo, commit) if e.path.endswith(".py")]
    if apply_exclusions:
        files = [e for e in files if not matches_any(e.path, patterns) and e.size <= max_bytes]
    return sorted(files, key=lambda e: e.path)


def read_blobs(cfg: Config, repo: str, blobs: list[str]) -> dict[str, str]:
    """Read many blobs with one `git cat-file --batch` process. Returns {blob: text}."""
    if not blobs:
        return {}
    unique = list(dict.fromkeys(blobs))
    out = _git(repo_dir(cfg, repo), "cat-file", "--batch",
               input_bytes=("\n".join(unique) + "\n").encode())
    result: dict[str, str] = {}
    pos = 0
    for blob in unique:
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].split()
        if len(header) < 3 or header[1] == b"missing":
            pos = header_end + 1
            continue
        size = int(header[2])
        start = header_end + 1
        result[blob] = out[start:start + size].decode("utf-8", "replace")
        pos = start + size + 1  # trailing newline after each object
    return result


def read_files(cfg: Config, repo: str, commit: str, paths: list[str]) -> dict[str, str]:
    """Read files at a commit. Missing paths are omitted from the result."""
    if not paths:
        return {}
    refs = [f"{commit}:{p}" for p in paths]
    out = _git(repo_dir(cfg, repo), "cat-file", "--batch",
               input_bytes=("\n".join(refs) + "\n").encode())
    result: dict[str, str] = {}
    pos = 0
    for path in paths:
        header_end = out.index(b"\n", pos)
        header = out[pos:header_end].split()
        if len(header) < 3 or header[-1] == b"missing":
            pos = header_end + 1
            continue
        size = int(header[2])
        start = header_end + 1
        result[path] = out[start:start + size].decode("utf-8", "replace")
        pos = start + size + 1
    return result
