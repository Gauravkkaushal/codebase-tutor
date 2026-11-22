"""Cross-file resolution: imports, bindings, calls, routes, test links."""
from __future__ import annotations

import json
import posixpath
import re
from collections import defaultdict
from pathlib import Path

JS_EXTS = [".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs", ".mts", ".cts", ".json"]
COMMON_NAMES = {
    "get", "set", "has", "add", "push", "pop", "map", "filter", "reduce", "forEach", "find", "then", "catch",
    "call", "apply", "bind", "json", "send", "status", "render", "on", "once", "emit", "log", "error", "warn",
    "info", "debug", "toString", "valueOf", "keys", "values", "entries", "join", "split", "slice", "splice",
    "indexOf", "includes", "replace", "trim", "parse", "stringify", "assign", "create", "freeze", "test",
    "exec", "match", "next", "end", "write", "read", "close", "open", "start", "stop", "run", "init", "update",
    "delete", "remove", "append", "extend", "format", "print", "len", "str", "int", "list", "dict", "range",
    "isinstance", "super", "require", "resolve", "reject", "use", "handle", "listen", "save", "load", "copy",
    "sort", "items", "lower", "upper", "strip", "encode", "decode", "setdefault", "describe", "it", "expect",
    "equal", "ok", "assert", "Error", "Promise", "Object", "Array", "String", "Number", "Boolean", "Date",
    "main", "setup", "teardown", "concat", "from", "of", "is", "size", "clear", "length", "default",
}
JS_BUILTIN_RECEIVERS = {"Object", "Array", "JSON", "Math", "Number", "String", "Boolean", "Promise", "Reflect", "Symbol",
                        "Date", "RegExp", "Map", "Set", "WeakMap", "WeakSet", "ArrayBuffer", "Intl", "console", "process",
                        "Buffer", "globalThis", "window", "document", "Error", "BigInt", "Atomics", "URL", "URLSearchParams"}
JS_BUILTIN_FUNCS = {"parseInt", "parseFloat", "isNaN", "isFinite", "encodeURIComponent", "decodeURIComponent",
                    "encodeURI", "decodeURI", "setTimeout", "setInterval", "clearTimeout", "clearInterval",
                    "setImmediate", "clearImmediate", "queueMicrotask", "structuredClone", "fetch", "require",
                    "String", "Number", "Boolean", "Array", "Object", "Symbol", "BigInt", "Date", "Error", "TypeError",
                    "RangeError", "Promise", "Map", "Set", "RegExp", "Function", "eval", "alert"}
try:
    import builtins as _b
    PY_BUILTINS = set(dir(_b))
except Exception:  # pragma: no cover
    PY_BUILTINS = set()
LEXICAL_RECEIVERS = {"self", "cls"}
THIS_RECEIVERS = {"this"}


def _strip_json_comments(text: str) -> str:
    text = re.sub(r"//.*?$", "", text, flags=re.M)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r",(\s*[}\]])", r"\1", text)


