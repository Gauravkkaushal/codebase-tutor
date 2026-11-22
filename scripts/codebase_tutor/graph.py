"""Queries over the knowledge store: symbols, callers/callees, dependencies, module graph, cycles."""
from __future__ import annotations

import json
import posixpath
import re
from collections import defaultdict

from .store import row_dict


def sym_row(store, sid: int) -> dict | None:
    return row_dict(store.one("SELECT * FROM symbols WHERE id=?", (sid,)))


def find_symbols(store, query: str, limit: int = 30) -> list:
    """Resolve a user-supplied target: id, qualname, name, 'file:line', or substring."""
    q = query.strip()
    if q.isdigit():
        r = sym_row(store, int(q))
        return [r] if r else []
    m = re.match(r"^(.+?):(\d+)$", q)
    if m:
        rows = store.q("SELECT * FROM symbols WHERE file=? AND start_line<=? AND end_line>=? ORDER BY (end_line-start_line)",
                       (m.group(1), int(m.group(2)), int(m.group(2))))
        return [row_dict(r) for r in rows[:1]]
    if "#" in q:
        f, _, name = q.partition("#")
        rows = store.q("SELECT * FROM symbols WHERE file=? AND (qualname=? OR name=?)", (f, name, name))
        return [row_dict(r) for r in rows]
    exact = store.q("SELECT * FROM symbols WHERE qualname=? OR name=? ORDER BY kind='handler', file LIMIT ?", (q, q, limit))
    if exact:
        return [row_dict(r) for r in exact]
    like = store.q("SELECT * FROM symbols WHERE qualname LIKE ? OR name LIKE ? ORDER BY length(qualname) LIMIT ?",
                   (f"%{q}%", f"%{q}%", limit))
    return [row_dict(r) for r in like]


def search(store, query: str, limit: int = 40) -> dict:
    like = f"%{query}%"
    syms = [row_dict(r) for r in store.q(
        "SELECT s.id, s.file, s.name, s.qualname, s.kind, s.start_line, s.end_line, s.exported, f.role FROM symbols s "
        "JOIN files f ON f.path=s.file WHERE s.qualname LIKE ? OR s.name LIKE ? "
        "ORDER BY (s.name=?) DESC, f.role='test', length(s.qualname) LIMIT ?", (like, like, query, limit))]
    files = [r[0] for r in store.q("SELECT path FROM files WHERE path LIKE ? ORDER BY role='test', length(path) LIMIT ?",
                                   (like, limit))]
    routes = [row_dict(r) for r in store.q(
        "SELECT id, file, line, method, path, full_path, kind FROM routes WHERE full_path LIKE ? OR path LIKE ? OR handlers LIKE ? LIMIT ?",
        (like, like, like, limit))]
    return {"query": query, "symbols": syms, "files": files, "routes": routes}


def callers(store, sid: int) -> list:
    rows = store.q("SELECT c.file, c.line, c.caller, c.expr, c.resolution FROM calls c WHERE c.resolved_id=? ORDER BY c.file, c.line", (sid,))
    out = []
    for r in rows:
        d = row_dict(r)
        caller_sym = store.one("SELECT id, kind FROM symbols WHERE file=? AND qualname=?", (r["file"], r["caller"])) if r["caller"] else None
        d["caller_id"] = caller_sym["id"] if caller_sym else None
        out.append(d)
    return out


def callees(store, sid: int) -> list:
    s = sym_row(store, sid)
    if not s:
        return []
    rows = store.q("SELECT line, expr, name, resolved_id, resolution, external FROM calls WHERE file=? AND caller=? ORDER BY line",
                   (s["file"], s["qualname"]))
    out = []
    for r in rows:
        d = row_dict(r)
        if r["resolved_id"]:
            t = sym_row(store, r["resolved_id"])
            d["target"] = {"id": t["id"], "file": t["file"], "qualname": t["qualname"], "line": t["start_line"]} if t else None
        out.append(d)
    return out


def imports_of(store, path: str) -> list:
    return [row_dict(r) for r in store.q("SELECT line, module, names, resolved, external, kind FROM imports WHERE file=? ORDER BY line", (path,))]


def importers_of(store, path: str) -> list:
    return [row_dict(r) for r in store.q("SELECT file, line, module FROM imports WHERE resolved=? ORDER BY file", (path,))]


