"""Report generation: report.md (selected language) + standalone interactive HTML (all languages embedded)."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import __version__
from .config import data_dir, load_config
from .evidence import EvidenceError, read_lines, redact_line
from .explain import evidence_status, load_all
from .dataflow import classify_external, system_map
from .graph import cycles, file_graph, layer_hint, module_graph, module_of
from .overview import overview
from .runtime import list_traces
from .testing import list_runs

SKILL_ROOT = Path(__file__).resolve().parents[2]
ASSETS = SKILL_ROOT / "assets" / "report"
I18N_DIR = Path(__file__).resolve().parent / "i18n"
LANGS = ("en", "hi", "hinglish")


def load_i18n() -> dict:
    out = {}
    for code in LANGS:
        p = I18N_DIR / f"{code}.json"
        if p.exists():
            out[code] = json.loads(p.read_text(encoding="utf-8"))
    for p in sorted(I18N_DIR.glob("*.json")):
        if p.stem not in out:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    return out


def _json_files(d: Path) -> list:
    out = []
    for p in sorted(d.glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def _collect_refs(obj, acc: set):
    if isinstance(obj, dict):
        f = obj.get("file") or obj.get("path") or obj.get("test_file")
        if isinstance(f, str) and "/" in f or (isinstance(f, str) and "." in f):
            acc.add(f)
        for v in obj.values():
            _collect_refs(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_refs(v, acc)


def build_data(store, root: Path, lang: str) -> dict:
    root = Path(root)
    cfg = load_config(root)
    ov = overview(store, root)
    flows = _json_files(data_dir(root) / "knowledge" / "flows")
    contexts = _json_files(data_dir(root) / "knowledge" / "contexts")
    explanations = load_all(root)
    for d in explanations:
        d["evidence_summary"] = evidence_status(root, d)
    # flow staleness: compare stored per-step line hashes with current source
    for fl in flows:
        stale = 0
        for st in fl.get("steps", []):
            if st.get("file") and st.get("line") and st.get("text_hash"):
                try:
                    lines = read_lines(root, st["file"])
                    from .evidence import text_hash
                    cur = text_hash(lines[st["line"] - 1:st["line"]]) if st["line"] <= len(lines) else None
                except EvidenceError:
                    cur = None
                st["stale"] = cur != st["text_hash"]
                stale += st["stale"]
        fl["stale_steps"] = stale
        for st in fl.get("steps", []):
            if st.get("kind") == "external-call" and st.get("module"):
                cls = classify_external(st["module"])
                if cls:
                    st["storage_kind"], st["storage"] = cls
    changes_path = data_dir(root) / "knowledge" / "changes" / "latest.json"
    changes = json.loads(changes_path.read_text(encoding="utf-8")) if changes_path.exists() else None
    runs = []
    for r in list_runs(root)["runs"]:
        p = data_dir(root) / "runs" / "tests" / r["id"] / "result.json"
        try:
            full = json.loads(p.read_text(encoding="utf-8"))
            r["tests"] = full.get("tests", [])[:1500]
            r["executed_command"] = full.get("executed_command")
            r["started_at"] = full.get("started_at")
            r["verification"] = full.get("verification")
        except (OSError, ValueError):
            pass
        runs.append(r)
    traces = []
    for t in list_traces(root)[-5:]:
        t["sequence"] = t.get("sequence", [])[:2500]
        traces.append(t)

    # graph data
    mg = module_graph(store, depth=2)
    fg = file_graph(store)
    roles = {r["path"]: (r["role"], r["lang"], r["lines"] or 0, r["status"]) for r in store.q("SELECT path, role, lang, lines, status FROM files")}
    sym_count = {r[0]: r[1] for r in store.q("SELECT file, COUNT(*) FROM symbols GROUP BY file")}
    max_nodes = int(cfg["report"].get("max_graph_nodes", 400))
    file_nodes = [{"id": p, "module": module_of(p), "lang": v[1], "lines": v[2], "symbols": sym_count.get(p, 0),
                   "layer": layer_hint(p)} for p, v in roles.items() if v[0] == "source" and v[1] in ("python", "javascript", "typescript", "tsx")]
    for n in mg["nodes"]:
        n["layer"] = layer_hint(n["id"] + "/")
    max_syms = int(cfg["report"].get("max_symbols_indexed", 30000))
    symbols = [[r["id"], r["name"], r["qualname"], r["kind"], r["file"], r["start_line"], r["end_line"], r["exported"]]
               for r in store.q("SELECT s.id, s.name, s.qualname, s.kind, s.file, s.start_line, s.end_line, s.exported FROM symbols s "
                                "JOIN files f ON f.path=s.file ORDER BY f.role='test', s.file, s.start_line LIMIT ?", (max_syms,))]
    # call edges for symbol panel (resolved only)
    sym_edges = [[r["caller_id"], r["resolved_id"], r["resolution"], r["file"], r["line"]] for r in store.q(
        "SELECT s.id AS caller_id, c.resolved_id, c.resolution, c.file, c.line FROM calls c "
        "JOIN symbols s ON s.file=c.file AND s.qualname=c.caller WHERE c.resolved_id IS NOT NULL LIMIT 60000")]
    imports = [[r["file"], r["resolved"], r["line"]] for r in store.q("SELECT file, resolved, line FROM imports WHERE resolved IS NOT NULL")]

    # embed sources
    refs = set()
    for obj in (flows, contexts, explanations, changes, ov["entry_points"], ov["hubs"], ov["routes"], runs):
        _collect_refs(obj, refs)
    budget = int(cfg["report"].get("embed_source_budget_kb", 6000)) * 1024
    ordered = [p for p in refs if p in roles] + sorted(
        (p for p, v in roles.items() if v[0] in ("source", "test") and p not in refs),
        key=lambda p: (roles[p][0] == "test", -sym_count.get(p, 0)))
    sources, used = {}, 0
    for p in ordered:
        if roles[p][3] in ("secret", "binary", "skipped-large"):
            continue
        try:
            lines = read_lines(root, p)
        except EvidenceError:
            continue
        size = sum(len(x) + 1 for x in lines)
        if used + size > budget:
            continue
        sources[p] = [redact_line(x)[0] for x in lines]
        used += size
    files = [{"path": p, "role": v[0], "lang": v[1], "lines": v[2], "status": v[3], "embedded": p in sources,
              "module": module_of(p), "layer": layer_hint(p)} for p, v in sorted(roles.items())]
    gi = ov["git"]
    meta = {"repo_name": root.name, "repo": str(root), "commit": gi.get("commit"), "branch": gi.get("branch"),
            "dirty": gi.get("dirty"), "generated_at": time.time(), "snapshot": store.get_meta("last_snapshot"),
            "tool_version": __version__, "default_lang": lang, "languages": list(load_i18n().keys()),
            "embedded_source_kb": round(used / 1024), "embedded_files": len(sources)}
    ov.pop("git", None)
    return {"meta": meta, "i18n": load_i18n(), "overview": ov,
            "graph": {"modules": mg, "file_nodes": file_nodes, "file_edges": fg["edges"], "cycles": cycles(store)},
            "system_map": _jsonable(system_map(store, root=root)),
            "symbols": symbols, "symbol_edges": sym_edges, "imports": imports, "files": files, "sources": sources,
            "flows": flows, "explanations": explanations, "contexts": contexts, "changes": changes,
            "test_runs": runs, "runtime": traces}


def _jsonable(obj):
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    return obj


def build_report(store, root: Path, lang: str | None = None, out_dir: str | None = None) -> dict:
    root = Path(root)
    lang = lang or load_config(root).get("language", "en")
    i18n = load_i18n()
    if lang not in i18n:
        return {"error": f"unknown language '{lang}'", "available": sorted(i18n)}
    out = Path(out_dir).resolve() if out_dir else data_dir(root) / "reports"
    out.mkdir(parents=True, exist_ok=True)
    data = build_data(store, root, lang)
    (out / "vendor").mkdir(exist_ok=True)
    for name in ("index.html", "app.js", "viz.js", "styles.css"):
        shutil.copyfile(ASSETS / name, out / name)
    for p in (ASSETS / "vendor").iterdir():
        shutil.copyfile(p, out / "vendor" / p.name)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str).replace("</", "<\\/")
    (out / "data.js").write_text("window.CT_DATA=" + payload + ";\n", encoding="utf-8")
    md = render_markdown(data, lang)
    (out / "report.md").write_text(md, encoding="utf-8")
    return {"report_dir": str(out), "index_html": str(out / "index.html"), "report_md": str(out / "report.md"),
            "data_kb": round((out / "data.js").stat().st_size / 1024), "embedded_files": data["meta"]["embedded_files"],
            "flows": len(data["flows"]), "explanations": len(data["explanations"]), "test_runs": len(data["test_runs"]),
            "runtime_traces": len(data["runtime"]), "language": lang}


# ---------------------------------------------------------------- Markdown
def _t(i18n, code, key, **kw):
    s = i18n.get(code, {}).get(key) or i18n["en"].get(key) or key
    try:
        return s.format(**kw)
    except (KeyError, IndexError, ValueError):
        return s


def _loc(obj, lang):
    if isinstance(obj, dict):
        return obj.get(lang) or obj.get("en") or next(iter(obj.values()), "")
    return obj or ""


def _cite(f, line=None, end=None):
    if not f:
        return ""
    if line and end and end != line:
        return f"`{f}:{line}-{end}`"
    return f"`{f}:{line}`" if line else f"`{f}`"


def render_markdown(data: dict, lang: str) -> str:
    i18n, ov, meta = data["i18n"], data["overview"], data["meta"]
    T = lambda k, **kw: _t(i18n, lang, k, **kw)  # noqa: E731
    L = []
    L.append(f"# {T('report_title')}: {meta['repo_name']}")
    L.append("")
    L.append(f"{T('generated')}: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(meta['generated_at']))} · "
             f"{T('commit')}: `{(meta['commit'] or 'n/a')[:12]}`" + (f" ({T('dirty_tree')})" if meta.get("dirty") else "") +
             f" · {T('snapshot')}: `{meta['snapshot']}`")
    L.append("")
    L.append(f"> {T('legend_intro')}")
    for lv in ("verified-source", "structurally-inferred", "test-verified", "runtime-observed", "not-verified"):
        L.append(f"> - **{T('v_' + lv)}** — {T('v_' + lv + '_desc')}")
    L.append("")
    # Overview
    L.append(f"## 1. {T('nav_overview')}")
    proj = ov.get("project") or {}
    if proj.get("description"):
        L.append(f"**{T('project_purpose')}:** {proj['description']} ({T('source')}: {_cite(proj.get('file'), proj.get('line'))})")
    langs = ov.get("languages", [])
    if langs:
        top = langs[0]
        L.append(T("md_lang_summary", lang=top["lang"], share=round(top["share"] * 100), files=top["files"], lines=top["lines"]))
    L.append("")
    stack_rows = []
    for key in ("frameworks", "databases", "auth", "security", "external_services", "queues", "test_frameworks", "build",
                "package_managers", "ci", "containers"):
        for it in ov.get(key) or []:
            stack_rows.append(f"| {T('cat_' + key)} | {it['name']} | {_cite(it['file'], it.get('line'))} |")
    if stack_rows:
        L += [f"| {T('category')} | {T('technology')} | {T('evidence')} |", "|---|---|---|", *stack_rows, ""]
    if ov.get("monorepo"):
        L.append(f"**{T('monorepo')}:** {ov['monorepo']['type']} — {len(ov['monorepo'].get('packages', []))} {T('packages')}")
    L.append(f"### {T('structure')}")
    L += [f"| {T('folder')} | {T('files')} | {T('lines')} | {T('layer_hint')} |", "|---|---:|---:|---|"]
    for s in ov.get("structure", [])[:25]:
        L.append(f"| `{s['path']}` | {s['files']} | {s['lines']} | {s.get('layer_hint') or '—'} |")
    L.append("")
    L.append(f"### {T('entry_points')}")
    for e in ov.get("entry_points", [])[:15]:
        ev = e.get("evidence") or {}
        L.append(f"- {_cite(e.get('file')) if e.get('file') else ''} {e['reason']} — {T('evidence')}: {_cite(ev.get('file'), ev.get('line'))}")
    if not ov.get("entry_points"):
        L.append(f"- {T('none_found')}")
    L.append("")
    L.append(f"### {T('hubs')}")
    for h in ov.get("hubs", [])[:10]:
        L.append(f"- {_cite(h['file'])} — {T('imported_by_n', n=h['imported_by_files'])}, {T('incoming_calls_n', n=h['incoming_calls'])}")
    L.append("")
    sm = data.get("system_map") or {}
    stores = [n for n in sm.get("nodes", []) if n["kind"] == "storage"]
    if stores:
        L.append(f"### {T('df_storages')}")
        for n in stores:
            ins = [e for e in sm["edges"] if e["target"] == n["id"]]
            ev = next((x for e in ins for x in e.get("evidence", [])), None)
            users = ", ".join(f"`{e['source']}`" for e in ins[:6])
            L.append(f"- **{n['label']}** ({', '.join('`' + p + '`' for p in n.get('packages', [])[:4])}) ← {users}"
                     + (f" — {T('evidence')}: {_cite(ev['file'], ev['line'])}" if ev else ""))
        L.append("")
    routes = [r for r in ov.get("routes", []) if r["kind"] == "route"]
    if routes:
        L.append(f"### {T('routes')} ({len(routes)})")
        for r in routes[:40]:
            L.append(f"- `{r['method']} {r['full_path'] or r['path']}` — {_cite(r['file'], r['line'])}")
        L.append("")
    if ov.get("env_var_names"):
        L.append(f"### {T('env_vars')}")
        L.append(T("env_vars_note"))
        for e in ov["env_var_names"][:40]:
            L.append(f"- `{e['name']}` — " + ", ".join(_cite(r["file"], r["line"]) for r in e["refs"][:3]))
        L.append("")
    L.append(f"### {T('learning_path')}")
    for i, s in enumerate(ov.get("learning_path", []), 1):
        L.append(f"{i}. `{s['target']}` — {s['why']}")
    L.append("")
    # Explanations
    exps = [e for e in data["explanations"] if e.get("type") != "flow-notes"]
    if exps:
        L.append(f"## 2. {T('nav_learn')}")
        for e in exps:
            L.append(f"### {_loc(e.get('title'), lang)}" + (f" · _{T('level_' + e['level'])}_" if e.get("level") else ""))
            if lang not in (e.get("languages") or []) and lang != "en":
                L.append(f"_{T('translation_missing')}_")
            if e.get("summary"):
                L.append(_loc(e["summary"], lang))
            for sec in e.get("sections", []):
                if sec.get("heading"):
                    L.append(f"#### {_loc(sec['heading'], lang)}")
                L.append(_loc(sec.get("body"), lang))
                for ev in sec.get("evidence", []):
                    st = ev.get("current_status", "valid")
                    flag = "" if st == "valid" else f" ⚠ {T('ev_' + st)}"
                    L.append(f"- {T('evidence')}: {_cite(ev['file'])}:{ev['lines']}" + (f" ({ev['symbol']})" if ev.get("symbol") else "") + flag)
                    try:
                        s, _, en = ev["lines"].partition("-")
                        s, en = int(s), int(en or s)
                        src = data["sources"].get(ev["file"])
                        if src and en - s < 30:
                            hl = set()
                            for part in str(ev.get("highlight", "")).split(","):
                                if part.strip():
                                    a, _, b = part.strip().partition("-")
                                    hl.update(range(int(a), int(b or a) + 1))
                            L.append("```")
                            for n in range(s, en + 1):
                                L.append(f"{'▶' if n in hl else ' '} {n:>4}  {src[n - 1]}")
                            L.append("```")
                    except (ValueError, IndexError):
                        pass
            for c in e.get("checkpoints", []):
                L.append(f"- **{T('checkpoint')}:** {_loc(c.get('question'), lang)}")
            L.append("")
    # Flows
    if data["flows"]:
        L.append(f"## 3. {T('nav_flows')}")
        for fl in data["flows"]:
            L.append(f"### {fl['title']} — _{T('v_' + fl.get('verification', 'structurally-inferred'))}_")
            L.append(f"_{T('flow_static_note')}_")
            for st in fl["steps"][:120]:
                mark = {"failure": "✗", "success": "✓"}.get(st.get("outcome"), "·")
                ver = "" if st["verification"] == "verified-source" else f" _[{T('v_' + st['verification']) if st['verification'] != 'unresolved' else T('unresolved')}]_"
                stale = f" ⚠ {T('ev_stale')}" if st.get("stale") else ""
                L.append(f"{'  ' * st.get('depth', 0)}{st['n']}. {mark} {st['text']} — {_cite(st['file'], st['line'])}{ver}{stale}")
            if fl.get("unresolved_steps"):
                L.append(f"\n{T('flow_unresolved_note', n=fl['unresolved_steps'])}")
            L.append("")
    # Contributions
    if data["contexts"]:
        L.append(f"## 4. {T('nav_contribute')}")
        for c in data["contexts"]:
            L.append(f"### {c['target']}" + (f" — {c['task']}" if c.get("task") else ""))
            L += [f"| {T('area')} | {T('status')} | {T('basis')} |", "|---|---|---|"]
            for row in c["coverage"]:
                L.append(f"| {row['area']} | {row['status']} | {row['basis']} |")
            for t in c.get("tests", [])[:6]:
                L.append(f"- {T('test')}: {_cite(t['test_file'])} ({'; '.join(t['signals'][:2])})")
            L.append("")
    # Changes
    ch = data.get("changes")
    if ch:
        s = ch["summary"]
        L.append(f"## 5. {T('nav_changes')}")
        L.append(T("changes_summary", added=s["files_added"], modified=s["files_modified"], deleted=s["files_deleted"],
                   syms=s["symbols_modified"], impacted=s["impacted_symbols"], baseline=ch["baseline"]["id"]))
        for f in ch["files"][:30]:
            L.append(f"#### {f['status']} `{f['path']}` (+{f.get('lines_added', 0)} / -{f.get('lines_removed', 0)})")
            for m in (f.get("symbols") or {}).get("symbols_modified", []):
                L.append(f"- `{m['qualname']}` {m['old_lines']} → {m['new_lines']}" + (f" — {T('signature_changed')}" if m["signature_changed"] else ""))
                for k, v in m["behaviour_signals"].items():
                    L.append(f"  - {T('bs_' + k)}: {', '.join('`' + str(x) + '`' for x in (v if isinstance(v, list) else [v]))}")
            if f.get("diff"):
                L.append("```diff")
                L += f["diff"][:80]
                L.append("```")
        if ch["risks"]:
            L.append(f"#### {T('risks')}")
            for r in ch["risks"][:20]:
                L.append(f"- **{T('risk_' + r['level'])}** {r['kind']}: {r['detail']}")
        L.append(f"\n{ch['impact']['completeness']['note']}")
        L.append("")
    # Tests / runtime
    if data["test_runs"] or data["runtime"]:
        L.append(f"## 6. {T('nav_simulation')}")
        for r in data["test_runs"][-10:]:
            c = r.get("counts") or {}
            L.append(f"- {T('test_run')} `{r['command']}` → **{r['status']}** ({c.get('passed', 0)} {T('passed')}, {c.get('failed', 0)} {T('failed')}, "
                     f"{c.get('skipped', 0)} {T('skipped')}) — {T('v_test-verified')}, {T('commit')} `{(r.get('git_commit') or '')[:10]}`" +
                     (f" ({T('dirty_tree')})" if r.get("dirty") else ""))
        for t in data["runtime"]:
            L.append(f"- {T('runtime_trace')} `{t['command']}` → {t['events_total']} {T('events')}, {t['functions_observed']} {T('functions')} — {T('v_runtime-observed')}")
            for m in t.get("mapped_symbols", [])[:10]:
                L.append(f"  - `{m['qualname']}` × {m['calls']}" + (f" ({m['throws']} {T('throws')})" if m.get("throws") else "") + f" — {_cite(m['file'], m['line'])}")
        L.append("")
    # Coverage & limitations
    L.append(f"## 7. {T('coverage')}")
    cov = ov["coverage"]
    L += [f"| {T('language')} | {T('files')} | {T('lines')} | {T('analyzed')} | {T('partial')} | {T('inventory_only')} | {T('failed')} |",
          "|---|---:|---:|---:|---:|---:|---:|"]
    for lg in ov["languages"]:
        L.append(f"| {lg['lang']} | {lg['files']} | {lg['lines']} | {lg['analyzed']} | {lg['partial']} | {lg['inventory_only']} | {lg['failed']} |")
    L.append("")
    L.append(T("calls_resolution", total=cov["calls_total"], unresolved=cov["calls_unresolved"]))
    if cov.get("excluded_dir_count"):
        L.append(T("excluded_dirs", n=cov["excluded_dir_count"]) + ": " + ", ".join(f"`{d}`" for d in list(cov["excluded_dirs"])[:15]))
    L.append("")
    L.append(f"_{T('limitations_static')}_")
    L.append("")
    return "\n".join(L)
