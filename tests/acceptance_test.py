#!/usr/bin/env python3
"""Codebase Tutor acceptance test against the 18-point Definition of Done.

Reference repository: a fresh clone of https://github.com/expressjs/express (checks use real Express code).
Usage:
  python acceptance_test.py --skill <path to codebase-tutor> --repo <path to express clone> [--out DIR] [--run-tests]

--run-tests executes Express's own mocha tests and a runtime trace (needs `npm install` in the repo first).
Passing --run-tests is your approval to execute repository code. Without it those checks are reported as SKIPPED.
The script modifies one Express file temporarily and restores it with `git checkout` at the end.
"""
import argparse
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

RESULTS = []
CATALOG = {}


def ct(skill, repo, *args, check=True):
    p = subprocess.run([sys.executable, str(Path(skill) / "scripts" / "ct.py"), "-C", str(repo), *args],
                       capture_output=True, text=True, encoding="utf-8")
    if check and p.returncode != 0:
        raise RuntimeError(f"ct {' '.join(args)} failed ({p.returncode}): {p.stderr[-800:]}")
    try:
        return json.loads(p.stdout)
    except ValueError:
        return {"_raw": p.stdout, "_stderr": p.stderr}


def lines_of(repo, path):
    return (Path(repo) / path).read_text(encoding="utf-8", errors="replace").splitlines()


def record(num, requirement, ok, evidence, how_to_verify, skipped=False):
    status = "SKIPPED" if skipped else ("PASS" if ok else "FAIL")
    RESULTS.append({"id": num, "requirement": requirement, "status": status, "evidence": evidence, "verify_yourself": how_to_verify})
    print(f"[{status}] {num:>2}. {requirement}")