def tests_for(store, root, sid: int | None = None, path: str | None = None, limit: int = 25) -> list:
    """Rank test files related to a symbol or file. Signals are explicit so the agent can explain the ranking."""
    from pathlib import Path
    s = sym_row(store, sid) if sid else None
    target_file = s["file"] if s else path
    scores = defaultdict(lambda: {"score": 0, "signals": []})
    for r in store.q("SELECT test_file, via, confidence FROM test_links WHERE target_file=?", (target_file,)):
        w = 3 if r["via"] == "import" else 1
        scores[r["test_file"]]["score"] += w
        scores[r["test_file"]]["signals"].append(f"{r['via']} of {target_file}")
    if s:
        name = s["name"]
        pat = re.compile(r"\b" + re.escape(name) + r"\b")
        for r in store.q("SELECT path FROM files WHERE role='test' AND lang IN ('python','javascript','typescript','tsx')"):
            tf = r["path"]
            base = posixpath.basename(tf).lower()
            if name.lower() in base and len(name) > 2:
                scores[tf]["score"] += 4
                scores[tf]["signals"].append(f"file name mentions '{name}'")
            try:
                text = (Path(root) / tf).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits = len(pat.findall(text))
            if hits and len(name) > 2:
                scores[tf]["score"] += min(3, hits)
                scores[tf]["signals"].append(f"mentions '{name}' {hits}x")
        for r in store.q("SELECT c.file, MIN(c.resolution) AS res, COUNT(*) AS n FROM calls c JOIN files f ON f.path=c.file "
                         "WHERE c.resolved_id=? AND f.role='test' GROUP BY c.file", (sid,)):
            scores[r["file"]]["score"] += 5 if r["res"] == "verified-source" else 3
            scores[r["file"]]["signals"].append(f"calls the symbol {r['n']}x ({r['res']})")
    ranked = sorted(({"test_file": k, **v} for k, v in scores.items() if v["score"] > 0), key=lambda x: -x["score"])
    for x in ranked:
        x["signals"] = sorted(set(x["signals"]))
        x["confidence"] = "verified-source" if any("(verified-source)" in sg or sg.startswith("import of") for sg in x["signals"]) else "structurally-inferred"
    return ranked[:limit]


def module_of(path: str, depth: int = 2) -> str:
    parts = path.split("/")
    if len(parts) <= 1:
        return "(root)"
    return "/".join(parts[: min(depth, len(parts) - 1)])


def module_graph(store, depth: int = 2, include_tests: bool = False) -> dict:
    roles = {r["path"]: r["role"] for r in store.q("SELECT path, role FROM files")}
    lines = {r["path"]: r["lines"] or 0 for r in store.q("SELECT path, lines FROM files")}
    keep_roles = {"source"} | ({"test"} if include_tests else set())
    nodes = defaultdict(lambda: {"files": 0, "lines": 0, "symbols": 0, "langs": defaultdict(int), "roles": defaultdict(int)})
    langs = {r["path"]: r["lang"] for r in store.q("SELECT path, lang FROM files")}
    for p, role in roles.items():
        if role in keep_roles:
            m = module_of(p, depth)
            nodes[m]["files"] += 1
            nodes[m]["lines"] += lines.get(p, 0)
            nodes[m]["langs"][langs.get(p)] += 1
            nodes[m]["roles"][role] += 1
    for r in store.q("SELECT file, COUNT(*) n FROM symbols GROUP BY file"):
        if roles.get(r["file"]) in keep_roles:
            nodes[module_of(r["file"], depth)]["symbols"] += r["n"]
    edges = defaultdict(lambda: {"imports": 0, "calls": 0, "examples": []})
    for r in store.q("SELECT file, line, resolved FROM imports WHERE resolved IS NOT NULL"):
        if roles.get(r["file"]) in keep_roles and roles.get(r["resolved"]) in keep_roles:
            a, b = module_of(r["file"], depth), module_of(r["resolved"], depth)
            if a != b:
                e = edges[(a, b)]
                e["imports"] += 1
                if len(e["examples"]) < 3:
                    e["examples"].append({"file": r["file"], "line": r["line"], "to": r["resolved"]})
    for r in store.q("SELECT c.file, s.file AS tfile FROM calls c JOIN symbols s ON s.id=c.resolved_id"):
        if roles.get(r["file"]) in keep_roles and roles.get(r["tfile"]) in keep_roles:
            a, b = module_of(r["file"], depth), module_of(r["tfile"], depth)
            if a != b:
                edges[(a, b)]["calls"] += 1
    out_nodes = [{"id": k, **{kk: (dict(vv) if isinstance(vv, defaultdict) else vv) for kk, vv in v.items()}} for k, v in nodes.items()]
    out_edges = [{"source": a, "target": b, **v} for (a, b), v in edges.items()]
    return {"depth": depth, "nodes": out_nodes, "edges": out_edges}


