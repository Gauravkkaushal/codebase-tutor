"""Static (source-inferred) execution flows: Level 1 of the Simulation Lab."""
from __future__ import annotations

import json
import re
import time

from .config import data_dir
from .evidence import EvidenceError, read_lines, text_hash
from .graph import find_symbols, sym_row
from .resolve import COMMON_NAMES
from .snapshots import git_info
from .store import row_dict

ROUTE_TARGET = re.compile(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|ALL|USE|ANY)\s+(\S+)$", re.I)
RANK = {"verified-source": 0, "structurally-inferred": 1, "external": 1, "unresolved": 2}
MAX_STEPS = 400


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()[:80] or "flow"


class _Tracer:
    def __init__(self, store, root, depth):
        self.store, self.root, self.depth = store, root, depth
        self.steps = []
        self.visited = set()
        self.lines_cache = {}
        self.weakest = "verified-source"
        self.truncated = False

    def line_hash(self, file, line):
        if file not in self.lines_cache:
            try:
                self.lines_cache[file] = read_lines(self.root, file)
            except EvidenceError:
                self.lines_cache[file] = []
        lines = self.lines_cache[file]
        if 1 <= line <= len(lines):
            return text_hash(lines[line - 1:line]), lines[line - 1].strip()
        return None, ""

    def add(self, **kw):
        if len(self.steps) >= MAX_STEPS:
            self.truncated = True
            return None
        th, src = self.line_hash(kw["file"], kw["line"]) if kw.get("file") and kw.get("line") else (None, "")
        kw.setdefault("end_line", kw.get("line"))
        kw["text_hash"] = th
        kw["source_line"] = src[:200]
        kw["n"] = len(self.steps) + 1
        ver = kw.get("verification", "verified-source")
        if RANK.get(ver, 0) > RANK.get(self.weakest, 0) and ver != "unresolved":
            self.weakest = ver
        self.steps.append(kw)
        return kw

    def walk(self, sid, level, how="verified-source", via=None):
        s = sym_row(self.store, sid)
        if s is None:
            return
        if sid in self.visited:
            self.add(kind="revisit", file=s["file"], line=s["start_line"], symbol=s["qualname"], depth=level,
                     text=f"{s['qualname']} already shown above (recursion or repeated call)", verification=how,
                     outcome="neutral", symbol_id=sid)
            return
        self.visited.add(sid)
        self.add(kind="enter", file=s["file"], line=s["start_line"], end_line=s["end_line"], symbol=s["qualname"],
                 symbol_id=sid, depth=level, text=f"enter {s['qualname']}" + (f" (called from line {via})" if via else ""),
                 signature=s["signature"], verification=how, outcome="neutral")
        events = []
        for c in self.store.q("SELECT line, kind, text, outcome FROM control WHERE file=? AND symbol=? ORDER BY line",
                              (s["file"], s["qualname"])):
            if c["kind"] in ("try",):
                continue
            events.append((c["line"], 0, "control", row_dict(c)))
        for c in self.store.q("SELECT line, expr, name, resolved_id, resolution, external FROM calls WHERE file=? AND caller=? ORDER BY line",
                              (s["file"], s["qualname"])):
            events.append((c["line"], 1, "call", row_dict(c)))
        events.sort(key=lambda e: (e[0], e[1], 0 if e[3].get("kind") in ("if", "else", "return", "throw", "raise") else 1))
        seen_lines_calls = set()
        last_ctl = None
        for line, _, kind, ev in events:
            if self.truncated:
                return
            if kind == "control":
                # Merge `return res.status(401).json(..)` + its respond/next control on the same line.
                if last_ctl and last_ctl["line"] == line and ev["kind"] in ("respond", "next-error", "next") and \
                        last_ctl["kind"] in ("return", "respond", "next-error", "next"):
                    if ev["outcome"] == "failure":
                        last_ctl["outcome"] = "failure"
                    continue
                last_ctl = self.add(kind=ev["kind"], file=s["file"], line=line, symbol=s["qualname"], depth=level + 1,
                                    text=ev["text"], outcome=ev["outcome"], verification="verified-source")
                continue
            if res_skip(ev):
                continue
            key = (line, ev["expr"])
            if key in seen_lines_calls:
                continue
            seen_lines_calls.add(key)
            res = ev["resolution"] or "unresolved"
            if ev["resolved_id"]:
                t = sym_row(self.store, ev["resolved_id"])
                self.add(kind="call", file=s["file"], line=line, symbol=s["qualname"], depth=level + 1,
                         text=f"calls {ev['expr']}() → {t['qualname']} ({t['file']}:{t['start_line']})", outcome="neutral",
                         verification=res, target_id=t["id"])
                if level + 1 < self.depth:
                    self.walk(t["id"], level + 1, res, via=line)
            elif res == "external":
                self.add(kind="external-call", file=s["file"], line=line, symbol=s["qualname"], depth=level + 1,
                         text=f"calls {ev['expr']}() from package '{ev['external']}' (not traced into dependencies)",
                         outcome="neutral", verification="verified-source", module=ev["external"])
            elif ev["name"] not in COMMON_NAMES and not ev["expr"].startswith("new "):
                self.add(kind="unresolved-call", file=s["file"], line=line, symbol=s["qualname"], depth=level + 1,
                         text=f"calls {ev['expr']}() — target not resolved statically", outcome="neutral",
                         verification="unresolved")


def res_skip(ev) -> bool:
    return (ev.get("resolution") == "builtin")