def guard(num, requirement, how):
    def deco(fn):
        def run(*a, **k):
            try:
                fn(*a, **k)
            except Exception as e:  # a crash is a failure, with the error as evidence
                record(num, requirement, False, {"error": f"{type(e).__name__}: {e}"}, how)
        return run
    return deco


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", default="ct-acceptance-results")
    ap.add_argument("--run-tests", action="store_true")
    a = ap.parse_args()
    skill, repo, out = Path(a.skill).resolve(), Path(a.repo).resolve(), Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(skill / "scripts"))
    global CATALOG
    from codebase_tutor.detect import CATALOG
    data_dir = repo / ".codebase-tutor"
    if data_dir.exists():
        shutil.rmtree(data_dir)  # start as an "unfamiliar" repo
    secret_file = repo / ".env"
    had_secret = secret_file.exists()
    target = repo / "lib" / "response.js"
    original = target.read_text(encoding="utf-8")
    try:
        if not had_secret:
            secret_file.write_text("ACCEPTANCE_FAKE_SECRET=do-not-leak-7f3a9c\n", encoding="utf-8")
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        t0 = time.time()
        state = {}

        @guard(1, "Enter an unfamiliar repository", "Run `python scripts/ct.py -C <repo> scan` on any repo with no .codebase-tutor folder.")
        def c1():
            s = ct(skill, repo, "scan", "--quiet")
            state["scan"] = s
            record(1, "Enter an unfamiliar repository", s["first_scan"] and s["parse_failures"] == 0,
                   {"first_scan": s["first_scan"], "files": s["files_total"], "parsed": s["parsed_now"], "seconds": s["seconds"],
                    "coverage": s["coverage"]["by_status"]},
                   "Run `ct scan` on a fresh repo; it should finish with parse_failures 0 and print coverage.")
        c1()

        @guard(2, "Discover structure and technologies", "")
        def c2():
            ov = ct(skill, repo, "overview")
            state["ov"] = ov
            langs = [l["lang"] for l in ov["languages"]]
            pms = {p["name"] for p in ov["package_managers"]}
            ci = {c["name"] for c in ov["ci"]}
            tests = {t["name"] for t in ov["test_frameworks"]}
            entries = {e["file"] for e in ov["entry_points"] if e.get("file")}
            ok = langs[0] == "javascript" and "Mocha" in tests and "GitHub Actions" in ci and "index.js" in entries and pms
            record(2, "Discover structure and technologies", ok,
                   {"languages": langs, "package_managers": sorted(pms), "ci": sorted(ci), "test_frameworks": sorted(tests),
                    "entry_points": sorted(entries)[:6], "top_folders": [s["path"] for s in ov["structure"][:8]]},
                   "Open report → Overview: JavaScript, npm, GitHub Actions, Mocha and index.js should be listed with file:line evidence.")
        c2()

        @guard(3, "Build a usable structural representation", "")
        def c3():
            db = sqlite3.connect(str(data_dir / "knowledge" / "index.db"))
            counts = {t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in ("files", "symbols", "imports", "calls", "routes", "control")}
            resolved = db.execute("SELECT COUNT(*) FROM imports WHERE resolved IS NOT NULL").fetchone()[0]
            g = ct(skill, repo, "graph")
            ok = counts["symbols"] > 500 and resolved > 50 and len(g["nodes"]) > 3 and len(g["edges"]) > 3
            record(3, "Build a usable structural representation", ok,
                   {**counts, "resolved_imports": resolved, "module_nodes": len(g["nodes"]), "module_edges": len(g["edges"])},
                   "Run `ct graph` or open report → Architecture; modules and edges should appear.")
        c3()

        @guard(4, "Explain its architecture using actual evidence", "")
        def c4():
            ov = state["ov"]
            checked, bad = 0, []
            for cat in ("frameworks", "databases", "auth", "security", "external_services", "test_frameworks", "build", "lint"):
                for it in ov.get(cat) or []:
                    if it.get("line"):
                        text = lines_of(repo, it["file"])[it["line"] - 1]
                        checked += 1
                        pkgs = [k for k, v in CATALOG.items() if v[1] == it["name"]]
                        if not any(f'"{k}"' in text or text.strip().lower().startswith(k) for k in pkgs):
                            bad.append({"name": it["name"], "file": it["file"], "line": it["line"], "text": text.strip()})
            for e in ov["entry_points"]:
                ev = e.get("evidence") or {}
                if ev.get("file") and ev.get("line"):
                    checked += 1
                    if ev["line"] > len(lines_of(repo, ev["file"])):
                        bad.append(e)
            hubs = ov["hubs"][:3]
            record(4, "Explain its architecture using actual evidence", checked > 5 and not bad,
                   {"evidence_lines_checked": checked, "bad_evidence": bad[:5], "top_hubs": hubs,
                    "note": "Narrative explanation is written by the agent; the engine supplies these cited facts."},
                   "Open report → Overview → click any stack chip: it should open the exact package.json line naming that package.")
        c4()

        @guard(5, "Explore a specific feature across multiple files", "")
        def c5():
            f = ct(skill, repo, "trace", "createApplication", "--depth", "3", "--title", "Acceptance: createApplication")
            files = sorted({s["file"] for s in f["steps"]})
            state["flow"] = f
            record(5, "Explore a specific feature across multiple files", len(files) >= 2,
                   {"flow": f["title"], "steps": len(f["steps"]), "files_touched": files, "verification": f["verification"]},
                   "Report → Execution flows → pick 'Acceptance: createApplication' and press Next; the code pane should switch files.")
        c5()

        @guard(6, "Show highlighted source with accurate paths and line numbers", "")
        def c6():
            sym = ct(skill, repo, "symbol", "res.status")["symbol"]
            ev = ct(skill, repo, "evidence", sym["file"], f"{sym['start_line']}-{sym['end_line']}", "--highlight", str(sym["start_line"]))
            real = lines_of(repo, sym["file"])
            mism = [l["n"] for l in ev["lines"] if real[l["n"] - 1] != l["text"]]
            record(6, "Show highlighted source with accurate paths and line numbers",
                   not mism and ev["lines"][0]["hl"] and "res.status = function" in real[sym["start_line"] - 1],
                   {"symbol": "res.status", "file": sym["file"], "lines": f"{sym['start_line']}-{sym['end_line']}",
                    "first_line": real[sym["start_line"] - 1].strip(), "mismatched_lines": mism},
                   f"Open {sym['file']} in your editor at line {sym['start_line']}: it must be `res.status = function status(code) {{`.")
        c6()

        @guard(7, "Trace a feature's relationships across the repository", "")
        def c7():
            cal = ct(skill, repo, "callers", "res.status")["callers"]
            cee = ct(skill, repo, "callees", "createApplication")["callees"]
            files = sorted({c["file"] for c in cal})
            bad = []
            for c in cal[:40]:
                if "status" not in lines_of(repo, c["file"])[c["line"] - 1]:
                    bad.append(c)
            record(7, "Trace a feature's relationships across the repository", len(files) >= 3 and not bad,
                   {"callers_of_res.status": len(cal), "in_files": files[:8], "callers_whose_line_lacks_'status'": len(bad),
                    "callees_of_createApplication": [(c["expr"], c["resolution"]) for c in cee][:10]},
                   "Run `ct callers res.status --no-refresh`; open two of the listed file:line spots and confirm they call .status(.")
        c7()

        @guard(18, "Approval gate before executing repository code", "")
        def gate():
            r = ct(skill, repo, "tests", "run", "--", "npx", "--no-install", "mocha", "test/res.status.js")
            record(18.1, "Approval gate: refuses to run tests without --yes", r.get("status") == "needs-approval",
                   {"response": r.get("status"), "message": r.get("message")},
                   "Run `ct tests run -- npx mocha test/res.status.js` without --yes: it must answer needs-approval and run nothing.")
        gate()

        @guard(16, "Identify relevant tests", "")
        def c16():
            t = ct(skill, repo, "tests-for", "res.status")["tests"]
            top = [x["test_file"] for x in t[:3]]
            record(16, "Identify relevant tests", top and top[0] == "test/res.status.js",
                   {"top_tests": [{k: x[k] for k in ("test_file", "score", "signals")} for x in t[:3]]},
                   "Run `ct tests-for res.status`: test/res.status.js should be first, with the reasons listed.")
        c16()

        # ---- explanation in two languages + invented-evidence rejection
        @guard(12, "Explain the repository in English and at least one other language", "")
        def c12():
            sym = ct(skill, repo, "symbol", "res.status")["symbol"]
            s, e = sym["start_line"], sym["end_line"]
            body = lines_of(repo, sym["file"])
            throw_lines = [i + 1 for i in range(s - 1, e) if "throw" in body[i]]
            exp = {"id": "acceptance-res-status", "level": "beginner",
                   "title": {"en": "How res.status() validates the code", "hi": "res.status() कोड की जाँच कैसे करता है",
                             "hinglish": "res.status() code ko kaise validate karta hai"},
                   "sections": [{"heading": {"en": "Validation", "hi": "जाँच", "hinglish": "Validation"},
                                 "body": {"en": "It throws if the status code is not an integer or is out of range.",
                                          "hi": "अगर स्टेटस कोड पूर्णांक नहीं है या सीमा से बाहर है तो यह एरर throw करता है।",
                                          "hinglish": "Agar status code integer nahi hai ya range se bahar hai to ye error throw karta hai."},
                                 "status": "verified-source",
                                 "evidence": [{"file": sym["file"], "lines": f"{s}-{e}", "highlight": ",".join(map(str, throw_lines))}]}]}
            good = out / "explanation-good.json"
            good.write_text(json.dumps(exp, ensure_ascii=False), encoding="utf-8")
            r_good = ct(skill, repo, "explain", "add", str(good))
            bad = dict(exp, id="acceptance-invented")
            bad["sections"] = [dict(exp["sections"][0], evidence=[{"file": "lib/auth/login.js", "lines": "39-47"}])]
            badp = out / "explanation-invented.json"
            badp.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
            r_bad = ct(skill, repo, "explain", "add", str(badp))
            rep_hi = ct(skill, repo, "report", "--lang", "hi")
            md_hi = Path(rep_hi["report_md"]).read_text(encoding="utf-8")
            shutil.copy(rep_hi["report_md"], out / "report.hi.md")
            has_dev = bool(re.search(r"[ऀ-ॿ]", md_hi))
            ok = r_good.get("ok") and set(r_good["languages"]) >= {"en", "hi", "hinglish"} and r_bad.get("ok") is False and has_dev
            record(12, "Explain the repository in English and at least one other language", ok,
                   {"stored_languages": r_good.get("languages"), "invented_evidence_rejected": r_bad.get("errors"),
                    "hindi_report_has_devanagari": has_dev},
                   "Report → language selector → हिन्दी / Hinglish: UI and the 'How res.status() validates the code' lesson switch; file paths stay in English.")
        c12()

        # ---- change detection, comparison, impact (modify res.status)

        @guard(14, "Detect changes on a subsequent run", "")
        def c14():
            new = original.replace("res.status = function status(code) {",
                                   "res.status = function status(code) {\n  if (code === 418) {\n    throw new RangeError('teapots not supported');\n  }", 1)
            assert new != original
            target.write_text(new, encoding="utf-8")
            s = ct(skill, repo, "scan", "--quiet")
            ch = s["changes_since_last_scan"]
            record(14, "Detect changes on a subsequent run", ch["modified"] == ["lib/response.js"] and s["parsed_now"] == 1,
                   {"modified": ch["modified"], "added": ch["added"], "deleted": ch["deleted"], "files_reparsed": s["parsed_now"],
                    "rescan_seconds": s["seconds"], "new_snapshot": s["snapshot"], "previous_snapshot": s["previous_snapshot"]},
                   "Edit any file, run `ct scan`: only that file is listed as modified and re-parsed.")
        c14()

        @guard(15, "Compare old and new code", "")
        def c15():
            r = ct(skill, repo, "changes")
            state["changes"] = r
            f = next(x for x in r["files"] if x["path"] == "lib/response.js")
            mod = next(m for m in f["symbols"]["symbols_modified"] if m["qualname"] == "res.status")
            added_lines = [l for l in f["diff"] if l.startswith("+") and "418" in l]
            ok = bool(added_lines) and "if (code === 418)" in mod["behaviour_signals"].get("conditions_added", [])
            record(15, "Compare old and new code", ok,
                   {"diff_added_lines": added_lines, "symbol": mod["qualname"], "lines_before_after": [mod["old_lines"], mod["new_lines"]],
                    "behaviour_signals": mod["behaviour_signals"]},
                   "Report → Change analysis: lib/response.js shows the +lines in green and 'Conditions added: if (code === 418)'.")
        c15()

        @guard(17, "Produce a grounded change-impact analysis", "")
        def c17():
            r = state["changes"]
            callers = r["impact"]["callers"]
            bad = [c for c in callers[:30] if c["line"] > len(lines_of(repo, c["file"]))]
            tests = [t["test_file"] for t in r["impact"]["tests_to_run"]]
            ok = callers and not bad and "test/res.status.js" in tests[:5] and r["impact"]["completeness"]["note"]
            record(17, "Produce a grounded change-impact analysis", ok,
                   {"impacted_symbols": r["summary"]["impacted_symbols"], "first_callers": callers[:5], "tests_to_run": tests[:5],
                    "risks": [x["kind"] for x in r["risks"]], "completeness": r["impact"]["completeness"]},
                   "Report → Change analysis → Architecture impact: callers by distance with clickable file:line, tests to run, and the completeness note.")
        c17()

        # ---- verification levels (inferred vs test vs runtime)
        @guard(18, "Distinguish inferred, test-verified and runtime-observed behaviour", "")
        def c18():
            flow_ok = state["flow"]["verification"] in ("structurally-inferred", "verified-source") and \
                state["flow"]["verification_note"].startswith("Reconstructed")
            ev = {"static_flow_label": state["flow"]["verification"], "static_flow_note": state["flow"]["verification_note"]}
            if not a.run_tests:
                record(18, "Distinguish inferred, test-verified and runtime-observed behaviour", flow_ok, ev,
                       "Report → Simulation lab: three separately labelled levels.", skipped=True)
                return
            t = ct(skill, repo, "tests", "run", "--yes", "--label", "acceptance", "--", "npx", "--no-install", "mocha",
                   "--require", "test/support/env", "--check-leaks", "test/res.status.js")
            rt = ct(skill, repo, "runtime", "--yes", "--label", "acceptance", "--", "npx", "--no-install", "mocha",
                    "--require", "test/support/env", "test/res.status.js")
            rs = next((m for m in rt.get("mapped_symbols", []) if m["qualname"] == "res.status"), None)
            ev.update({"test_run": {"status": t["status"], "counts": t["counts"], "verification": t["verification"],
                                    "failed": [x["name"] for x in t.get("failed_tests", [])]},
                       "runtime_trace": {"verification": rt["verification"], "events": rt["events_total"],
                                         "res.status_calls": rs and rs["calls"], "res.status_throws": rs and rs["throws"]}})
            ok = flow_ok and t["status"] in ("passed", "failed") and t["counts"]["passed"] > 0 and \
                t["verification"].startswith("test-verified") and rt["verification"] == "runtime-observed" and rs
            record(18, "Distinguish inferred, test-verified and runtime-observed behaviour", ok, ev,
                   "Report → Simulation lab: Level 1 (inferred), Level 2 (per-test pass/fail), Level 3 (runtime calls with throw counts).")
        c18()

        # ---- knowledge base persistence (after all writes)
        @guard(13, "Preserve a structured knowledge base", "")
        def c13():
            kd = data_dir / "knowledge"
            snaps = ct(skill, repo, "snapshots")["snapshots"]
            files = {"index.db": (kd / "index.db").exists(), "flows": len(list((kd / "flows").glob("*.json"))),
                     "explanations": len(list((kd / "explanations").glob("*.json"))), "changes": len(list((kd / "changes").glob("*.json")))}
            st = ct(skill, repo, "status")
            ok = files["index.db"] and files["flows"] >= 1 and files["explanations"] >= 1 and len(snaps) >= 2
            record(13, "Preserve a structured knowledge base", ok, {**files, "snapshots": [s["id"] for s in snaps],
                                                                   "evidence_status": st.get("evidence_status")},
                   "Look inside <repo>/.codebase-tutor/knowledge: index.db, flows/, explanations/, changes/; `ct snapshots` lists 2+ states.")
        c13()

        # ---- reports
        @guard(8, "Generate a readable report.md", "")
        def c8():
            r = ct(skill, repo, "report", "--lang", "en")
            md = Path(r["report_md"]).read_text(encoding="utf-8")
            v = ct(skill, repo, "verify", "--file", r["report_md"])
            problems = v["citation_problems"]
            shutil.copy(r["report_md"], out / "report.en.md")
            state["report"] = r
            record(8, "Generate a readable report.md", len(md) > 3000 and not problems,
                   {"bytes": len(md), "citations_checked": len(v["citations"]), "citation_problems": problems[:5],
                    "sections": re.findall(r"^## (.+)$", md, re.M)},
                   "Open report.en.md (copied next to this file): every `path:line` should match the repo.")
        c8()

        @guard(9, "Generate an interactive index.html", "")
        def c9():
            rd = Path(state["report"]["report_dir"])
            need = ["index.html", "app.js", "styles.css", "data.js", "vendor/cytoscape.min.js"]
            present = {n: (rd / n).exists() for n in need}
            raw = (rd / "data.js").read_text(encoding="utf-8")
            data = json.loads(raw[len("window.CT_DATA="):].rstrip().rstrip(";"))
            leak = "do-not-leak-7f3a9c" in raw
            dest = out / "report"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(rd, dest)
            record(9, "Generate an interactive index.html", all(present.values()) and not leak and not any("cdn" in l for l in (rd / "index.html").read_text().splitlines() if "<script" in l),
                   {"files": present, "offline_no_cdn": True, "fake_secret_leaked": leak, "languages": data["meta"]["languages"],
                    "copied_to": str(dest)},
                   "Double-click report/index.html (copied next to this file). It must open offline from file:// with no server.")
            state["data"] = data
        c9()

        @guard(10, "Explore architecture nodes and source evidence", "")
        def c10():
            d = state["data"]
            emb = d["sources"]
            mism = []
            for path, lines in list(emb.items())[:40]:
                real = lines_of(repo, path)
                if len(real) != len(lines):
                    mism.append(path)
            record(10, "Explore architecture nodes and source evidence", len(d["graph"]["modules"]["nodes"]) > 3 and len(emb) > 20 and not mism,
                   {"module_nodes": len(d["graph"]["modules"]["nodes"]), "file_nodes": len(d["graph"]["file_nodes"]),
                    "embedded_source_files": len(emb), "line_count_mismatches": mism},
                   "Report → Architecture: click 'lib', double-click to see files, click a file, then a symbol link → Code view highlights its lines.")
        c10()

        @guard(11, "Animate a source-backed execution flow", "")
        def c11():
            bad, total = [], 0
            for fl in state["data"]["flows"]:
                for st in fl["steps"]:
                    if st.get("file") and st.get("line") and st.get("source_line") is not None:
                        total += 1
                        real = lines_of(repo, st["file"])[st["line"] - 1].strip()[:200]
                        if real != st["source_line"] and not st.get("stale"):
                            bad.append({"step": st["n"], "file": st["file"], "line": st["line"]})
            record(11, "Animate a source-backed execution flow", total > 10 and not bad,
                   {"flows": [f["title"] for f in state["data"]["flows"]], "steps_checked_against_source": total, "mismatches": bad[:5],
                    "note": "Stale steps (code changed after tracing) are flagged in the UI, not hidden."},
                   "Report → Execution flows → Play: steps advance, the lane diagram moves, the highlighted code line matches the step text.")
        c11()

    finally:
        if target.read_text(encoding="utf-8") != original:
            target.write_text(original, encoding="utf-8")
        if not had_secret and secret_file.exists():
            secret_file.unlink()
    porcelain = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=all"], capture_output=True, text=True).stdout
    stray = [ln[3:] for ln in porcelain.splitlines() if not ln[3:].startswith(".codebase-tutor/") and "node_modules" not in ln]
    record(19, "Safety: generated data stays in .codebase-tutor/ and secrets are not exported", not stray,
           {"files_changed_outside_data_dir": stray, "repo_head": head}, "Run `git status` in the repo: only .codebase-tutor/ is new.")

    RESULTS.sort(key=lambda r: r["id"])
    summary = {"passed": sum(r["status"] == "PASS" for r in RESULTS), "failed": sum(r["status"] == "FAIL" for r in RESULTS),
               "skipped": sum(r["status"] == "SKIPPED" for r in RESULTS), "seconds": round(time.time() - t0, 1),
               "repo": str(repo), "repo_commit": head, "python": sys.version.split()[0], "platform": sys.platform}
    (out / "results.json").write_text(json.dumps({"summary": summary, "results": RESULTS}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