def file_graph(store, include_tests: bool = False) -> dict:
    roles = {r["path"]: r["role"] for r in store.q("SELECT path, role FROM files")}
    keep = {"source"} | ({"test"} if include_tests else set())
    edges = defaultdict(int)
    for r in store.q("SELECT file, resolved FROM imports WHERE resolved IS NOT NULL"):
        if roles.get(r["file"]) in keep and roles.get(r["resolved"]) in keep and r["file"] != r["resolved"]:
            edges[(r["file"], r["resolved"])] += 1
    return {"edges": [{"source": a, "target": b, "count": n} for (a, b), n in edges.items()]}


def cycles(store) -> list:
    """Strongly connected components (size > 1) in the file import graph (Tarjan, iterative)."""
    g = defaultdict(set)
    for e in file_graph(store)["edges"]:
        g[e["source"]].add(e["target"])
    index, low, on, stack, out = {}, {}, set(), [], []
    counter = [0]
    for start in list(g):
        if start in index:
            continue
        work = [(start, iter(sorted(g[start])))]
        index[start] = low[start] = counter[0]
        counter[0] += 1
        stack.append(start)
        on.add(start)
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter[0]
                    counter[0] += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(sorted(g[w]))))
                    advanced = True
                    break
                elif w in on:
                    low[v] = min(low[v], index[w])
            if advanced:
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[v])
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                if len(comp) > 1:
                    out.append(sorted(comp))
    return out


def orphans(store) -> list:
    """Source files nobody imports and that are not entry points (candidates for dead code or dynamic loading)."""
    imported = {r[0] for r in store.q("SELECT DISTINCT resolved FROM imports WHERE resolved IS NOT NULL")}
    entries = {r[0] for r in store.q("SELECT path FROM files WHERE entry IS NOT NULL")}
    rows = store.q("SELECT path FROM files WHERE role='source' AND lang IN ('python','javascript','typescript','tsx') AND status IN ('analyzed','partial')")
    return [r[0] for r in rows if r[0] not in imported and r[0] not in entries
            and not posixpath.basename(r[0]).startswith(("index.", "__init__", "main.", "app.", "server.", "manage."))]


def layer_hint(path: str) -> str | None:
    """Naming-convention layer hint (labelled as inferred in the UI)."""
    p = "/" + path.lower()
    for key, layer in (("/routes/", "routing"), ("/router", "routing"), ("/controllers/", "controller"),
                       ("/handlers/", "controller"), ("/views/", "view"), ("/middleware", "middleware"),
                       ("/services/", "service"), ("/models/", "model"), ("/schemas/", "model"), ("/db/", "data"),
                       ("/repositories/", "data"), ("/migrations/", "data"), ("/utils/", "utility"), ("/lib/", "library"),
                       ("/helpers/", "utility"), ("/components/", "ui"), ("/pages/", "ui"), ("/api/", "api"),
                       ("/config", "config"), ("/test", "test"), ("/examples/", "example")):
        if key in p:
            return layer
    return None


def symbol_card(store, root, sid: int) -> dict:
    s = sym_row(store, sid)
    if not s:
        return {}
    ctl = [row_dict(r) for r in store.q("SELECT line, kind, text, outcome FROM control WHERE file=? AND symbol=? ORDER BY line",
                                        (s["file"], s["qualname"]))]
    routes = [row_dict(r) for r in store.q("SELECT file, line, method, full_path, handler_ids FROM routes WHERE handler_ids LIKE ?",
                                            (f"%{sid}%",)) if sid in json.loads(r["handler_ids"] or "[]")]
    for r in routes:
        r.pop("handler_ids", None)
    return {"symbol": s, "callers": callers(store, sid), "callees": callees(store, sid), "control_points": ctl,
            "routes": routes, "tests": tests_for(store, root, sid=sid, limit=10)}
