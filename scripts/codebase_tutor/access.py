"""Data access that a plain import/call graph misses, inferred from parsed facts plus the source line.

1. Database handles: a local file that imports a database package (a Mongoose model, a Sequelize model, a
   `db.js` exporting a pg pool, a Flask-SQLAlchemy `db`) is a *model file*. Names imported from it, and variables
   assigned from them (`const user = await User.findOne(..)`, `cart = new Cart(..)`), are database handles; calls on
   them are database reads/writes. Label: structurally-inferred (we do not run the query).
2. In-repo HTTP calls: `axios.post('http://localhost:5000/api/cart/add')` / `fetch('/api/x')` in one part of the
   repo matched to a route defined in another part (method + path pattern). Label: structurally-inferred.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .evidence import EvidenceError, read_lines, redact_line

WRITE_RE = re.compile(r"(save|create|insert|update|upsert|delete|remove|destroy|replace|bulk|truncate|drop|commit|add|"
                      r"increment|decrement|AndUpdate|AndDelete|AndRemove|AndReplace)", re.I)
READ_RE = re.compile(r"^(find|get|count|exists|aggregate|distinct|populate|select|query|filter|first|all|one|scalar|"
                     r"fetch|lean|exec|where|order_by|limit|paginate|search|lookup|scan)", re.I)
INSTANCE_OPS = {"save", "remove", "deleteOne", "updateOne", "populate", "validate", "destroy", "reload", "increment",
                "decrement", "update", "delete", "toJSON"}
HTTP_LIBS = {"axios", "node-fetch", "got", "superagent", "ky", "cross-fetch", "isomorphic-fetch", "requests", "httpx"}
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}
STR_LIT = re.compile(r"""(['"`])((?:https?://[^/'"`\s]*)?/[^'"`\s]*?)\1""")
TPL_EXPR = re.compile(r"\$\{[^}]*\}")
FETCH_METHOD = re.compile(r"""method\s*:\s*['"](\w+)['"]""", re.I)


def _root_of(store) -> Path:
    return Path(store.path).resolve().parents[2]


def db_op(name: str) -> str:
    if WRITE_RE.search(name or ""):
        return "write"
    if READ_RE.match(name or ""):
        return "read"
    return "query"


class AccessIndex:
    def __init__(self, store, root=None, classify=None):
        from .dataflow import classify_external  # local import: dataflow imports this module
        classify = classify or classify_external
        self.store = store
        self.root = Path(root) if root else _root_of(store)
        self.model_files = {}  # file -> (label, package)
        for r in store.q("SELECT file, module FROM imports WHERE external=1"):
            cls = classify(r["module"])
            if cls and cls[0] == "database" and r["file"] not in self.model_files:
                self.model_files[r["file"]] = (cls[1], r["module"])
        self.handles = defaultdict(dict)  # file -> local name -> {model_file, label, package, name}
        for r in store.q("SELECT file, names, resolved FROM imports WHERE external=0 AND resolved IS NOT NULL"):
            mf = self.model_files.get(r["resolved"])
            if not mf or r["file"] == r["resolved"]:
                continue
            for pair in json.loads(r["names"] or "[]"):
                local = pair[1] if isinstance(pair, (list, tuple)) and len(pair) > 1 else pair
                if isinstance(local, str) and local.isidentifier():
                    self.handles[r["file"]][local] = {"model_file": r["resolved"], "label": mf[0], "package": mf[1],
                                                      "name": local}
        self._instances = {}
        self._lines = {}

    def lines(self, file):
        if file not in self._lines:
            try:
                self._lines[file] = read_lines(self.root, file)
            except EvidenceError:
                self._lines[file] = []
        return self._lines[file]

    def instances(self, file):
        if file in self._instances:
            return self._instances[file]
        out = {}
        hs = self.handles.get(file) or {}
        if hs:
            names = "|".join(re.escape(n) for n in hs)
            pat = re.compile(r"\b([A-Za-z_$][\w$]*)\s*=\s*(?:await\s+)?(?:new\s+)?(" + names + r")\s*[.(]")
            for ln in self.lines(file):
                for m in pat.finditer(ln):
                    var = m.group(1)
                    if var not in hs and var not in ("exports",):
                        out[var] = hs[m.group(2)]
        self._instances[file] = out
        return out

    def classify_call(self, file, expr, name, receiver):
        """Return a dict describing a database operation, or None."""
        if not receiver:
            return None
        root = re.match(r"[A-Za-z_$][\w$]*", receiver)
        if not root:
            return None
        root = root.group(0)
        rest = receiver[len(root):]
        h = (self.handles.get(file) or {}).get(root)
        if h:
            # Model.find(...), Model.find(...).populate(...), db.session.add(...)
            if rest and not rest.startswith(("(", ".")):
                return None
            via = "model"
        else:
            h = self.instances(file).get(root)
            if not h or rest or name not in INSTANCE_OPS:
                return None
            via = "instance"
        op = db_op(name)
        return {"label": h["label"], "package": h["package"], "model": h["name"], "model_file": h["model_file"],
                "op": op, "via": via}

    # ---------------------------------------------------------------- in-repo HTTP calls
    def http_calls(self):
        """Calls in this repo that hit a route defined in this repo: list of dicts with caller + route."""
        routes = []
        for r in self.store.q("SELECT id, file, line, method, path, full_path FROM routes WHERE kind='route'"):
            p = r["full_path"] or r["path"]
            if not p or not p.startswith("/"):
                continue
            routes.append((dict(r), _route_regex(p)))
        if not routes:
            return []
        rows = self.store.q("SELECT id, file, line, caller, expr, name, receiver, external FROM calls "
                            "WHERE (resolution='external' AND external IN (%s)) OR (name='fetch' AND receiver IS NULL)"
                            % ",".join("?" * len(HTTP_LIBS)), tuple(sorted(HTTP_LIBS)))
        out = []
        for c in rows:
            lines = self.lines(c["file"])
            if not (1 <= c["line"] <= len(lines)):
                continue
            seg = _call_slice(lines, c["line"], c["expr"], is_py=c["file"].endswith((".py", ".pyi")))
            m = STR_LIT.search(seg)
            if not m:
                continue
            url = m.group(2)
            path = TPL_EXPR.sub(":param", re.sub(r"^https?://[^/]*", "", url)).split("?")[0]
            method = None
            if c["name"] in HTTP_METHODS:
                method = c["name"].upper()
            elif c["name"] in ("fetch", "request", "ky", "got") or c["expr"] in ("axios", "fetch"):
                mm = FETCH_METHOD.search(seg)
                method = mm.group(1).upper() if mm else "GET"
            if not method:
                continue
            norm = _norm(path)
            cands = [r for r, rx in routes
                     if r["file"] != c["file"] and r["method"] in (method, "ALL", "USE") and rx.match(norm)]
            # exact method beats ALL/USE, literal path beats wildcard; id makes the pick independent of row order
            hit = min(cands, key=lambda r: (r["method"] != method, "*" in (r["full_path"] or r["path"]), r["id"]),
                      default=None)
            if hit:
                out.append({"id": c["id"], "file": c["file"], "line": c["line"], "caller": c["caller"], "expr": c["expr"],
                            "method": method, "url": redact_line(url)[0], "route": hit})
        return out


def _call_slice(lines: list, line_no: int, expr: str, is_py: bool = False) -> str:
    """Extract the single call expression starting at `expr` through its matching `)` across up to 12 lines."""
    idx = line_no - 1
    ln = lines[idx]
    pos = ln.find(expr + "(")
    if pos < 0:
        pos = ln.find(expr)
    pos = max(0, pos)
    chunk = "\n".join(lines[idx:idx + 12])
    start = chunk.find("(", pos)
    if start < 0:
        return ln[pos:]
    depth, quote, esc, line_cmt, block_cmt, in_regex, regex_cls = 0, None, False, False, False, False, False
    prev_sig = ""
    i = start
    while i < len(chunk):
        ch = chunk[i]
        if line_cmt:
            if ch == "\n":
                line_cmt = False
        elif block_cmt:
            if chunk[i:i + 2] == "*/":
                block_cmt = False
                i += 2
                continue
        elif esc:
            esc = False
        elif quote:
            if ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
                prev_sig = quote
        elif in_regex:
            if ch == "\\":
                esc = True
            elif ch == "[" and not regex_cls:
                regex_cls = True
            elif ch == "]" and regex_cls:
                regex_cls = False
            elif ch == "/" and not regex_cls:
                in_regex = False
                prev_sig = "/"
        elif is_py and ch == "#":
            line_cmt = True
        elif not is_py and chunk[i:i + 2] == "//":
            line_cmt = True
            i += 2
            continue
        elif not is_py and chunk[i:i + 2] == "/*":
            block_cmt = True
            i += 2
            continue
        elif not is_py and ch == "/" and prev_sig in ("", "(", ",", ":", "=", "[", "{", "!", "&", "|", "?", ";", "~", "+", "-", "*", "%", "^", "<", ">"):
            in_regex = True
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "(":
            depth += 1
            prev_sig = "("
        elif ch == ")":
            depth -= 1
            prev_sig = ")"
            if depth == 0:
                return chunk[pos:i + 1]
        elif not ch.isspace():
            prev_sig = ch
        i += 1
    return chunk[pos:]


def _norm(p: str) -> str:
    p = re.sub(r"/{2,}", "/", p)
    return p.rstrip("/") or "/"


def _route_regex(path: str):
    p = _norm(path)
    parts = []
    for seg in p.split("/"):
        if seg.startswith(":") or seg.startswith("<") or (seg.startswith("{") and seg.endswith("}")):
            parts.append(r"[^/]+")
        elif seg in ("*", "(.*)"):
            parts.append(r".*")
        else:
            parts.append(re.escape(seg).replace(r"\:param", r"[^/]+"))
    return re.compile("^" + "/".join(parts) + "/?$")
