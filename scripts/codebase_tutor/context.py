"""Contribution context expansion with an honest coverage table (Mode E)."""
from __future__ import annotations

import json
import re
import time
from collections import deque

from .config import data_dir
from .flows import resolve_target
from .graph import callees, callers, importers_of, imports_of, module_of, sym_row, tests_for
from .store import row_dict

SECURITY_HINT = re.compile(r"(auth|login|logout|passw|token|session|secret|permission|role|acl|csrf|jwt|crypt|hash|sanitiz|escape|admin)", re.I)


def reverse_reach(store, sid: int, max_depth: int = 4) -> dict:
    """Transitive callers (resolved edges only) up to max_depth."""
    seen = {sid: 0}
    q = deque([sid])
    while q:
        cur = q.popleft()
        d = seen[cur]
        if d >= max_depth:
            continue
        for r in store.q("SELECT c.file, c.caller FROM calls c WHERE c.resolved_id=?", (cur,)):
            if not r["caller"]:
                continue
            row = store.one("SELECT id FROM symbols WHERE file=? AND qualname=?", (r["file"], r["caller"]))
            if row and row["id"] not in seen:
                seen[row["id"]] = d + 1
                q.append(row["id"])
    return seen


def routes_reaching(store, reach: dict) -> list:
    ids = set(reach)
    out = []
    for r in store.q("SELECT r.id, r.file, r.line, r.method, r.full_path, r.handler_ids, f.role FROM routes r JOIN files f ON f.path=r.file"):
        hids = set(x for x in json.loads(r["handler_ids"] or "[]") if x)
        hit = hids & ids
        if hit:
            out.append({"method": r["method"], "path": r["full_path"], "file": r["file"], "line": r["line"],
                        "role": r["role"], "distance": min(reach[h] for h in hit)})
    return sorted(out, key=lambda x: (x["role"] == "test", x["distance"]))