class Resolver:
    def __init__(self, root: Path, store, all_paths: set):
        self.root = Path(root)
        self.store = store
        self.paths = all_paths
        self.dirs = set()
        for p in all_paths:
            d = posixpath.dirname(p)
            while d and d not in self.dirs:
                self.dirs.add(d)
                d = posixpath.dirname(d)
        self._load_ts_paths()
        self._load_workspaces()
        self._load_py_roots()

    # ------------------------------------------------------------ config discovery
    def _load_ts_paths(self):
        self.ts_aliases = []  # (prefix, [targets], wildcard)
        self.ts_base = ""
        for name in ("tsconfig.json", "jsconfig.json"):
            if name in self.paths:
                try:
                    cfg = json.loads(_strip_json_comments((self.root / name).read_text(encoding="utf-8")))
                except (OSError, ValueError):
                    continue
                opts = cfg.get("compilerOptions", {}) or {}
                self.ts_base = (opts.get("baseUrl") or "").strip("./")
                for alias, targets in (opts.get("paths") or {}).items():
                    wildcard = alias.endswith("*")
                    self.ts_aliases.append((alias.rstrip("*"), [t.rstrip("*") for t in targets], wildcard))
                break

    def _load_workspaces(self):
        self.workspace_pkgs = {}
        for p in self.paths:
            if p.endswith("package.json") and p != "package.json" and "node_modules" not in p:
                try:
                    data = json.loads((self.root / p).read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                name = data.get("name")
                if name:
                    self.workspace_pkgs[name] = (posixpath.dirname(p), data.get("main") or data.get("module") or "index")

    def _load_py_roots(self):
        roots = {""}
        for p in self.paths:
            base = posixpath.basename(p)
            d = posixpath.dirname(p)
            if base in ("setup.py", "pyproject.toml", "setup.cfg"):
                roots.add(d)
            parts = p.split("/")
            if "src" in parts[:-1]:
                roots.add("/".join(parts[: parts.index("src") + 1]))
        self.py_roots = sorted(roots, key=len)

    # ------------------------------------------------------------ imports
    def _try_js(self, base: str):
        base = posixpath.normpath(base)
        if base.startswith(".."):
            return None
        if base == ".":
            base = ""
        cands = [base] if base in self.paths else []
        stem, ext = posixpath.splitext(base)
        if ext in (".js", ".jsx", ".mjs", ".cjs"):
            cands += [stem + e for e in (".ts", ".tsx", ".mts", ".cts")]
        cands += [base + e for e in JS_EXTS]
        cands += [posixpath.join(base, "index" + e) for e in JS_EXTS]
        for c in cands:
            if c in self.paths:
                return c
        if base in self.dirs and posixpath.join(base, "package.json") in self.paths:
            try:
                main = json.loads((self.root / base / "package.json").read_text(encoding="utf-8")).get("main")
            except (OSError, ValueError):
                main = None
            if main:
                return self._try_js(posixpath.join(base, main))
        return None

    def resolve_js(self, from_file: str, spec: str):
        """Returns (resolved_path|None, external: bool)."""
        if spec.startswith("."):
            return self._try_js(posixpath.join(posixpath.dirname(from_file), spec)), False
        if spec.startswith("/"):
            return self._try_js(spec.lstrip("/")), False
        for prefix, targets, wildcard in self.ts_aliases:
            if (wildcard and spec.startswith(prefix)) or spec == prefix:
                rest = spec[len(prefix):] if wildcard else ""
                for t in targets:
                    r = self._try_js(posixpath.join(self.ts_base, t + rest))
                    if r:
                        return r, False
        parts = spec.split("/")
        pkg = "/".join(parts[:2]) if spec.startswith("@") else parts[0]
        if pkg in self.workspace_pkgs:
            d, main = self.workspace_pkgs[pkg]
            sub = spec[len(pkg):].lstrip("/")
            r = self._try_js(posixpath.join(d, sub)) if sub else (self._try_js(posixpath.join(d, main)) or self._try_js(posixpath.join(d, "src/index")))
            if r:
                return r, False
        if self.ts_base:
            r = self._try_js(posixpath.join(self.ts_base, spec))
            if r:
                return r, False
        return None, True

    def _try_py(self, dotted_path: str):
        for c in (dotted_path + ".py", posixpath.join(dotted_path, "__init__.py"), dotted_path + ".pyi"):
            c = c.lstrip("/")
            if c in self.paths:
                return c
        return None

    def resolve_py(self, from_file: str, module: str):
        level = len(module) - len(module.lstrip("."))
        name = module.lstrip(".")
        if level:
            base = posixpath.dirname(from_file)
            for _ in range(level - 1):
                base = posixpath.dirname(base)
            target = posixpath.join(base, name.replace(".", "/")) if name else base
            r = self._try_py(target)
            return r, False
        rel = name.replace(".", "/")
        for root in self.py_roots:
            r = self._try_py(posixpath.join(root, rel) if root else rel)
            if r:
                return r, False
        # sibling-module import (scripts run from their directory)
        r = self._try_py(posixpath.join(posixpath.dirname(from_file), rel))
        if r:
            return r, False
        return None, True

    def resolve_module(self, from_file: str, lang: str, spec: str):
        if lang == "python":
            return self.resolve_py(from_file, spec)
        return self.resolve_js(from_file, spec)


def resolve_all(root: Path, store, all_paths: set) -> dict:
    """Global resolution pass. Returns stats."""
    db = store.db
    res = Resolver(root, store, all_paths)
    langs = {r["path"]: r["lang"] for r in db.execute("SELECT path, lang FROM files")}

    # 1. imports
    imp_rows = db.execute("SELECT id, file, module FROM imports").fetchall()
    updates = []
    for r in imp_rows:
        resolved, external = res.resolve_module(r["file"], langs.get(r["file"], ""), r["module"])
        updates.append((resolved, int(external), r["id"]))
    db.executemany("UPDATE imports SET resolved=?, external=? WHERE id=?", updates)

    # 2. symbol tables
    syms_by_file_qual = defaultdict(dict)
    syms_by_name = defaultdict(list)
    syms_by_qual_global = defaultdict(list)
    sym_info = {}
    for s in db.execute("SELECT id, file, name, qualname, kind, parent FROM symbols"):
        syms_by_file_qual[s["file"]][s["qualname"]] = s["id"]
        sym_info[s["id"]] = (s["file"], s["qualname"], s["kind"], s["parent"], s["name"])
        if s["kind"] in ("function", "method", "class", "handler"):
            syms_by_name[s["name"]].append(s["id"])
            syms_by_qual_global[s["qualname"]].append(s["id"])
    exports = defaultdict(dict)
    for e in db.execute("SELECT file, name, local FROM exports"):
        exports[e["file"]].setdefault(e["name"], e["local"])

    # 3. bindings: file -> local -> (kind, target_file, imported_name, module)
    bindings = defaultdict(dict)
    for r in db.execute("SELECT file, module, names, resolved, external FROM imports"):
        names = json.loads(r["names"] or "[]")
        lang = langs.get(r["file"], "")
        for imported, local in names:
            if local == "*" and imported == "*":
                continue
            if lang == "python" and imported not in ("*",):
                mod = r["module"]
                sub, _ = res.resolve_py(r["file"], mod + imported if mod.endswith(".") else mod + "." + imported)
                if sub:
                    bindings[r["file"]][local] = ("module", sub, "*", r["module"])
                    continue
            if imported in ("*",) or (imported == "default" and lang != "python" and r["resolved"] and not exports[r["resolved"]].get("default")):
                bindings[r["file"]][local] = ("module", r["resolved"], "*", r["module"])
            else:
                bindings[r["file"]][local] = ("symbol", r["resolved"], imported, r["module"])

    def find_export(file, name, depth=0):
        if not file or depth > 4:
            return None
        local = exports[file].get(name)
        table = syms_by_file_qual.get(file, {})
        if local is None:
            if name in table:
                return table[name]
            return None
        if local.startswith("import:"):
            _, mod, imported = local.split(":", 2)
            target, _ = res.resolve_module(file, langs.get(file, ""), mod)
            return find_export(target, imported, depth + 1)
        if local in table:
            return table[local]
        b = bindings[file].get(local)
        if b and b[1]:
            if b[0] == "symbol":
                return find_export(b[1], b[2], depth + 1)
        return None

    def default_alias(file):
        """Name of the object/function aliased as the module's default export (CJS)."""
        return exports[file].get("default") if file else None

    # 4. calls
    stats = defaultdict(int)
    call_updates = []
    for c in db.execute("SELECT id, file, caller, expr, name, receiver FROM calls"):
        f, caller, name, recv, expr = c["file"], c["caller"], c["name"], c["receiver"], c["expr"]
        table = syms_by_file_qual.get(f, {})
        rid, how, ext = None, "unresolved", None
        if expr.startswith("new "):
            expr_core = expr[4:]
        else:
            expr_core = expr
        if recv is None:
            if caller and f"{caller}.{name}" in table:
                rid, how = table[f"{caller}.{name}"], "verified-source"
            elif name in table:
                rid, how = table[name], "verified-source"
            elif name in bindings[f]:
                kind, tfile, imported, module = bindings[f][name]
                if tfile:
                    rid = find_export(tfile, imported) if kind == "symbol" else (find_export(tfile, "default"))
                    how = "verified-source" if rid else "unresolved"
                else:
                    ext, how = module, "external"
            elif name not in COMMON_NAMES and len(syms_by_name.get(name, [])) == 1:
                rid, how = syms_by_name[name][0], "structurally-inferred"
        else:
            parts = expr_core.split(".")
            direct_member = len(parts) == 2 and parts[0] == recv
            if recv in LEXICAL_RECEIVERS or recv in THIS_RECEIVERS:
                parent = sym_info.get(table.get(caller), (None, None, None, None, None))[3] if caller else None
                cand = f"{parent}.{name}" if parent else None
                if cand and cand in table and direct_member:
                    rid = table[cand]
                    how = "verified-source" if recv in LEXICAL_RECEIVERS else "structurally-inferred"
                else:
                    same = [i for q, i in table.items() if q.endswith("." + name)]
                    if len(same) == 1 and direct_member:
                        rid, how = same[0], "structurally-inferred"
            elif recv in bindings[f]:
                kind, tfile, imported, module = bindings[f][recv]
                if not tfile:
                    ext, how = module, "external"
                elif direct_member:
                    if kind == "module":
                        rid = find_export(tfile, name)
                        if rid is None:
                            alias = default_alias(tfile)
                            if alias:
                                rid = syms_by_file_qual.get(tfile, {}).get(f"{alias}.{name}")
                        how = "verified-source" if rid else "unresolved"
                    else:
                        base = find_export(tfile, imported)
                        if base is not None:
                            bfile, bqual = sym_info[base][0], sym_info[base][1]
                            rid = syms_by_file_qual.get(bfile, {}).get(f"{bqual}.{name}")
                            how = "verified-source" if rid else "unresolved"
            elif direct_member and f"{recv}.{name}" in table:
                rid, how = table[f"{recv}.{name}"], "verified-source"
            if rid is None and how == "unresolved" and direct_member:
                glob = syms_by_qual_global.get(f"{recv}.{name}", [])
                if len(glob) == 1:
                    rid, how = glob[0], "structurally-inferred"
                elif name not in COMMON_NAMES and len(syms_by_name.get(name, [])) == 1 and recv not in bindings[f]:
                    rid, how = syms_by_name[name][0], "structurally-inferred"
        if rid is None and how == "unresolved":
            lang = langs.get(f, "")
            root_name = (recv or name)
            if lang == "python" and recv is None and name in PY_BUILTINS:
                how = "builtin"
            elif lang != "python" and ((recv is None and name in JS_BUILTIN_FUNCS) or root_name in JS_BUILTIN_RECEIVERS
                                       or expr_core.split(".")[0] in JS_BUILTIN_RECEIVERS):
                how = "builtin"
        stats[how] += 1
        call_updates.append((rid, how, ext, c["id"]))
    db.executemany("UPDATE calls SET resolved_id=?, resolution=?, external=? WHERE id=?", call_updates)

    # 5. routes: handler ids, mounts, full paths
    route_rows = db.execute("SELECT id, file, method, path, handlers, router, kind FROM routes").fetchall()
    mounts = defaultdict(list)  # target_file -> [prefix]
    handler_updates = []
    for r in route_rows:
        f = r["file"]
        table = syms_by_file_qual.get(f, {})
        ids, mount_target = [], None
        for h in json.loads(r["handlers"] or "[]"):
            hid = table.get(h)
            req = re.match(r"""require\(\s*['"]([^'"]+)['"]\s*\)""", h)
            if hid is None and req:
                tfile, _ = res.resolve_module(f, langs.get(f, ""), req.group(1))
                if tfile:
                    hid = find_export(tfile, "default")
                    if r["kind"] in ("middleware", "mount"):
                        mount_target = tfile
            elif hid is None:
                head = h.split("(")[0]
                parts = head.split(".")
                if head in bindings[f]:
                    kind, tfile, imported, module = bindings[f][head]
                    if tfile:
                        hid = find_export(tfile, imported) if kind == "symbol" else find_export(tfile, "default")
                        if r["kind"] in ("middleware", "mount") and tfile:
                            mount_target = tfile
                elif len(parts) == 2 and parts[0] in bindings[f]:
                    kind, tfile, imported, module = bindings[f][parts[0]]
                    if tfile:
                        hid = find_export(tfile, parts[1]) if kind == "module" else None
                elif langs.get(f) == "python" and h in table:
                    hid = table[h]
            ids.append(hid)
        kind = r["kind"]
        is_py = langs.get(f) == "python"
        if not is_py and kind in ("middleware", "mount"):
            if mount_target and r["path"] not in ("/", ""):
                kind = "mount"
                mounts[mount_target].append(r["path"])
            else:
                kind = "middleware"
        elif kind == "mount" and is_py:
            m = re.match(r"include\(\s*['\"]([\w.]+)['\"]", (json.loads(r["handlers"]) or [""])[0])
            if m:
                tfile, _ = res.resolve_py(f, m.group(1))
                if tfile:
                    mount_target = tfile
                    mounts[tfile].append(r["path"])
        handler_updates.append((json.dumps(ids), kind, mount_target, r["id"]))
    db.executemany("UPDATE routes SET handler_ids=?, kind=?, mount_target=? WHERE id=?", handler_updates)
    full_updates = []
    for r in route_rows:
        prefixes = mounts.get(r["file"], [])
        prefix = prefixes[0].rstrip("/") if prefixes else ""
        path = r["path"] if r["path"].startswith("/") else "/" + r["path"]
        full = (prefix + path) if prefix else path
        if prefix and path == "/" and langs.get(r["file"]) != "python":
            full = prefix  # Express/Hono/Koa: router.get('/') under app.use('/api/cart') answers GET /api/cart
        full_updates.append((full, r["id"]))
    db.executemany("UPDATE routes SET full_path=? WHERE id=?", full_updates)
    _file_routes(db, syms_by_file_qual, exports)

    # 6. test links (file level)
    db.execute("DELETE FROM test_links")
    roles = {r["path"]: r["role"] for r in db.execute("SELECT path, role FROM files")}
    imports_of = defaultdict(set)
    for r in db.execute("SELECT file, resolved FROM imports WHERE resolved IS NOT NULL"):
        imports_of[r["file"]].add(r["resolved"])
    links = []
    for t, role in roles.items():
        if role != "test":
            continue
        seen = {}
        frontier = [(x, 0) for x in imports_of.get(t, ())]
        while frontier:
            tgt, depth = frontier.pop()
            if tgt in seen or depth > 2:
                continue
            seen[tgt] = depth
            for nxt in imports_of.get(tgt, ()):
                frontier.append((nxt, depth + 1))
        for tgt, depth in seen.items():
            if roles.get(tgt) in ("source",) and tgt != t:
                links.append((t, tgt, "import" if depth == 0 else f"import+{depth}",
                              "verified-source" if depth == 0 else "structurally-inferred"))
    db.executemany("INSERT INTO test_links(test_file,target_file,via,confidence) VALUES(?,?,?,?)", links)
    store.commit()
    return dict(stats)


NEXT_PAGES = re.compile(r"(?:^|/)pages/api/(.+)\.(?:js|jsx|ts|tsx)$")
NEXT_APP = re.compile(r"(?:^|/)app/(.*?)/?route\.(?:js|ts)$")


def _file_routes(db, syms_by_file_qual, exports):
    """File-system routes (Next.js)."""
    db.execute("DELETE FROM routes WHERE framework='next'")
    rows = []
    for r in db.execute("SELECT path FROM files WHERE role='source' AND lang IN ('javascript','typescript','tsx')"):
        p = r["path"]
        m = NEXT_PAGES.search(p)
        if m:
            sub = re.sub(r"/?index$", "", m.group(1))
            local = exports[p].get("default")
            hid = syms_by_file_qual.get(p, {}).get(local) if local else None
            rows.append((p, 1, "next", "ANY", "/api/" + sub if sub else "/api", json.dumps([local or "default"]),
                         "pages", "route", "/api/" + sub if sub else "/api", json.dumps([hid]), None))
            continue
        m = NEXT_APP.search(p)
        if m:
            sub = "/".join(seg for seg in m.group(1).split("/") if not (seg.startswith("(") and seg.endswith(")")))
            for meth in ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                hid = syms_by_file_qual.get(p, {}).get(meth)
                if hid:
                    rows.append((p, 1, "next", meth, "/" + sub, json.dumps([meth]), "app", "route", "/" + sub,
                                 json.dumps([hid]), None))
    db.executemany("INSERT INTO routes(file,line,framework,method,path,handlers,router,kind,full_path,handler_ids,mount_target)"
                   " VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows)
