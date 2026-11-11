"""Find where a program starts — FR-G4.

Concept: "where does execution begin?" is the first question a newcomer asks.
Python has several conventions, all statically detectable:
`if __name__ == "__main__":` blocks, `console_scripts` / `[project.scripts]`
declared in packaging files (`name = "pkg.mod:func"`), Django's `manage.py`,
and CLI frameworks (functions decorated with `click.command` / `group` or
`app.command`, and `typer.Typer()` apps). Each entry point is recorded with
its `path:line`, so the guide can cite it and call-flow diagrams can start there.
"""

from __future__ import annotations

import configparser
import re
import tomllib

from buglens.schemas import FileFacts

_SCRIPT_RE = re.compile(r"""["']\s*([\w.\-]+)\s*=\s*([\w.]+)\s*:\s*([\w.]+)""")


def console_scripts(config_files: dict[str, str]) -> list[tuple[str, str, str]]:
    """[(script name, module, function)] from setup.py / setup.cfg / pyproject.toml."""
    found: list[tuple[str, str, str]] = []
    for name, text in sorted(config_files.items()):
        base = name.split("/")[-1]
        try:
            if base == "pyproject.toml":
                data = tomllib.loads(text)
                scripts = dict(data.get("project", {}).get("scripts", {}))
                scripts.update(data.get("tool", {}).get("poetry", {}).get("scripts", {}))
                for k, v in scripts.items():
                    if isinstance(v, str) and ":" in v:
                        mod, func = v.split(":", 1)
                        found.append((k, mod.strip(), func.strip()))
            elif base == "setup.cfg":
                cp = configparser.ConfigParser()
                cp.read_string(text)
                if cp.has_option("options.entry_points", "console_scripts"):
                    for line in cp.get("options.entry_points", "console_scripts").splitlines():
                        if "=" in line and ":" in line:
                            k, v = line.split("=", 1)
                            mod, func = v.split(":", 1)
                            found.append((k.strip(), mod.strip(), func.strip()))
            elif base == "setup.py" and "console_scripts" in text:
                found.extend(_SCRIPT_RE.findall(text))
        except (tomllib.TOMLDecodeError, configparser.Error, ValueError):
            continue
    return sorted(set(found))


def find_entry_points(facts: dict[str, FileFacts], raw_by_path: dict[str, dict],
                      config_files: dict[str, str]) -> list[dict]:
    """[{kind, path, line, name, module, qualname}] sorted by (path, line)."""
    eps: list[dict] = []
    by_module = {f.module: f for f in facts.values()}
    for path in sorted(facts):
        f, raw = facts[path], raw_by_path.get(path, {})
        if raw.get("main_line"):
            eps.append({"kind": "__main__", "path": path, "line": raw["main_line"],
                        "name": f"{f.module or path} __main__", "module": f.module,
                        "qualname": "<module>"})
        if path.split("/")[-1] == "manage.py":
            eps.append({"kind": "manage.py", "path": path, "line": 1, "name": "manage.py",
                        "module": f.module, "qualname": "<module>"})
        for fn in f.functions:
            for d in fn.get("decorators", []):
                if "." in d and d.split(".")[-1] in ("command", "group"):
                    eps.append({"kind": "cli", "path": path, "line": fn["start_line"],
                                "name": f"{fn['name']} (@{d})", "module": f.module,
                                "qualname": fn["name"]})
                    break
        for line in raw.get("typer_lines", []):
            eps.append({"kind": "typer", "path": path, "line": line, "name": "typer app",
                        "module": f.module, "qualname": "<module>"})
    for script, mod, func in console_scripts(config_files):
        f = by_module.get(mod)
        if f is None:
            continue
        line = next((fn["start_line"] for fn in f.functions if fn["name"] == func), 1)
        eps.append({"kind": "console_script", "path": f.path, "line": line,
                    "name": f"{script} -> {mod}:{func}", "module": mod,
                    "qualname": func if any(fn["name"] == func for fn in f.functions)
                    else "<module>"})
    uniq = {(e["kind"], e["path"], e["line"], e["name"]): e for e in eps}
    return sorted(uniq.values(), key=lambda e: (e["path"], e["line"], e["kind"]))
