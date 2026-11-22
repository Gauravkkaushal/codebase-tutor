import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
FIXTURES = Path(__file__).resolve().parent / 'fixtures'
from codebase_tutor.parsers import parse_file  # noqa: E402
from codebase_tutor.parsers.js_parser import tree_sitter_available  # noqa: E402


def _js(path):
    return parse_file(path, "javascript", (FIXTURES / "js_app" / path).read_text())


def test_tree_sitter_available():
    assert tree_sitter_available()


def test_js_symbols_have_exact_lines():
    f = _js("src/controllers/auth.controller.js")
    syms = {s.qualname: s for s in f.symbols}
    assert syms["login"].start == 5 and syms["login"].end == 20
    assert syms["logout"].start == 22 and syms["logout"].end == 24
    assert syms["login"].exported and syms["logout"].exported
    assert f.parser == "tree-sitter" and not f.errors


def test_js_imports_and_bindings():
    f = _js("src/controllers/auth.controller.js")
    mods = {i.module: i.names for i in f.imports}
    assert mods["bcrypt"] == [["default", "bcrypt"]]
    assert mods["../services/token"] == [["signToken", "signToken"]]


def test_js_control_points_and_outcomes():
    f = _js("src/controllers/auth.controller.js")
    by_line = {(c.line, c.kind): c for c in f.controls}
    assert by_line[(7, "if")].text == "if (!email || !password)"
    assert by_line[(12, "return")].outcome == "failure"  # 401
    assert by_line[(19, "return")].outcome == "success"


def test_js_routes_and_class_methods():
    r = _js("src/routes/auth.routes.js")
    routes = {(x.method, x.path): x for x in r.routes}
    assert routes[("POST", "/logout")].handlers == ["requireAuth", "logout"]
    m = _js("src/models/user.js")
    assert any(s.qualname == "User.findByEmail" and s.kind == "method" for s in m.symbols)


def test_js_env_vars_names_only():
    f = _js("src/services/token.js")
    assert [e[1] for e in f.env_vars] == ["JWT_SECRET"]


def test_python_parser():
    text = (FIXTURES / "py_app" / "app" / "views.py").read_text()
    f = parse_file("app/views.py", "python", text)
    assert f.routes[0].path == "/login" and f.routes[0].method == "POST" and f.routes[0].handlers == ["login"]
    login = next(s for s in f.symbols if s.name == "login")
    assert login.start == 8 and login.end == 13  # decorator line included
    auth = parse_file("app/services/auth.py", "python", (FIXTURES / "py_app/app/services/auth.py").read_text())
    assert ["APP_SECRET"] == [e[1] for e in auth.env_vars]
    q = {s.qualname: s for s in auth.symbols}
    assert q["Session.refresh"].kind == "method" and q["Session"].kind == "class"
    assert any(c.kind == "raise" and c.outcome == "failure" for c in auth.controls)


def test_syntax_error_is_reported_not_raised():
    f = parse_file("bad.py", "python", "def x(:\n")
    assert f.errors and not f.symbols