def build_context(store, root, target: str, task: str | None = None, save: bool = True) -> dict:
    kind, items = resolve_target(store, target)
    file_target = None
    if kind == "missing" and store.one("SELECT 1 FROM files WHERE path=?", (target,)):
        kind, file_target = "file", target
    if kind == "missing":
        return {"error": f"cannot resolve '{target}'", "hint": "pass a symbol, file path, or 'METHOD /path'"}
    focus_ids = []
    if kind == "symbol":
        focus_ids = [items[0]["id"]]
        file_target = items[0]["file"]
    elif kind == "route":
        r = items[0]
        focus_ids = [x for x in json.loads(r["handler_ids"] or "[]") if x]
        file_target = r["file"]
    else:
        focus_ids = [s["id"] for s in store.q("SELECT id FROM symbols WHERE file=? AND kind!='variable' ORDER BY start_line", (file_target,))][:40]

    impl = [sym_row(store, i) for i in focus_ids]
    impl = [{k: s[k] for k in ("id", "qualname", "kind", "file", "start_line", "end_line", "signature", "exported")} for s in impl if s]
    direct_callers, transitive, callee_list = [], {}, []
    for sid in focus_ids[:10]:
        direct_callers += callers(store, sid)
        transitive.update({k: v for k, v in reverse_reach(store, sid).items() if k not in transitive})
        callee_list += callees(store, sid)
    names = {s["qualname"].split(".")[-1] for s in impl}
    possible_dynamic = 0
    for n in names:
        possible_dynamic += store.one("SELECT COUNT(*) FROM calls WHERE name=? AND resolution='unresolved'", (n,))[0]
    trans_syms = []
    for sid, d in sorted(transitive.items(), key=lambda kv: kv[1]):
        if d == 0:
            continue
        s = sym_row(store, sid)
        trans_syms.append({"id": sid, "qualname": s["qualname"], "file": s["file"], "line": s["start_line"], "distance": d})
    routes = routes_reaching(store, transitive)
    tests = tests_for(store, root, sid=focus_ids[0] if len(focus_ids) == 1 else None, path=file_target)
    errors = [row_dict(r) for r in store.q(
        f"SELECT file, symbol, line, kind, text FROM control WHERE kind IN ('throw','raise','catch','next-error') AND file=? "
        f"AND symbol IN ({','.join('?' * len(impl)) or 'NULL'}) ORDER BY line", (file_target, *[s["qualname"] for s in impl]))]
    callee_files = sorted({c["target"]["file"] for c in callee_list if c.get("target")})
    env = [row_dict(r) for r in store.q(
        f"SELECT name, file, line FROM env_vars WHERE file IN ({','.join('?' * (len(callee_files) + 1))}) ORDER BY name",
        (file_target, *callee_files))]
    imports = imports_of(store, file_target)
    importers = importers_of(store, file_target)
    sec_signals = []
    for s in impl:
        if SECURITY_HINT.search(s["qualname"]):
            sec_signals.append(f"symbol name '{s['qualname']}' suggests security-sensitive logic")
    for i in imports:
        if SECURITY_HINT.search(i["module"]) or i["module"] in ("bcrypt", "bcryptjs", "jsonwebtoken", "passport", "crypto"):
            sec_signals.append(f"imports '{i['module']}' (line {i['line']})")
    if env:
        sec_signals.append(f"reads environment variables: {', '.join(sorted({e['name'] for e in env})[:8])}")
    types = []
    sig_text = " ".join(s["signature"] or "" for s in impl)
    for tok in sorted(set(re.findall(r"\b([A-Z][A-Za-z0-9_]+)\b", sig_text)))[:30]:
        r = store.one("SELECT id, qualname, kind, file, start_line FROM symbols WHERE name=? AND kind IN ('interface','type','class','enum') LIMIT 1", (tok,))
        if r:
            types.append(row_dict(r))
    modules = sorted({module_of(c["file"]) for c in direct_callers} | {module_of(t["file"]) for t in trans_syms})
    siblings = [r[0] for r in store.q("SELECT path FROM files WHERE path LIKE ? AND path != ? AND role='source' LIMIT 15",
                                      (file_target.rsplit("/", 1)[0] + "/%" if "/" in file_target else "%", file_target))]
    verified_callers = sum(1 for c in direct_callers if c["resolution"] == "verified-source")
    inferred_callers = len(direct_callers) - verified_callers

    def status(found: bool, partial: bool = False):
        return "Found (partial)" if found and partial else ("Found" if found else "None found")

    coverage = [
        {"area": "Implementation", "status": status(bool(impl)), "basis": f"{len(impl)} symbol(s) extracted with exact line ranges"},
        {"area": "Callers", "status": status(bool(direct_callers), possible_dynamic > 0 or inferred_callers > 0),
         "basis": f"{verified_callers} verified, {inferred_callers} inferred; {possible_dynamic} unresolved call(s) elsewhere use the same name"},
        {"area": "Callees / dependencies", "status": status(bool(callee_list) or bool(imports)),
         "basis": f"{len(callee_list)} call sites, {len(imports)} imports in {file_target}"},
        {"area": "Types / interfaces", "status": status(bool(types)) if any(s['signature'] for s in impl) else "Not applicable",
         "basis": "matched capitalised names in signatures to type/class/interface symbols"},
        {"area": "Routes reaching this code", "status": status(bool(routes), possible_dynamic > 0), "basis": "reverse call graph (resolved edges) to route handlers"},
        {"area": "Tests", "status": status(bool(tests)), "basis": "imports, name mentions, resolved calls from test files"},
        {"area": "Error handling", "status": status(bool(errors)), "basis": "throw/raise/catch/next(err) control points"},
        {"area": "Configuration / env vars", "status": status(bool(env)), "basis": "env var names read in this file and direct callee files (values never read)"},
        {"area": "Security signals", "status": status(bool(sec_signals)), "basis": "naming + imports + env usage heuristics (inferred)"},
        {"area": "Cross-module impact", "status": "Not fully verified" if possible_dynamic or inferred_callers else ("Found" if modules else "None found"),
         "basis": f"modules with callers: {', '.join(modules[:8]) or '—'}"},
        {"area": "Edge cases", "status": "Needs agent review", "basis": "engine lists branch conditions; the agent must read and reason about them"},
    ]
    ctx = {
        "id": re.sub(r"[^A-Za-z0-9]+", "-", target).strip("-").lower()[:80] or "context",
        "target": target, "task": task, "kind": kind, "file": file_target, "generated_at": time.time(),
        "snapshot": store.get_meta("last_snapshot"),
        "implementation": impl, "direct_callers": direct_callers[:60], "transitive_callers": trans_syms[:60],
        "callees": callee_list[:80], "imports": imports, "imported_by": importers[:60], "types": types,
        "routes": routes[:40], "tests": tests, "error_handling": errors, "env_vars": env,
        "security_signals": sec_signals, "modules_affected": modules, "sibling_files": siblings,
        "branch_conditions": [row_dict(r) for r in store.q(
            f"SELECT symbol, line, text FROM control WHERE kind='if' AND file=? AND symbol IN ({','.join('?' * len(impl)) or 'NULL'}) ORDER BY line",
            (file_target, *[s["qualname"] for s in impl]))][:60],
        "coverage": coverage,
        "note": "Statuses describe what the engine located. Mark an area 'Reviewed' only after reading its evidence.",
    }
    ctx["text"] = render(ctx)
    if save:
        p = data_dir(root) / "knowledge" / "contexts" / f"{ctx['id']}.json"
        p.write_text(json.dumps({k: v for k, v in ctx.items() if k != "text"}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
        ctx["saved_to"] = str(p.relative_to(root))
    return ctx


def render(ctx: dict) -> str:
    lines = [f"Context for {ctx['target']} ({ctx['kind']}, {ctx['file']})", "", "| Area | Status | Basis |", "|---|---|---|"]
    lines += [f"| {c['area']} | {c['status']} | {c['basis']} |" for c in ctx["coverage"]]
    lines.append("")
    for s in ctx["implementation"][:10]:
        lines.append(f"- impl: {s['qualname']} — {s['file']}:{s['start_line']}-{s['end_line']}")
    for c in ctx["direct_callers"][:10]:
        lines.append(f"- caller: {c['caller'] or '(module level)'} — {c['file']}:{c['line']} [{c['resolution']}]")
    for r in ctx["routes"][:8]:
        lines.append(f"- route: {r['method']} {r['path']} — {r['file']}:{r['line']} (distance {r['distance']})")
    for t in ctx["tests"][:8]:
        lines.append(f"- test: {t['test_file']} (score {t['score']}: {'; '.join(t['signals'][:3])})")
    return "\n".join(lines)
