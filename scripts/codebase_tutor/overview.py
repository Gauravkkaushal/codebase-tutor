"""Repository overview and learning-path derivation (deterministic facts only)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from . import graph
from .analyzer import coverage
from .snapshots import git_info


def top_level_structure(store, max_children: int = 40) -> list:
    tree = defaultdict(lambda: {"files": 0, "lines": 0, "roles": Counter(), "langs": Counter()})
    for r in store.q("SELECT path, role, lang, lines FROM files"):
        parts = r["path"].split("/")
        key = parts[0] if len(parts) > 1 else "(root files)"
        t = tree[key]
        t["files"] += 1
        t["lines"] += r["lines"] or 0
        t["roles"][r["role"]] += 1
        if r["role"] in ("source", "test"):
            t["langs"][r["lang"]] += 1
    out = []
    for k, v in sorted(tree.items(), key=lambda kv: -kv[1]["files"])[:max_children]:
        out.append({"path": k, "files": v["files"], "lines": v["lines"], "roles": dict(v["roles"]),
                    "langs": dict(v["langs"].most_common(3)), "layer_hint": graph.layer_hint(k + "/")})
    return out


def hubs(store, limit: int = 15) -> list:
    """Most imported / most called source files — good first reading candidates."""
    roles = {r["path"]: r["role"] for r in store.q("SELECT path, role FROM files")}
    indeg = Counter()
    for r in store.q("SELECT resolved, COUNT(DISTINCT file) n FROM imports WHERE resolved IS NOT NULL GROUP BY resolved"):
        if roles.get(r["resolved"]) == "source":
            indeg[r["resolved"]] += r["n"]
    callin = Counter()
    for r in store.q("SELECT s.file, COUNT(*) n FROM calls c JOIN symbols s ON s.id=c.resolved_id "
                     "WHERE c.file != s.file AND c.resolution='verified-source' GROUP BY s.file"):
        if roles.get(r["file"]) == "source":
            callin[r["file"]] += r["n"]
    keys = set(indeg) | set(callin)
    ranked = sorted(keys, key=lambda k: -(indeg[k] * 3 + callin[k]))[:limit]
    return [{"file": k, "imported_by_files": indeg[k], "incoming_calls": callin[k], "calls_counted": "verified-source only"} for k in ranked]


def overview(store, root) -> dict:
    det = store.get_json("detect", {}) or {}
    cov = coverage(store)
    langs = sorted(((k, v) for k, v in cov["by_language"].items()), key=lambda kv: -kv[1]["lines"])
    total_lines = sum(v["lines"] for _, v in langs) or 1
    routes = [dict(r) for r in store.q(
        "SELECT r.file, r.line, r.framework, r.method, r.path, r.full_path, r.kind, r.handlers FROM routes r "
        "JOIN files f ON f.path=r.file WHERE f.role='source' ORDER BY r.kind!='route', r.file, r.line LIMIT 400")]
    for r in routes:
        r["handlers"] = json.loads(r["handlers"] or "[]")
    env = defaultdict(list)
    for r in store.q("SELECT name, file, line FROM env_vars ORDER BY name"):
        if len(env[r["name"]]) < 5:
            env[r["name"]].append({"file": r["file"], "line": r["line"]})
    tests = store.q("SELECT COUNT(*) FROM files WHERE role='test'")[0][0]
    sym_counts = {r[0]: r[1] for r in store.q("SELECT kind, COUNT(*) FROM symbols GROUP BY kind")}
    cyc = graph.cycles(store)
    orph = graph.orphans(store)
    summary = store.get_json("last_scan_summary", {}) or {}
    data = {
        "repo": str(root),
        "project": (det.get("project") or [None])[0],
        "git": git_info(root),
        "languages": [{"lang": k, "files": v["files"], "lines": v["lines"], "share": round(v["lines"] / total_lines, 3),
                       "analyzed": v["analyzed"], "partial": v["partial"], "inventory_only": v["inventory_only"],
                       "failed": v["failed"]} for k, v in langs],
        "frameworks": det.get("framework", []), "databases": det.get("database", []), "auth": det.get("auth", []),
        "security": det.get("security", []), "external_services": det.get("external", []), "queues": det.get("queue", []),
        "realtime": det.get("realtime", []), "test_frameworks": det.get("test", []), "build": det.get("build", []),
        "lint": det.get("lint", []), "package_managers": det.get("package_managers", []), "ci": det.get("ci", []),
        "containers": det.get("containers", []), "monorepo": (det.get("monorepo") or [None])[0],
        "docs": det.get("docs", []), "scripts": det.get("scripts", []),
        "entry_points": det.get("entry_points", []),
        "structure": top_level_structure(store),
        "hubs": hubs(store),
        "routes": routes,
        "env_var_names": [{"name": k, "refs": v} for k, v in sorted(env.items())],
        "symbols": sym_counts,
        "test_files": tests,
        "cycles": cyc[:20], "cycle_count": len(cyc),
        "orphans": orph[:30], "orphan_count": len(orph),
        "coverage": cov,
        "last_scan": summary,
        "learning_path": learning_path(store, det),
        "limitations": limitations(store, cov),
    }
    return data


def learning_path(store, det) -> list:
    steps = []
    docs = [d for d in det.get("docs", []) if d["name"].lower().startswith("readme")]
    if docs:
        steps.append({"kind": "read-doc", "target": docs[0]["file"], "why": "Project's own description of purpose and setup."})
    for e in (det.get("entry_points") or [])[:3]:
        if e.get("file"):
            steps.append({"kind": "entry-point", "target": e["file"], "why": e["reason"]})
    for h in hubs(store, 4):
        steps.append({"kind": "hub", "target": h["file"],
                      "why": f"imported by {h['imported_by_files']} files; {h['incoming_calls']} incoming calls"})
    r = store.one("SELECT file, line, method, full_path FROM routes WHERE kind='route' ORDER BY file, line LIMIT 1")
    if r:
        steps.append({"kind": "trace-route", "target": f"{r['method']} {r['full_path']}", "file": r["file"], "line": r["line"],
                      "why": "Follow one real request end to end."})
    t = store.one("SELECT test_file, COUNT(*) n FROM test_links GROUP BY test_file ORDER BY n DESC LIMIT 1")
    if t:
        steps.append({"kind": "read-test", "target": t["test_file"], "why": "Tests show intended behaviour with concrete inputs."})
    seen, out = set(), []
    for s in steps:
        if s["target"] not in seen:
            seen.add(s["target"])
            out.append(s)
    return out


def limitations(store, cov) -> list:
    notes = []
    inv_only = {k: v["inventory_only"] for k, v in cov["by_language"].items() if v["inventory_only"]}
    if inv_only:
        notes.append({"code": "inventory-only-languages", "detail": inv_only})
    partial = store.q("SELECT path, error FROM files WHERE status IN ('partial','failed') LIMIT 20")
    if partial:
        notes.append({"code": "partial-or-failed-files", "detail": [{"file": r[0], "error": r[1]} for r in partial]})
    if cov["calls_total"]:
        notes.append({"code": "unresolved-calls", "detail": {"unresolved": cov["calls_unresolved"], "total": cov["calls_total"]}})
    notes.append({"code": "static-analysis", "detail": "Dynamic dispatch, DI, reflection and config-driven wiring are not resolved."})
    return notes
