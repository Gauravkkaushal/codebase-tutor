"""Command-line interface. All commands print JSON (agent-friendly) unless --text is given."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__


def _out(obj, text: str | None = None, as_text: bool = False):
    if as_text and text is not None:
        print(text)
    else:
        print(json.dumps(obj, indent=1, ensure_ascii=False, default=str))


def _store(root):
    from .analyzer import open_store
    from .config import data_dir
    if not (data_dir(root) / "knowledge" / "index.db").exists():
        print(json.dumps({"error": "no knowledge base yet; run `ct scan` first", "repo": str(root)}))
        sys.exit(2)
    return open_store(root)


def _one_symbol(store, target):
    from .graph import find_symbols
    found = find_symbols(store, target)
    if not found:
        _out({"error": f"no symbol matches '{target}'", "hint": "try `ct search <text>`"})
        sys.exit(3)
    exact = [s for s in found if s["qualname"] == target or s["name"] == target]
    return (exact or found)[0], found


def cmd_init(a):
    from .config import init_data_dir
    d, created = init_data_dir(a.repo)
    _out({"data_dir": str(d), "created": created})


def cmd_scan(a):
    from .analyzer import scan
    _out(scan(a.repo, full=a.full, jobs=a.jobs, quiet=a.quiet, note=a.note or ""))


def cmd_status(a):
    from .analyzer import open_store
    from .config import data_dir, load_config
    from .inventory import scan_inventory
    from .snapshots import git_info
    if not (data_dir(a.repo) / "knowledge" / "index.db").exists():
        _out({"knowledge_base": False, "hint": "run `ct scan`"})
        return
    store = open_store(a.repo)
    prev = store.file_index()
    inv = scan_inventory(a.repo, load_config(a.repo), previous={p: (v[0], v[1], v[2]) for p, v in prev.items()})
    cur = inv.by_path()
    added = [p for p in cur if p not in prev]
    modified = [p for p in cur if p in prev and prev[p][2] != cur[p].hash]
    deleted = [p for p in prev if p not in cur]
    ev = {r[0]: r[1] for r in store.q("SELECT status, COUNT(*) FROM evidence GROUP BY status")}
    _out({"knowledge_base": True, "last_snapshot": store.get_meta("last_snapshot"), "git": git_info(a.repo),
          "unscanned_changes": {"added": added[:100], "modified": modified[:100], "deleted": deleted[:100],
                                "counts": [len(added), len(modified), len(deleted)]},
          "evidence_status": ev, "up_to_date": not (added or modified or deleted)})


def cmd_overview(a):
    from .overview import overview
    data = overview(_store(a.repo), a.repo)
    if a.section:
        data = {k: data.get(k) for k in a.section.split(",")}
    _out(data)


def cmd_search(a):
    from .graph import search
    _out(search(_store(a.repo), a.query, a.limit))


def cmd_symbol(a):
    from .evidence import EvidenceError, excerpt, format_excerpt
    from .graph import symbol_card
    store = _store(a.repo)
    s, found = _one_symbol(store, a.target)
    card = symbol_card(store, a.repo, s["id"])
    end = min(s["end_line"], s["start_line"] + a.max_lines - 1)
    try:
        ev = excerpt(a.repo, s["file"], s["start_line"], end, highlight=[s["start_line"]])
        card["definition_excerpt"] = format_excerpt(ev, s["qualname"]) + (
            f"\n… ({s['end_line'] - end} more lines; use `ct evidence`)" if end < s["end_line"] else "")
    except EvidenceError as e:
        card["definition_excerpt"] = f"(excerpt unavailable: {e})"
    card["other_matches"] = [{"id": x["id"], "qualname": x["qualname"], "file": x["file"], "line": x["start_line"]}
                             for x in found if x["id"] != s["id"]][:10]
    _out(card, card["definition_excerpt"], a.text)


def _range(spec: str):
    if "-" in spec:
        s, e = spec.split("-", 1)
        return int(s), int(e)
    return int(spec), int(spec)


def cmd_evidence(a):
    from .evidence import EvidenceError, excerpt, format_excerpt, register
    try:
        s, e = _range(a.lines)
        hl = []
        for part in (a.highlight or "").split(","):
            if part.strip():
                hs, he = _range(part.strip())
                hl.extend(range(hs, he + 1))
    except ValueError:
        _out({"error": f"invalid line range '{a.lines}' (expected N or START-END)"})
        sys.exit(2)
    try:
        ev = excerpt(a.repo, a.path, s, e, highlight=hl, context=a.context)
    except EvidenceError as ex:
        _out({"error": str(ex)})
        sys.exit(4)
    if a.register:
        store = _store(a.repo)
        fh = store.one("SELECT hash FROM files WHERE path=?", (a.path,))
        register(store, a.repo, ev, fh[0] if fh else None)
        store.commit()
    ev["formatted"] = format_excerpt(ev, a.symbol)
    _out(ev, ev["formatted"], a.text)


def cmd_callers(a):
    from .graph import callers
    store = _store(a.repo)
    s, _ = _one_symbol(store, a.target)
    _out({"symbol": {k: s[k] for k in ("id", "qualname", "file", "start_line")}, "callers": callers(store, s["id"])})


def cmd_callees(a):
    from .graph import callees
    store = _store(a.repo)
    s, _ = _one_symbol(store, a.target)
    _out({"symbol": {k: s[k] for k in ("id", "qualname", "file", "start_line")}, "callees": callees(store, s["id"])})


def cmd_deps(a):
    from .graph import importers_of, imports_of
    store = _store(a.repo)
    _out({"file": a.path, "imports": imports_of(store, a.path), "imported_by": importers_of(store, a.path)})


def cmd_routes(a):
    from .store import row_dict
    store = _store(a.repo)
    rows = [row_dict(r) for r in store.q("SELECT * FROM routes ORDER BY file, line")]
    for r in rows:
        r["handlers"] = json.loads(r["handlers"] or "[]")
        r["handler_ids"] = json.loads(r["handler_ids"] or "[]")
    _out({"routes": rows})


def cmd_tests_for(a):
    from .graph import find_symbols, tests_for
    store = _store(a.repo)
    if store.one("SELECT 1 FROM files WHERE path=?", (a.target,)):
        _out({"target": a.target, "tests": tests_for(store, a.repo, path=a.target)})
        return
    found = find_symbols(store, a.target)
    if not found:
        _out({"error": f"no symbol or file '{a.target}'"})
        sys.exit(3)
    _out({"target": found[0]["qualname"], "file": found[0]["file"], "tests": tests_for(store, a.repo, sid=found[0]["id"])})


def cmd_graph(a):
    from .graph import cycles, module_graph, orphans
    store = _store(a.repo)
    g = module_graph(store, a.depth, a.include_tests)
    g["cycles"] = cycles(store)
    g["orphans"] = orphans(store)[:100]
    _out(g)


def cmd_trace(a):
    from .flows import trace
    store = _store(a.repo)
    flow = trace(store, a.repo, a.target, depth=a.depth, title=a.title, save=not a.no_save)
    _out(flow, flow.get("text"), a.text)


def cmd_context(a):
    from .context import build_context
    store = _store(a.repo)
    ctx = build_context(store, a.repo, a.target, task=a.task, save=not a.no_save)
    _out(ctx, ctx.get("text"), a.text)


def cmd_changes(a):
    from .changes import analyze_changes
    store = _store(a.repo)
    res = analyze_changes(store, a.repo, since=a.since, save=not a.no_save, max_diff_lines=a.max_diff_lines)
    _out(res, res.get("text"), a.text)


def cmd_snapshots(a):
    from .snapshots import list_snapshots
    _out({"snapshots": list_snapshots(_store(a.repo))})


def cmd_tests(a):
    from . import testing
    store = _store(a.repo)
    if a.action == "detect":
        _out(testing.detect_runners(a.repo, store))
    elif a.action == "plan":
        if not a.args:
            _out({"error": "usage: ct tests plan <symbol|file>"})
            sys.exit(2)
        _out(testing.plan(store, a.repo, a.args[0]))
    elif a.action == "run":
        cmd = a.args[1:] if a.args and a.args[0] == "--" else a.args
        _out(testing.run(store, a.repo, cmd, approved=a.yes, timeout=a.timeout, label=a.label))
    elif a.action == "list":
        _out(testing.list_runs(a.repo))


def cmd_runtime(a):
    from .runtime import run_traced
    cmd = a.args[1:] if a.args and a.args[0] == "--" else a.args
    store = _store(a.repo)
    _out(run_traced(store, a.repo, cmd, approved=a.yes, lang=a.lang, timeout=a.timeout, label=a.label))


def cmd_explain(a):
    from . import explain
    store = _store(a.repo)
    if a.action == "add":
        _out(explain.add(store, a.repo, Path(a.file)))
    elif a.action == "validate":
        _out(explain.validate_file(a.repo, Path(a.file)))
    elif a.action == "list":
        _out(explain.list_items(a.repo))


def cmd_verify(a):
    from . import explain
    from .evidence import refresh_evidence_status, verify_citations
    store = _store(a.repo)
    out = {"evidence_refs": refresh_evidence_status(a.repo, store), "explanations": explain.verify_all(store, a.repo)}
    if a.file:
        text = sys.stdin.read() if a.file == "-" else Path(a.file).read_text(encoding="utf-8")
        cites = verify_citations(a.repo, text)
        out["citations"] = cites
        out["citation_problems"] = [c for c in cites if c["status"] != "ok"]
    _out(out)


def cmd_report(a):
    from .report import build_report
    store = _store(a.repo)
    _out(build_report(store, a.repo, lang=a.lang, out_dir=a.out))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ct", description="Codebase Tutor engine (deterministic repository intelligence).")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--no-refresh", action="store_true", help="skip the automatic incremental re-scan when the tree changed")
    p.add_argument("-C", "--repo", default=".", type=lambda s: Path(s).resolve(), help="target repository (default: cwd)")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help_):
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(fn=fn)
        return sp

    add("init", cmd_init, "create .codebase-tutor/")
    sp = add("scan", cmd_scan, "incremental scan (parse changed files, resolve, snapshot)")
    sp.add_argument("--full", action="store_true")
    sp.add_argument("--jobs", type=int, default=0)
    sp.add_argument("--quiet", action="store_true")
    sp.add_argument("--note")
    add("status", cmd_status, "knowledge base vs working tree")
    sp = add("overview", cmd_overview, "repository overview facts")
    sp.add_argument("--section", help="comma-separated keys")
    sp = add("search", cmd_search, "search symbols, files, routes")
    sp.add_argument("query")
    sp.add_argument("--limit", type=int, default=40)
    sp = add("symbol", cmd_symbol, "symbol card: definition, callers, callees, control points, tests")
    sp.add_argument("target")
    sp.add_argument("--max-lines", type=int, default=60)
    sp.add_argument("--text", action="store_true")
    sp = add("evidence", cmd_evidence, "exact excerpt with line numbers")
    sp.add_argument("path")
    sp.add_argument("lines", help="N or START-END")
    sp.add_argument("--highlight", help="e.g. 44,46-47")
    sp.add_argument("--context", type=int, default=0)
    sp.add_argument("--symbol")
    sp.add_argument("--register", action="store_true", help="store as evidence ref for staleness tracking")
    sp.add_argument("--text", action="store_true")
    for name, fn in (("callers", cmd_callers), ("callees", cmd_callees)):
        sp = add(name, fn, f"{name} of a symbol")
        sp.add_argument("target")
    sp = add("deps", cmd_deps, "imports and importers of a file")
    sp.add_argument("path")
    add("routes", cmd_routes, "detected HTTP routes / mounts / middleware")
    sp = add("tests-for", cmd_tests_for, "rank related tests for a symbol or file")
    sp.add_argument("target")
    sp = add("graph", cmd_graph, "module dependency graph, cycles, orphans")
    sp.add_argument("--depth", type=int, default=2)
    sp.add_argument("--include-tests", action="store_true")
    sp = add("trace", cmd_trace, "static execution flow from a symbol, file:line or 'METHOD /path'")
    sp.add_argument("target")
    sp.add_argument("--depth", type=int, default=4)
    sp.add_argument("--title")
    sp.add_argument("--no-save", action="store_true")
    sp.add_argument("--text", action="store_true")
    sp = add("context", cmd_context, "contribution context expansion + coverage table")
    sp.add_argument("target")
    sp.add_argument("--task")
    sp.add_argument("--no-save", action="store_true")
    sp.add_argument("--text", action="store_true")
    sp = add("changes", cmd_changes, "change intelligence vs snapshot or git ref")
    sp.add_argument("--since", default="last", help="last | <snapshot-id> | git:<ref>")
    sp.add_argument("--no-save", action="store_true")
    sp.add_argument("--max-diff-lines", type=int, default=400)
    sp.add_argument("--text", action="store_true")
    add("snapshots", cmd_snapshots, "list snapshots")
    sp = add("tests", cmd_tests, "detect | plan <target> | run --yes -- <cmd> | list")
    sp.add_argument("action", choices=["detect", "plan", "run", "list"])
    sp.add_argument("args", nargs=argparse.REMAINDER)
    sp.add_argument("--yes", action="store_true", help="user approved executing the command")
    sp.add_argument("--timeout", type=int, default=0)
    sp.add_argument("--label")
    sp = add("runtime", cmd_runtime, "run a command with runtime call tracing (experimental)")
    sp.add_argument("args", nargs=argparse.REMAINDER)
    sp.add_argument("--yes", action="store_true")
    sp.add_argument("--lang", choices=["auto", "python", "node"], default="auto")
    sp.add_argument("--timeout", type=int, default=0)
    sp.add_argument("--label")
    sp = add("explain", cmd_explain, "add | validate | list agent-authored explanations/flows")
    sp.add_argument("action", choices=["add", "validate", "list"])
    sp.add_argument("file", nargs="?")
    sp = add("verify", cmd_verify, "re-check evidence refs, explanations, and citations in a Markdown file")
    sp.add_argument("--file", help="Markdown file to check (`-` for stdin)")
    sp = add("report", cmd_report, "generate report.md + interactive index.html")
    sp.add_argument("--lang", default=None, help="en | hi | hinglish (default from config)")
    sp.add_argument("--out", default=None)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    # argparse REMAINDER swallows options placed after the action; recover the common ones.
    if getattr(args, "args", None):
        rest = []
        it = iter(args.args)
        for tok in it:
            if tok == "--":
                rest.append(tok)
                rest.extend(it)
                break
            if tok == "--yes":
                args.yes = True
            elif tok in ("--timeout", "--label", "--lang"):
                val = next(it, None)
                if val is None:
                    _out({"error": f"{tok} requires a value"})
                    return 2
                if tok == "--timeout":
                    try:
                        val = int(val)
                    except ValueError:
                        _out({"error": f"invalid --timeout value '{val}'"})
                        return 2
                setattr(args, tok[2:], val)
            else:
                rest.append(tok)
        args.args = rest
    if args.cmd in REFRESH_CMDS and not args.no_refresh:
        from .analyzer import ensure_fresh
        res = ensure_fresh(args.repo)
        if res and res["changes_since_last_scan"]["counts"] != {"added": 0, "modified": 0, "deleted": 0}:
            c = res["changes_since_last_scan"]["counts"]
            print(f"[ct] knowledge base refreshed: +{c['added']} ~{c['modified']} -{c['deleted']} files", file=sys.stderr)
    args.fn(args)
    return 0


REFRESH_CMDS = {"overview", "search", "symbol", "evidence", "callers", "callees", "deps", "routes", "tests-for", "graph",
                "trace", "context", "tests", "report", "verify", "explain"}
