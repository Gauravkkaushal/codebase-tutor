"""Change intelligence (Mode F): code diff, symbol/behaviour diff, architecture impact, risks."""
from __future__ import annotations

import difflib
import json
import re
import time
from collections import defaultdict

from .config import data_dir, load_config
from .context import reverse_reach, routes_reaching
from .graph import module_of, sym_row, tests_for
from .inventory import PARSEABLE_LANGS, classify, scan_inventory
from .parsers import parse_file
from .snapshots import git, git_ref_manifest, list_snapshots, load_manifest, ref_content

TEXT_ROLES = {"source", "test", "config", "doc", "asset", "data"}
DEP_MANIFESTS = ("package.json", "requirements.txt", "pyproject.toml", "setup.py", "Pipfile")


def _current_hashes(root, store) -> dict:
    prev = store.file_index()
    inv = scan_inventory(root, load_config(root), previous={p: (v[0], v[1], v[2]) for p, v in prev.items()})
    return {f.path: (f.hash, f.role, f.lang) for f in inv.files}


def pick_baseline(root, store, since: str, current: dict):
    if since.startswith("git:"):
        m = git_ref_manifest(root, since[4:])
        if m is None:
            raise ValueError(f"unknown git ref {since[4:]}")
        return m
    snaps = list_snapshots(store)
    if not snaps:
        raise ValueError("no snapshots yet; run `ct scan` first")
    if since != "last":
        return load_manifest(root, store, since)
    cur = {p: h for p, (h, role, _) in current.items() if role in TEXT_ROLES}
    for s in reversed(snaps):
        m = load_manifest(root, store, s["id"])
        old = {p: h for p, h in m["files"].items() if classify(p, 0)[1] in TEXT_ROLES}
        if old != cur:
            return m
    return load_manifest(root, store, snaps[0]["id"])