def resolve_target(store, target: str):
    m = ROUTE_TARGET.match(target.strip())
    if m:
        method, path = m.group(1).upper(), m.group(2)
        rows = store.q("SELECT r.* FROM routes r JOIN files f ON f.path=r.file WHERE (r.full_path=? OR r.path=?) "
                       "AND (r.method=? OR ?='ANY' OR r.method='ALL') ORDER BY f.role='test', r.file, r.line",
                       (path, path, method, method))
        if rows:
            return "route", [row_dict(r) for r in rows]
        return "missing", []
    found = find_symbols(store, target)
    if not found:
        return "missing", []
    exact = [s for s in found if s["qualname"] == target or s["name"] == target]
    return "symbol", (exact or found)[:1]


def outcomes_from_steps(steps: list) -> list:
    """Terminal outcomes with the guard conditions that precede them in the same function (inferred)."""
    out = []
    guards_by_symbol = {}
    for st in steps:
        sym = st.get("symbol")
        if st["kind"] == "enter":
            guards_by_symbol[st["symbol"]] = []
        elif st["kind"] in ("if", "else"):
            guards_by_symbol.setdefault(sym, []).append({"n": st["n"], "text": st["text"], "line": st["line"]})
        elif st.get("outcome") in ("success", "failure") and st["kind"] in ("return", "throw", "raise", "respond", "next-error", "catch"):
            g = guards_by_symbol.get(sym, [])
            out.append({"step": st["n"], "outcome": st["outcome"], "kind": st["kind"], "text": st["text"],
                        "file": st["file"], "line": st["line"], "symbol": sym, "nearest_guards": g[-2:],
                        "verification": "structurally-inferred"})
    return out


def trace(store, root, target: str, depth: int = 4, title: str | None = None, save: bool = True) -> dict:
    kind, items = resolve_target(store, target)
    if kind == "missing":
        return {"error": f"could not resolve '{target}' to a route or symbol", "hint": "use `ct search` or `ct routes`"}
    tr = _Tracer(store, root, depth)
    if kind == "route":
        r = items[0]
        if r.get("full_path") and r["full_path"] != r["path"]:
            mounts = store.q("SELECT file, line, path FROM routes WHERE kind='mount' AND mount_target=?", (r["file"],))
            for mrow in mounts:
                tr.add(kind="mount", file=mrow["file"], line=mrow["line"], depth=0, outcome="neutral",
                       text=f"router from {r['file']} mounted at '{mrow['path']}'", verification="verified-source")
        tr.add(kind="route", file=r["file"], line=r["line"], depth=0, outcome="neutral",
               text=f"{r['method']} {r['full_path'] or r['path']} registered on {r['router']}", verification="verified-source")
        handlers = json.loads(r["handlers"] or "[]")
        ids = json.loads(r["handler_ids"] or "[]")
        for i, (h, hid) in enumerate(zip(handlers, ids)):
            role = "handler" if i == len(handlers) - 1 else f"middleware #{i + 1}"
            if hid:
                tr.add(kind="dispatch", file=r["file"], line=r["line"], depth=0, outcome="neutral",
                       text=f"{role}: {h.split('@')[0] if h.startswith('handler:') else h}", verification="verified-source")
                tr.walk(hid, 1, "verified-source", via=r["line"])
            else:
                tr.add(kind="unresolved-handler", file=r["file"], line=r["line"], depth=0, outcome="neutral",
                       text=f"{role}: {h} (not resolved statically)", verification="unresolved")
        start_label = f"{r['method']} {r['full_path'] or r['path']}"
        other = [f"{x['file']}:{x['line']}" for x in items[1:6]]
    else:
        s = items[0]
        tr.walk(s["id"], 0)
        start_label = s["qualname"]
        other = []
    unresolved = sum(1 for st in tr.steps if st["verification"] == "unresolved")
    gi = git_info(root)
    flow = {
        "id": _slug(title or start_label),
        "title": title or f"Flow: {start_label}",
        "target": target, "start": start_label, "generated_by": "static-trace", "generated_at": time.time(),
        "git_commit": gi.get("commit"), "snapshot": store.get_meta("last_snapshot"),
        "depth": depth, "verification": tr.weakest,
        "verification_note": "Reconstructed from source code (Level 1, inferred). Not a runtime observation.",
        "steps": tr.steps, "outcomes": outcomes_from_steps(tr.steps),
        "unresolved_steps": unresolved, "truncated": tr.truncated, "other_matching_routes": other,
    }
    flow["text"] = render_text(flow)
    if save:
        p = data_dir(root) / "knowledge" / "flows" / f"{flow['id']}.json"
        p.write_text(json.dumps({k: v for k, v in flow.items() if k != "text"}, indent=1, ensure_ascii=False), encoding="utf-8")
        flow["saved_to"] = str(p.relative_to(root))
    return flow


def render_text(flow: dict) -> str:
    out = [f"{flow['title']}  [{flow['verification']}; static, not runtime]"]
    icons = {"failure": "✗", "success": "✓"}
    for st in flow["steps"]:
        ind = "  " * st.get("depth", 0)
        mark = icons.get(st.get("outcome"), "·")
        tag = "" if st["verification"] == "verified-source" else f"  [{st['verification']}]"
        out.append(f"{st['n']:>3} {ind}{mark} {st['text']}  — {st['file']}:{st['line']}{tag}")
    if flow["unresolved_steps"]:
        out.append(f"Note: {flow['unresolved_steps']} step(s) could not be resolved statically; the real path may differ.")
    if flow["truncated"]:
        out.append("Note: flow truncated; use --depth or trace a narrower target.")
    return "\n".join(out)
