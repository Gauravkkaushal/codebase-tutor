"""Python facts via the stdlib ast module (exact line numbers, no guessing)."""
from __future__ import annotations

import ast
from pathlib import PurePosixPath

from .base import Call, Control, FileFacts, Import, Route, Symbol, body_hash, classify_outcome, short

ROUTE_DECORATOR_METHODS = {"route": None, "get": "GET", "post": "POST", "put": "PUT", "patch": "PATCH",
                           "delete": "DELETE", "head": "HEAD", "options": "OPTIONS", "api_route": None,
                           "websocket": "WS"}
DJANGO_URL_FUNCS = {"path", "re_path", "url"}


def _unparse(node) -> str:
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover - ast.unparse is robust on parsed trees
        return "<expr>"


def _call_name(func) -> tuple[str, str, str | None]:
    """Return (expr, name, receiver_root) for a call's func node."""
    expr = short(_unparse(func), 120)
    if isinstance(func, ast.Name):
        return expr, func.id, None
    if isinstance(func, ast.Attribute):
        root = func.value
        while isinstance(root, (ast.Attribute, ast.Call, ast.Subscript)):
            root = root.func if isinstance(root, ast.Call) else root.value
        recv = root.id if isinstance(root, ast.Name) else _unparse(func.value)[:40]
        return expr, func.attr, recv
    return expr, expr.split("(")[0].split(".")[-1][:60], None