def _changed_files(root, baseline, current):
    if baseline.get("ref"):
        out = git(root, "diff", "--name-status", "-M", baseline["git"]["commit"]) or ""
        added, modified, deleted, renamed = [], [], [], []
        for ln in out.splitlines():
            parts = ln.split("\t")
            st = parts[0]
            if st.startswith("R") and len(parts) == 3:
                renamed.append([parts[1], parts[2]])
                modified.append(parts[2])
            elif st == "A":
                added.append(parts[1])
            elif st == "D":
                deleted.append(parts[1])
            elif len(parts) > 1:
                modified.append(parts[1])
        untracked = (git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines()
        added += [u for u in untracked if u in current and u not in added]
        return added, modified, deleted, renamed
    old = baseline["files"]
    added = sorted(p for p in current if p not in old and current[p][1] in TEXT_ROLES)
    deleted = sorted(p for p in old if p not in current and classify(p, 0)[1] in TEXT_ROLES)
    modified = sorted(p for p in current if p in old and old[p] != current[p][0] and current[p][1] in TEXT_ROLES)
    return added, modified, deleted, []


def _facts(path, lang, text):
    if text is None or lang not in PARSEABLE_LANGS:
        return None
    try:
        return parse_file(path, lang, text).to_dict()
    except Exception:
        return None


def _by_symbol(items, key="symbol"):
    d = defaultdict(set)
    for it in items:
        d[it.get(key) or it.get("caller")].add((it.get("kind", ""), it.get("text") or it.get("expr")))
    return d


def _norm(q: str | None) -> str | None:
    """Synthetic route-handler names embed a line number; ignore it when matching versions."""
    if q and q.startswith("handler:"):
        return re.sub(r"@\d+", "", q)
    return q


def symbol_diff(old_f, new_f) -> dict:
    for f in (old_f, new_f):
        for s in (f or {}).get("symbols", []):
            s["qualname_raw"], s["qualname"] = s["qualname"], _norm(s["qualname"])
        for c in (f or {}).get("controls", []):
            c["symbol"] = _norm(c["symbol"])
        for c in (f or {}).get("calls", []):
            c["caller"] = _norm(c["caller"])
    old_s = {s["qualname"]: s for s in (old_f or {}).get("symbols", [])}
    new_s = {s["qualname"]: s for s in (new_f or {}).get("symbols", [])}
    added = [new_s[q] for q in new_s if q not in old_s]
    removed = [old_s[q] for q in old_s if q not in new_s]
    modified, moved = [], []
    old_ctl = _by_symbol((old_f or {}).get("controls", []))
    new_ctl = _by_symbol((new_f or {}).get("controls", []))
    old_calls = defaultdict(set)
    new_calls = defaultdict(set)
    for c in (old_f or {}).get("calls", []):
        old_calls[c["caller"]].add(c["expr"])
    for c in (new_f or {}).get("calls", []):
        new_calls[c["caller"]].add(c["expr"])
    for q in new_s:
        if q in old_s:
            o, n = old_s[q], new_s[q]
            if o["body_hash"] != n["body_hash"]:
                sig_changed = o["signature"] != n["signature"]
                def _exits(ctl):
                    texts = sorted(t for k, t in ctl if k not in ("if", "else", "try"))
                    return [t for t in texts if not any(t != o and t in o for o in texts)]
                b = {
                    "conditions_added": sorted(t for k, t in new_ctl[q] - old_ctl[q] if k in ("if", "else")),
                    "conditions_removed": sorted(t for k, t in old_ctl[q] - new_ctl[q] if k in ("if", "else")),
                    "exits_added": _exits(new_ctl[q] - old_ctl[q]),
                    "exits_removed": _exits(old_ctl[q] - new_ctl[q]),
                    "calls_added": sorted(new_calls[q] - old_calls[q]),
                    "calls_removed": sorted(old_calls[q] - new_calls[q]),
                }
                codes_old = set(re.findall(r"\b[1-5]\d\d\b", " ".join(t for k, t in old_ctl[q] if k not in ("if", "else"))))
                codes_new = set(re.findall(r"\b[1-5]\d\d\b", " ".join(t for k, t in new_ctl[q] if k not in ("if", "else"))))
                if codes_old != codes_new:
                    b["status_codes"] = {"before": sorted(codes_old), "after": sorted(codes_new)}
                modified.append({"qualname": n.get("qualname_raw", q), "kind": n["kind"], "old_lines": [o["start"], o["end"]],
                                 "new_lines": [n["start"], n["end"]], "signature_changed": sig_changed,
                                 "old_signature": o["signature"], "new_signature": n["signature"],
                                 "exported": n["exported"] or o["exported"], "behaviour_signals": {k: v for k, v in b.items() if v}})
            elif o["start"] != n["start"]:
                moved.append({"qualname": q, "old_lines": [o["start"], o["end"]], "new_lines": [n["start"], n["end"]]})
    imp_old = {i["module"] for i in (old_f or {}).get("imports", [])}
    imp_new = {i["module"] for i in (new_f or {}).get("imports", [])}
    rkey = lambda r: f"{r['method']} {r['path']} -> {', '.join(h.split('@')[0] for h in r['handlers'])}"
    r_old = {rkey(r) for r in (old_f or {}).get("routes", [])}
    r_new = {rkey(r) for r in (new_f or {}).get("routes", [])}
    e_old = {e[1] for e in (old_f or {}).get("env_vars", [])}
    e_new = {e[1] for e in (new_f or {}).get("env_vars", [])}
    x_old = {e[0] for e in (old_f or {}).get("exports", [])}
    x_new = {e[0] for e in (new_f or {}).get("exports", [])}
    return {
        "symbols_added": [{"qualname": s.get("qualname_raw", s["qualname"]), "kind": s["kind"], "lines": [s["start"], s["end"]], "exported": s["exported"]} for s in added],
        "symbols_removed": [{"qualname": s.get("qualname_raw", s["qualname"]), "kind": s["kind"], "old_lines": [s["start"], s["end"]], "exported": s["exported"]} for s in removed],
        "symbols_modified": modified, "symbols_moved": moved,
        "imports_added": sorted(imp_new - imp_old), "imports_removed": sorted(imp_old - imp_new),
        "routes_added": sorted(r_new - r_old), "routes_removed": sorted(r_old - r_new),
        "env_vars_added": sorted(e_new - e_old), "env_vars_removed": sorted(e_old - e_new),
        "exports_added": sorted(x_new - x_old), "exports_removed": sorted(x_old - x_new),
    }


def _deps(path, text):
    if not text:
        return {}
    if path.endswith("package.json"):
        try:
            d = json.loads(text)
        except ValueError:
            return {}
        out = {}
        for sect in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            for k, v in (d.get(sect) or {}).items():
                out[k] = f"{v} ({sect})"
        return out
    out = {}
    for ln in text.splitlines():
        m = re.match(r'^\s*"?([A-Za-z0-9_.\-]+)\s*([<>=~!]=?[^";#]*)?', ln.split("#")[0])
        if m and m.group(1) and not ln.strip().startswith(("[", "-")):
            out[m.group(1).lower()] = (m.group(2) or "").strip()
    return out


def analyze_changes(store, root, since: str = "last", save: bool = True, max_diff_lines: int = 400) -> dict:
    from .analyzer import open_store, scan
    current = _current_hashes(root, store)
    known = store.file_index()
    stale_kb = any(p not in known or known[p][2] != h for p, (h, role, _) in current.items()) or any(p not in current for p in known)
    if stale_kb:
        store.close()
        scan(root, quiet=True, note="auto-scan before change analysis")
        store = open_store(root)
        current = _current_hashes(root, store)
    try:
        baseline = pick_baseline(root, store, since, current)
    except (ValueError, KeyError) as e:
        return {"error": str(e)}
    added, modified, deleted, renamed = _changed_files(root, baseline, current)
    files, diff_budget = [], max_diff_lines
    all_changed_syms, removed_names = [], []
    dep_changes = []
    for path in sorted(set(added) | set(modified) | set(deleted)):
        lang, role = classify(path, 0)
        if role not in TEXT_ROLES:
            continue
        status = "added" if path in added else "deleted" if path in deleted else "modified"
        old_text, src = (None, "absent") if status == "added" else ref_content(root, baseline, path)
        new_text = None
        if status != "deleted":
            try:
                new_text = (root / path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                new_text = None
        entry = {"path": path, "status": status, "role": role, "lang": lang, "baseline_source": src}
        if old_text is not None or new_text is not None:
            ud = list(difflib.unified_diff((old_text or "").splitlines(), (new_text or "").splitlines(),
                                           f"a/{path}", f"b/{path}", n=3, lineterm=""))
            entry["lines_added"] = sum(1 for x in ud if x.startswith("+") and not x.startswith("+++"))
            entry["lines_removed"] = sum(1 for x in ud if x.startswith("-") and not x.startswith("---"))
            if diff_budget > 0:
                entry["diff"] = ud[:diff_budget]
                entry["diff_truncated"] = len(ud) > diff_budget
                diff_budget -= len(entry["diff"])
            else:
                entry["diff"], entry["diff_truncated"] = [], True
        if src == "unavailable":
            entry["note"] = "baseline content unavailable (no blob and not in git); file-level change only"
        sd = symbol_diff(_facts(path, lang, old_text), _facts(path, lang, new_text)) if lang in PARSEABLE_LANGS else None
        if sd:
            entry["symbols"] = sd
            for m in sd["symbols_modified"]:
                all_changed_syms.append((path, m["qualname"], m))
            for a in sd["symbols_added"]:
                all_changed_syms.append((path, a["qualname"], None))
            removed_names += [(path, r["qualname"], r) for r in sd["symbols_removed"]]
        if path.endswith(DEP_MANIFESTS):
            od, nd = _deps(path, old_text), _deps(path, new_text)
            ch = {"added": {k: nd[k] for k in nd if k not in od}, "removed": {k: od[k] for k in od if k not in nd},
                  "changed": {k: [od[k], nd[k]] for k in nd if k in od and od[k] != nd[k]}}
            if any(ch.values()):
                dep_changes.append({"file": path, **ch})
        files.append(entry)

    # ---- impact over the current knowledge base
    impacted = {}
    focus_tests = defaultdict(lambda: {"score": 0, "for": set()})
    untested = []
    for path, qual, m in all_changed_syms:
        row = store.one("SELECT id FROM symbols WHERE file=? AND qualname=?", (path, qual))
        if not row:
            continue
        reach = reverse_reach(store, row["id"], 3)
        for sid, d in reach.items():
            if d == 0:
                continue
            if sid not in impacted or impacted[sid]["distance"] > d:
                s = sym_row(store, sid)
                impacted[sid] = {"qualname": s["qualname"], "file": s["file"], "line": s["start_line"], "distance": d,
                                 "because_of": qual}
        if m is not None:
            ts = tests_for(store, root, sid=row["id"], limit=6)
            if not ts:
                untested.append(qual)
            for t in ts:
                focus_tests[t["test_file"]]["score"] += t["score"]
                focus_tests[t["test_file"]]["for"].add(qual)
        m_routes = routes_reaching(store, reach)
        if m is not None:
            m["routes_reaching"] = m_routes[:15]
    broken_refs = []
    for path, qual, r in removed_names:
        name = qual.split(".")[-1]
        for c in store.q("SELECT file, line, expr, resolution FROM calls WHERE name=? AND resolution IN ('unresolved','structurally-inferred')", (name,)):
            imports_changed = store.one("SELECT 1 FROM imports WHERE file=? AND resolved=?", (c["file"], path))
            if imports_changed or c["file"] == path:
                broken_refs.append({"removed": qual, "file": c["file"], "line": c["line"], "expr": c["expr"],
                                    "verification": "structurally-inferred"})
    changed_tests = [f["path"] for f in files if f["role"] == "test"]
    risks = []
    for f in files:
        for m in (f.get("symbols") or {}).get("symbols_modified", []):
            callers_n = sum(1 for v in impacted.values() if v["because_of"] == m["qualname"] and v["distance"] == 1)
            if m["signature_changed"] and m["exported"]:
                risks.append({"level": "high" if callers_n else "medium", "kind": "contract-change",
                              "detail": f"Signature of exported {m['qualname']} changed ({m['old_signature']} → {m['new_signature']}); {callers_n} direct caller(s) found",
                              "file": f["path"], "line": m["new_lines"][0]})
            bs = m["behaviour_signals"]
            if (bs.get("conditions_added") or bs.get("conditions_removed") or bs.get("exits_added") or bs.get("exits_removed")) and not changed_tests:
                risks.append({"level": "medium", "kind": "behaviour-change-without-test-change",
                              "detail": f"Control flow of {m['qualname']} changed but no test file changed", "file": f["path"], "line": m["new_lines"][0]})
            if re.search(r"(auth|login|passw|token|session|permission|role|admin|csrf)", m["qualname"] + f["path"], re.I):
                risks.append({"level": "high", "kind": "security-sensitive", "detail": f"{m['qualname']} looks security-related; review conditions and error paths",
                              "file": f["path"], "line": m["new_lines"][0]})
        for r in (f.get("symbols") or {}).get("symbols_removed", []):
            if r["exported"]:
                risks.append({"level": "high", "kind": "removed-export", "detail": f"Exported {r['qualname']} removed", "file": f["path"], "line": r["old_lines"][0]})
        sd = f.get("symbols") or {}
        if sd.get("routes_removed") or sd.get("routes_added"):
            risks.append({"level": "medium", "kind": "route-change", "detail": f"Routes changed: +{sd.get('routes_added')} -{sd.get('routes_removed')}", "file": f["path"], "line": None})
        if sd.get("env_vars_added"):
            risks.append({"level": "low", "kind": "new-config", "detail": f"New env vars read: {sd['env_vars_added']} (deployments must provide them)", "file": f["path"], "line": None})
    for q in untested:
        risks.append({"level": "medium", "kind": "missing-tests", "detail": f"No related tests found for {q}", "file": None, "line": None})
    if dep_changes:
        risks.append({"level": "medium", "kind": "dependency-change", "detail": f"{len(dep_changes)} manifest(s) changed dependencies", "file": None, "line": None})
    unresolved_same_name = 0
    for path, qual, _ in all_changed_syms + [(p, q, None) for p, q, _r in removed_names]:
        unresolved_same_name += store.one("SELECT COUNT(*) FROM calls WHERE name=? AND resolution='unresolved'", (qual.split(".")[-1],))[0]
    modules = sorted({module_of(v["file"]) for v in impacted.values()})
    result = {
        "baseline": {"id": baseline.get("id"), "git_commit": (baseline.get("git") or {}).get("commit"), "kind": "git-ref" if baseline.get("ref") else "snapshot"},
        "current_snapshot": store.get_meta("last_snapshot"),
        "generated_at": time.time(),
        "summary": {"files_added": len([f for f in files if f["status"] == "added"]),
                    "files_modified": len([f for f in files if f["status"] == "modified"]),
                    "files_deleted": len([f for f in files if f["status"] == "deleted"]),
                    "renamed": renamed,
                    "symbols_modified": sum(len((f.get("symbols") or {}).get("symbols_modified", [])) for f in files),
                    "symbols_added": sum(len((f.get("symbols") or {}).get("symbols_added", [])) for f in files),
                    "symbols_removed": sum(len((f.get("symbols") or {}).get("symbols_removed", [])) for f in files),
                    "impacted_symbols": len(impacted), "impacted_modules": modules},
        "files": files,
        "dependency_changes": dep_changes,
        "impact": {"callers": sorted(impacted.values(), key=lambda x: (x["distance"], x["file"]))[:200],
                   "possibly_broken_references": broken_refs[:100],
                   "tests_to_run": sorted(({"test_file": k, "score": v["score"], "covers": sorted(v["for"])} for k, v in focus_tests.items()),
                                          key=lambda x: -x["score"])[:30],
                   "tests_changed": changed_tests,
                   "completeness": {"unresolved_calls_with_changed_names": unresolved_same_name,
                                    "note": "Impact uses resolved call edges only; dynamic dispatch and unresolved calls may hide more callers."
                                    if unresolved_same_name else "No unresolved calls share names with changed symbols."}},
        "risks": sorted(risks, key=lambda r: {"high": 0, "medium": 1, "low": 2}[r["level"]]),
        "verification": "Static comparison of source (not execution). Run tests to verify behaviour.",
    }
    result["text"] = render(result)
    if save:
        d = data_dir(root) / "knowledge" / "changes"
        stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        body = json.dumps({k: v for k, v in result.items() if k != "text"}, indent=1, ensure_ascii=False, default=str)
        (d / f"{stamp}.json").write_text(body, encoding="utf-8")
        (d / "latest.json").write_text(body, encoding="utf-8")
        result["saved_to"] = str((d / f"{stamp}.json").relative_to(root))
    return result


def render(r: dict) -> str:
    s = r["summary"]
    out = [f"Changes vs {r['baseline']['kind']} {r['baseline']['id']}: +{s['files_added']} ~{s['files_modified']} -{s['files_deleted']} files; "
           f"symbols ~{s['symbols_modified']} +{s['symbols_added']} -{s['symbols_removed']}; impacted {s['impacted_symbols']} symbol(s)"]
    for f in r["files"]:
        out.append(f"\n## {f['status'].upper()} {f['path']} (+{f.get('lines_added', 0)}/-{f.get('lines_removed', 0)})")
        sd = f.get("symbols") or {}
        for m in sd.get("symbols_modified", []):
            out.append(f"  ~ {m['qualname']} lines {m['old_lines']} → {m['new_lines']}" + (" [signature changed]" if m["signature_changed"] else ""))
            for k, v in m["behaviour_signals"].items():
                out.append(f"      {k}: {v}")
        for a in sd.get("symbols_added", []):
            out.append(f"  + {a['qualname']} {a['lines']}")
        for d in sd.get("symbols_removed", []):
            out.append(f"  - {d['qualname']} (was {d['old_lines']})")
    if r["impact"]["callers"]:
        out.append("\nImpacted callers:")
        for c in r["impact"]["callers"][:15]:
            out.append(f"  d{c['distance']} {c['qualname']} — {c['file']}:{c['line']} (via {c['because_of']})")
    if r["impact"]["tests_to_run"]:
        out.append("\nTests to run: " + ", ".join(t["test_file"] for t in r["impact"]["tests_to_run"][:10]))
    if r["risks"]:
        out.append("\nRisks:")
        out += [f"  [{x['level']}] {x['kind']}: {x['detail']}" for x in r["risks"][:20]]
    out.append("\n" + r["impact"]["completeness"]["note"])
    return "\n".join(out)
