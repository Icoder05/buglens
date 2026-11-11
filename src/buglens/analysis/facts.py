"""Per-file static facts from the AST: imports, classes, functions, call sites.

Concept: static analysis reads code without running it. Python's `ast` gives
us, for every file, what it imports, which classes (and bases) and functions
it defines, and every call site. Extraction is purely local to one file (so it
is cached per git blob), while *resolution* needs the whole repository: a name
`helper` called in `shop/models.py` means `shop.core.helper` only because that
module did `from .core import helper`. Resolution is best effort and
deliberately approximate (FR-A2): direct names, `self.method` through in-repo
base classes, and `alias.attr` through imports; dynamic dispatch, return types
and monkey-patching stay unresolved (`resolved=None`).
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass, field

from buglens.schemas import FileFacts

BUILTIN_NAMES = set(dir(builtins))
CLI_DECORATOR_SUFFIXES = ("command", "group")


# ---------------------------------------------------------------- raw extraction
def _dotted(expr: ast.expr) -> str | None:
    """`a.b.c` -> 'a.b.c'; anything not a pure Name/Attribute chain -> None."""
    parts = []
    while isinstance(expr, ast.Attribute):
        parts.append(expr.attr)
        expr = expr.value
    if isinstance(expr, ast.Name):
        parts.append(expr.id)
        return ".".join(reversed(parts))
    return None


def _first_doc_line(node) -> str:
    doc = ast.get_docstring(node, clean=True) or ""
    return doc.strip().splitlines()[0][:200] if doc.strip() else ""


def _start(node) -> int:
    return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])


def _func_record(node) -> dict:
    return {"name": node.name, "start_line": _start(node), "end_line": node.end_lineno,
            "signature": f"({ast.unparse(node.args)})", "docstring": _first_doc_line(node),
            "decorators": [d for d in (_dotted(x.func if isinstance(x, ast.Call) else x)
                                       for x in node.decorator_list) if d]}


class _CallCollector(ast.NodeVisitor):
    """Collect call sites, attributing each to its enclosing chunk qualname."""

    def __init__(self):
        self.calls: list[dict] = []
        self.stack: list[str] = []      # qualname parts of enclosing defs
        self.kinds: list[str] = []      # "class" | "func"

    def _caller(self) -> str:
        if not self.stack:
            return "<module>"
        # Nested functions inside a function belong to the outermost function/method chunk.
        parts = []
        for name, kind in zip(self.stack, self.kinds, strict=True):
            parts.append(name)
            if kind == "func":
                break
        return ".".join(parts)

    def visit_ClassDef(self, node):
        for d in node.decorator_list + node.bases + [k.value for k in node.keywords]:
            self.visit(d)
        self.stack.append(node.name)
        self.kinds.append("class")
        for stmt in node.body:
            self.visit(stmt)
        self.stack.pop()
        self.kinds.pop()

    def _visit_func(self, node):
        for d in node.decorator_list:
            self.visit(d)
        self.stack.append(node.name)
        self.kinds.append("func")
        for stmt in node.body:
            self.visit(stmt)
        self.stack.pop()
        self.kinds.pop()

    visit_FunctionDef = _visit_func
    visit_AsyncFunctionDef = _visit_func

    def visit_Call(self, node):
        name = _dotted(node.func)
        if name is None and isinstance(node.func, ast.Attribute):
            name = "?." + node.func.attr  # e.g. foo().bar() — receiver unknown
        if name is not None:
            self.calls.append({"caller_qualname": self._caller(), "callee_name": name,
                               "line": node.lineno})
        self.generic_visit(node)


def _is_main_guard(node: ast.stmt) -> bool:
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    t = node.test
    sides = [t.left, *t.comparators]
    has_name = any(isinstance(s, ast.Name) and s.id == "__name__" for s in sides)
    has_main = any(isinstance(s, ast.Constant) and s.value == "__main__" for s in sides)
    return has_name and has_main


def _failed() -> dict:
    return {"ok": False, "imports": [], "classes": [], "functions": [], "calls": [],
            "main_line": None, "typer_lines": [], "local_names": []}


def extract_raw(path: str, source: str) -> dict:
    """Facts that depend only on this file's text (cacheable per git blob).

    FR-A3: never crash. Besides syntax errors, some generated files (e.g. huge
    nested expressions in sympy) parse but overflow the recursion limit while
    walking the tree; those also count as parse failures.
    """
    try:
        return _extract(ast.parse(source))
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return _failed()


def _extract(tree: ast.Module) -> dict:

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                imports.append({"kind": "import", "name": a.name, "asname": a.asname,
                                "line": node.lineno, "top": node in tree.body})
        elif isinstance(node, ast.ImportFrom):
            imports.append({"kind": "from", "module": node.module, "level": node.level,
                            "names": [[a.name, a.asname] for a in node.names],
                            "line": node.lineno, "top": node in tree.body})

    classes, functions = [], []

    def walk_class(node: ast.ClassDef, prefix: str):
        methods = [_func_record(c) for c in node.body
                   if isinstance(c, ast.FunctionDef | ast.AsyncFunctionDef)]
        classes.append({"name": prefix + node.name, "bases": [b for b in (
            _dotted(x) for x in node.bases) if b], "start_line": _start(node),
            "end_line": node.end_lineno, "methods": methods,
            "docstring": _first_doc_line(node)})
        for c in node.body:
            if isinstance(c, ast.ClassDef):
                walk_class(c, prefix + node.name + ".")

    main_line, typer_lines, local_names = None, [], []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions.append(_func_record(node))
            local_names.append(node.name)
        elif isinstance(node, ast.ClassDef):
            walk_class(node, "")
            local_names.append(node.name)
        elif _is_main_guard(node) and main_line is None:
            main_line = node.lineno
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
            if (_dotted(node.value.func) or "").endswith("Typer"):
                typer_lines.append(node.lineno)
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name):
                    local_names.append(tgt.id)

    collector = _CallCollector()
    collector.visit(tree)
    return {"ok": True, "imports": imports, "classes": classes, "functions": functions,
            "calls": collector.calls, "main_line": main_line, "typer_lines": typer_lines,
            "local_names": local_names}


# ---------------------------------------------------------------- module naming
def source_roots(paths: list[str]) -> list[str]:
    """Directories that hold top-level packages (src/ and lib/ layouts), longest first."""
    roots = []
    pathset = set(paths)
    for root in ("src", "lib"):
        if any(p.startswith(root + "/") and p.count("/") >= 2 and
               f"{root}/{p.split('/')[1]}/__init__.py" in pathset for p in paths):
            roots.append(root)
    return roots


def module_name(path: str, roots: list[str]) -> str:
    rel = path
    for root in roots:
        if path.startswith(root + "/"):
            rel = path[len(root) + 1:]
            break
    rel = rel[:-3] if rel.endswith(".py") else rel
    if rel.endswith("/__init__"):
        rel = rel[: -len("/__init__")]
    elif rel == "__init__":
        rel = ""
    return rel.replace("/", ".")


# ---------------------------------------------------------------- resolution
@dataclass
class _Index:
    modules: dict[str, str]                       # module -> path
    is_package: dict[str, bool]
    defs: dict[str, set[str]] = field(default_factory=dict)       # module -> top-level names
    bindings: dict[str, dict[str, str]] = field(default_factory=dict)  # module -> name -> dotted
    methods: dict[str, set[str]] = field(default_factory=dict)    # class full -> method names
    bases: dict[str, list[str]] = field(default_factory=dict)     # class full -> base fulls
    classes: set[str] = field(default_factory=set)


def _package_of(module: str, is_package: bool) -> str:
    return module if is_package else module.rpartition(".")[0]


def _absolute_from(mod: str, is_pkg: bool, module: str | None, level: int) -> str:
    if level == 0:
        return module or ""
    base = _package_of(mod, is_pkg)
    for _ in range(level - 1):
        base = base.rpartition(".")[0]
    return f"{base}.{module}" if module and base else (module or base)


def _longest_module(idx: _Index, dotted: str) -> tuple[str | None, list[str]]:
    parts = dotted.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in idx.modules:
            return cand, parts[i:]
    return None, parts


def _find_method(idx: _Index, cls: str, name: str, seen: set[str] | None = None) -> str | None:
    seen = seen or set()
    if cls in seen:
        return None
    seen.add(cls)
    if name in idx.methods.get(cls, set()):
        return f"{cls}.{name}"
    for base in idx.bases.get(cls, []):
        found = _find_method(idx, base, name, seen)
        if found:
            return found
    return None


def _resolve_dotted(idx: _Index, dotted: str, depth: int = 0) -> str | None:
    """Resolve an absolute dotted name to an in-repo module, class, function or method."""
    if depth > 5 or not dotted:
        return None
    mod, rest = _longest_module(idx, dotted)
    if mod is None:
        return None
    if not rest:
        return mod
    head, tail = rest[0], rest[1:]
    if head in idx.defs.get(mod, set()):
        full = f"{mod}.{head}"
        # nested classes: Outer.Inner
        while tail and f"{full}.{tail[0]}" in idx.classes:
            full = f"{full}.{tail[0]}"
            tail = tail[1:]
        if not tail:
            return full
        if full in idx.classes and len(tail) == 1:
            return _find_method(idx, full, tail[0])
        return None
    target = idx.bindings.get(mod, {}).get(head)  # re-export, e.g. `from .core import Base`
    if target:
        return _resolve_dotted(idx, ".".join([target, *tail]), depth + 1)
    return None


def _resolve_name(idx: _Index, mod: str, dotted: str) -> str | None:
    head, _, rest = dotted.partition(".")
    if head in idx.defs.get(mod, set()):
        base = f"{mod}.{head}"
    elif head in idx.bindings.get(mod, {}):
        base = idx.bindings[mod][head]
    else:
        return None
    return _resolve_dotted(idx, f"{base}.{rest}" if rest else base)


def build_facts(raw_by_path: dict[str, dict], main_targets: set[str] | None = None
                ) -> dict[str, FileFacts]:
    """Resolve raw per-file facts against the whole repository snapshot."""
    paths = sorted(raw_by_path)
    roots = source_roots(paths)
    mods = {p: module_name(p, roots) for p in paths}
    idx = _Index(modules={m: p for p, m in mods.items() if m},
                 is_package={m: p.endswith("__init__.py") for p, m in mods.items()})

    # pass 1: definitions, bindings, class methods
    for p in paths:
        raw, mod = raw_by_path[p], mods[p]
        idx.defs[mod] = {f["name"] for f in raw["functions"]} | {
            c["name"] for c in raw["classes"] if "." not in c["name"]}
        for c in raw["classes"]:
            full = f"{mod}.{c['name']}"
            idx.classes.add(full)
            idx.methods[full] = {m["name"] for m in c["methods"]}
        binds: dict[str, str] = {}
        for imp in raw["imports"]:
            if imp["kind"] == "import":
                if imp["asname"]:
                    binds[imp["asname"]] = imp["name"]
                else:
                    head = imp["name"].split(".")[0]
                    binds.setdefault(head, head)
            else:
                src = _absolute_from(mod, idx.is_package.get(mod, False), imp["module"],
                                     imp["level"])
                for name, asname in imp["names"]:
                    if name != "*":
                        binds[asname or name] = f"{src}.{name}" if src else name
        idx.bindings[mod] = binds

    # pass 2: class bases (needed for self.method resolution)
    for p in paths:
        mod = mods[p]
        for c in raw_by_path[p]["classes"]:
            full = f"{mod}.{c['name']}"
            resolved = []
            for b in c["bases"]:
                r = _resolve_name(idx, mod, b)
                if r in idx.classes and r != full:
                    resolved.append(r)
            idx.bases[full] = resolved

    # pass 3: per-file facts
    facts: dict[str, FileFacts] = {}
    for p in paths:
        raw, mod = raw_by_path[p], mods[p]
        imports = set()
        for imp in raw["imports"]:
            if imp["kind"] == "import":
                m, _ = _longest_module(idx, imp["name"])
                if m:
                    imports.add(m)
            else:
                src = _absolute_from(mod, idx.is_package.get(mod, False), imp["module"],
                                     imp["level"])
                for name, _ in imp["names"]:
                    sub = f"{src}.{name}" if src else name
                    if sub in idx.modules:
                        imports.add(sub)
                    elif src in idx.modules:
                        imports.add(src)
        imports.discard(mod)

        local = set(raw.get("local_names", [])) | set(idx.bindings.get(mod, {}))
        calls = []
        for call in raw["calls"]:
            name = call["callee_name"]
            head = name.split(".")[0]
            if head in BUILTIN_NAMES and head not in local:
                continue  # print(), len(), isinstance(): not part of the repo
            resolved = None
            if head in ("self", "cls") and "." in name:
                caller = call["caller_qualname"]
                cls_qual = caller.rpartition(".")[0]
                attr = name.split(".", 1)[1]
                if cls_qual and "." not in attr:
                    resolved = _find_method(idx, f"{mod}.{cls_qual}", attr)
            elif not name.startswith("?."):
                resolved = _resolve_name(idx, mod, name)
                if resolved in idx.modules:  # calling a module is not a call edge
                    resolved = None
            calls.append({**call, "resolved": resolved})

        classes = []
        for c in raw["classes"]:
            full = f"{mod}.{c['name']}"
            classes.append({**c, "bases_resolved": idx.bases.get(full, [])})
        is_entry = (raw.get("main_line") is not None or p.split("/")[-1] == "manage.py"
                    or bool(raw.get("typer_lines"))
                    or any(d.split(".")[-1] in CLI_DECORATOR_SUFFIXES and "." in d
                           for f in raw["functions"] for d in f.get("decorators", []))
                    or (main_targets is not None and mod in main_targets))
        facts[p] = FileFacts(path=p, module=mod, imports=sorted(imports), classes=classes,
                             functions=raw["functions"], calls=calls,
                             is_entry_point=is_entry, parse_ok=raw["ok"])
    return facts


def facts_from_sources(sources: dict[str, str], main_targets: set[str] | None = None
                       ) -> dict[str, FileFacts]:
    return build_facts({p: extract_raw(p, s) for p, s in sources.items()}, main_targets)