class _Visitor(ast.NodeVisitor):
    def __init__(self, path: str, lines: list):
        self.path = path
        self.lines = lines
        self.facts = FileFacts(parser="python-ast")
        self.stack: list = []  # (qualname, kind)
        self.all_names: set | None = None
        self.prefixes: dict = {}  # router variable -> url prefix (Blueprint url_prefix / APIRouter prefix)

    # ---- helpers
    @property
    def current(self):
        return self.stack[-1][0] if self.stack else None

    def _sig(self, node) -> str:
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        ret = f" -> {_unparse(node.returns)}" if getattr(node, "returns", None) is not None else ""
        return short(f"{prefix}{node.name}({_unparse(node.args)}){ret}", 200)

    def _body_text(self, start: int, end: int) -> str:
        return "\n".join(self.lines[start - 1:end])

    # ---- definitions
    def _visit_def(self, node, kind: str):
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        end = getattr(node, "end_lineno", node.lineno) or node.lineno
        parent = self.current
        parent_kind = self.stack[-1][1] if self.stack else None
        if kind == "function" and parent_kind == "class":
            kind = "method"
        qual = f"{parent}.{node.name}" if parent else node.name
        if isinstance(node, ast.ClassDef):
            bases = ", ".join(_unparse(b) for b in node.bases)
            sig = f"class {node.name}({bases})" if bases else f"class {node.name}"
        else:
            sig = self._sig(node)
        exported = not node.name.startswith("_") and parent is None
        self.facts.symbols.append(Symbol(node.name, qual, kind, start, end, sig, exported, parent,
                                         body_hash(self._body_text(node.lineno, end))))
        for dec in getattr(node, "decorator_list", []):
            self._route_from_decorator(dec, qual)
        for dec in getattr(node, "decorator_list", []):
            self.visit(dec)
        self.stack.append((qual, "class" if isinstance(node, ast.ClassDef) else "function"))
        for child in node.body:
            self.visit(child)
        self.stack.pop()
        if isinstance(node, ast.ClassDef):
            for b in node.bases:
                self.visit(b)
        else:
            self.visit(node.args)

    def visit_FunctionDef(self, node):
        self._visit_def(node, "function")

    def visit_AsyncFunctionDef(self, node):
        self._visit_def(node, "function")

    def visit_ClassDef(self, node):
        self._visit_def(node, "class")

    def visit_Assign(self, node):
        if not self.stack:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "__all__" and isinstance(node.value, (ast.List, ast.Tuple)):
                    self.all_names = {e.value for e in node.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                elif isinstance(t, ast.Name) and t.id == "urlpatterns":
                    self._django_urls(node.value)
                elif isinstance(t, ast.Name) and isinstance(node.value, ast.Call):
                    fname = _unparse(node.value.func).split(".")[-1]
                    if fname in ("Blueprint", "APIRouter"):
                        for kw in node.value.keywords:
                            if kw.arg in ("url_prefix", "prefix") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                self.prefixes[t.id] = kw.value.value.rstrip("/")
        self.generic_visit(node)

    def visit_AugAssign(self, node):
        if not self.stack and isinstance(node.target, ast.Name) and node.target.id == "urlpatterns":
            self._django_urls(node.value)
        self.generic_visit(node)

    # ---- imports
    def visit_Import(self, node):
        for a in node.names:
            local = a.asname or a.name.split(".")[0]
            target = a.name if a.asname else a.name.split(".")[0]
            self.facts.imports.append(Import(node.lineno, target if not a.asname else a.name, [["*", local]], "py"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        mod = "." * (node.level or 0) + (node.module or "")
        names = [[a.name, a.asname or a.name] for a in node.names]
        self.facts.imports.append(Import(node.lineno, mod, names, "py"))
        self.generic_visit(node)

    # ---- calls / env vars
    def visit_Call(self, node):
        expr, name, recv = _call_name(node.func)
        self.facts.calls.append(Call(node.lineno, self.current, expr, name, recv))
        # env vars: os.getenv('X'), os.environ.get('X')
        if expr in ("os.getenv", "getenv", "os.environ.get", "environ.get") and node.args and \
                isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            self.facts.env_vars.append([node.lineno, node.args[0].value])
        self.generic_visit(node)

    def visit_Subscript(self, node):
        base = _unparse(node.value)
        if base in ("os.environ", "environ") and isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
            self.facts.env_vars.append([node.lineno, node.slice.value])
        self.generic_visit(node)

    # ---- control points
    def _control(self, node, kind: str, text: str):
        self.facts.controls.append(Control(node.lineno, self.current, kind, short(text), classify_outcome(kind, text)))

    def visit_If(self, node):
        test = _unparse(node.test)
        if test.replace(" ", "") in ("__name__=='__main__'", '__name__=="__main__"'):
            self.facts.entry_reasons.append(f"if __name__ == '__main__' (line {node.lineno})")
        if self.stack:
            self._control(node, "if", f"if {test}")
            if node.orelse and not (len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If)):
                first = node.orelse[0]
                self.facts.controls.append(Control(max(first.lineno - 1, node.lineno), self.current, "else",
                                                   f"else (of if {short(test, 80)})", "neutral"))
        self.generic_visit(node)

    def visit_Return(self, node):
        if self.stack:
            self._control(node, "return", "return " + (_unparse(node.value) if node.value is not None else ""))
        self.generic_visit(node)

    def visit_Raise(self, node):
        if self.stack:
            self._control(node, "raise", "raise " + (_unparse(node.exc) if node.exc is not None else ""))
        self.generic_visit(node)

    def visit_Try(self, node):
        if self.stack:
            self._control(node, "try", "try")
            for h in node.handlers:
                self.facts.controls.append(Control(h.lineno, self.current, "catch",
                                                   short("except " + (_unparse(h.type) if h.type else "")), "failure"))
        self.generic_visit(node)

    visit_TryStar = visit_Try

    def visit_Assert(self, node):
        if self.stack:
            self._control(node, "assert", "assert " + _unparse(node.test))
        self.generic_visit(node)

    # ---- routes
    def _route_from_decorator(self, dec, handler_qual: str):
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            return
        attr = dec.func.attr
        if attr not in ROUTE_DECORATOR_METHODS:
            return
        router = _unparse(dec.func.value)
        path = None
        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
            path = dec.args[0].value
        for kw in dec.keywords:
            if kw.arg in ("rule", "path") and isinstance(kw.value, ast.Constant):
                path = kw.value.value
        if path is None:
            return
        methods = []
        if ROUTE_DECORATOR_METHODS[attr]:
            methods = [ROUTE_DECORATOR_METHODS[attr]]
        for kw in dec.keywords:
            if kw.arg == "methods" and isinstance(kw.value, (ast.List, ast.Tuple, ast.Set)):
                methods = [str(e.value).upper() for e in kw.value.elts if isinstance(e, ast.Constant)]
        if not methods:
            methods = ["GET"]
        framework = "fastapi" if attr in ("api_route", "websocket") or router.endswith("router") else "flask"
        prefix = self.prefixes.get(router, "")
        if prefix:
            path = prefix + (path if path.startswith("/") else "/" + path)
        for m in methods:
            self.facts.routes.append(Route(dec.lineno, framework, m, path, [handler_qual], router, "route"))

    def _django_urls(self, value):
        if not isinstance(value, (ast.List, ast.Tuple)):
            return
        for elt in value.elts:
            if isinstance(elt, ast.Call) and isinstance(elt.func, (ast.Name, ast.Attribute)):
                fname = elt.func.id if isinstance(elt.func, ast.Name) else elt.func.attr
                if fname in DJANGO_URL_FUNCS and len(elt.args) >= 2 and isinstance(elt.args[0], ast.Constant):
                    target = _unparse(elt.args[1])
                    kind = "mount" if target.startswith("include(") else "route"
                    self.facts.routes.append(Route(elt.lineno, "django", "ANY", "/" + str(elt.args[0].value).lstrip("^"),
                                                   [target], "urlpatterns", kind))


def parse_python(path: str, text: str) -> FileFacts:
    lines = text.splitlines()
    try:
        tree = ast.parse(text, filename=path, type_comments=False)
    except SyntaxError as e:
        f = FileFacts(parser="python-ast")
        f.errors.append(f"SyntaxError line {e.lineno}: {e.msg}")
        return f
    v = _Visitor(path, lines)
    v.visit(tree)
    facts = v.facts
    names = v.all_names
    for s in facts.symbols:
        if s.parent is None:
            s.exported = (s.name in names) if names is not None else not s.name.startswith("_")
            if s.exported:
                facts.exports.append([s.name, s.qualname])
    # Re-exports: names imported into the module are importable from it.
    for imp in facts.imports:
        for imported, local in imp.names:
            if imported != "*" and (names is None or local in names):
                facts.exports.append([local, f"import:{imp.module}:{imported}"])
    name = PurePosixPath(path).name
    if name in ("manage.py", "wsgi.py", "asgi.py", "__main__.py"):
        facts.entry_reasons.append(f"conventional entry file name ({name})")
    for r in facts.routes:
        if r.framework in ("flask", "fastapi") and not any("app" in e for e in facts.entry_reasons):
            pass
    return facts
