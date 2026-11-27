"""End-to-end engine tests on fixture repositories (each test gets a fresh git repo copy)."""
import json
import subprocess
from pathlib import Path


def test_scan_inventory_coverage_and_exclusions(js_repo, run_ct):
    s = run_ct(js_repo, "scan", "--quiet")
    assert s["first_scan"] and s["parse_failures"] == 0
    cov = s["coverage"]
    assert cov["by_status"]["analyzed"] == 8
    assert cov["by_status"]["secret"] == 1  # .env listed, never read
    assert "node_modules" in cov["excluded_dirs"]


def test_overview_detects_stack_and_entry_points(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    ov = run_ct(js_repo, "overview")
    names = {f["name"] for f in ov["frameworks"]} | {d["name"] for d in ov["databases"]} | {a["name"] for a in ov["auth"]}
    assert {"Express", "MongoDB (Mongoose)", "bcrypt", "JWT (jsonwebtoken)"} <= names
    express = next(f for f in ov["frameworks"] if f["name"] == "Express")
    assert express["file"] == "package.json" and express["line"] == 7
    entries = {(e["file"], e["reason"].split(" (")[0]) for e in ov["entry_points"]}
    assert ("src/server.js", 'package.json "main"') in entries
    assert [e["name"] for e in ov["env_var_names"]] == ["JWT_SECRET", "PORT"]


def test_call_resolution_and_routes(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    callees = run_ct(js_repo, "callees", "login")["callees"]
    by_expr = {c["expr"]: c for c in callees}
    assert by_expr["User.findByEmail"]["resolution"] == "verified-source"
    assert by_expr["User.findByEmail"]["target"]["qualname"] == "User.findByEmail"
    assert by_expr["signToken"]["target"]["file"] == "src/services/token.js"
    assert by_expr["bcrypt.compare"]["resolution"] == "external" and by_expr["bcrypt.compare"]["external"] == "bcrypt"
    routes = {r["full_path"]: r for r in run_ct(js_repo, "routes")["routes"] if r["kind"] == "route"}
    assert set(routes) == {"/api/auth/login", "/api/auth/logout"}  # mount prefix applied
    assert all(routes["/api/auth/logout"]["handler_ids"])


def test_trace_route_has_branches_and_external_call(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    flow = run_ct(js_repo, "trace", "POST /api/auth/login")
    kinds = [s["kind"] for s in flow["steps"]]
    assert kinds[:2] == ["mount", "route"]
    texts = " | ".join(s["text"] for s in flow["steps"])
    assert "bcrypt.compare" in texts and "User.findByEmail" in texts
    fails = [o for o in flow["outcomes"] if o["outcome"] == "failure"]
    assert len(fails) == 3 and all(o["verification"] == "structurally-inferred" for o in fails)
    assert flow["verification_note"].startswith("Reconstructed from source")
    assert (js_repo / flow["saved_to"]).exists()


def test_evidence_exact_redaction_and_bounds(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    ev = run_ct(js_repo, "evidence", "src/controllers/auth.controller.js", "14-17", "--highlight", "14")
    assert ev["lines"][0]["text"].strip().startswith("const isMatch = await bcrypt.compare")
    assert ev["lines"][0]["hl"] is True
    bad = run_ct(js_repo, "evidence", "src/controllers/auth.controller.js", "40-50", check=False)
    assert "out of bounds" in bad["error"]
    sec = run_ct(js_repo, "evidence", ".env", "1", check=False)
    assert "refusing" in sec["error"]
    from codebase_tutor.evidence import redact_line
    assert redact_line('const password = "hunter2hunter2";')[0] == 'const password = "«redacted»";'
    assert redact_line('fetch("http://localhost:3000/api/items?page=2&token=live-secret-value")')[0] == \
        'fetch("http://localhost:3000/api/items?page=2&token=«redacted»")'


def test_incremental_scan_reparses_only_changed(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    p = js_repo / "src/services/token.js"
    p.write_text(p.read_text() + "\nfunction verifyToken(t) {\n  return t;\n}\n")
    (js_repo / "src/models/user.js").unlink()
    s = run_ct(js_repo, "scan", "--quiet")
    assert s["parsed_now"] == 1
    assert s["changes_since_last_scan"]["modified"] == ["src/services/token.js"]
    assert s["changes_since_last_scan"]["deleted"] == ["src/models/user.js"]
    assert run_ct(js_repo, "search", "verifyToken")["symbols"][0]["start_line"] == 9
    assert not run_ct(js_repo, "search", "findByEmail")["symbols"]


def test_auto_refresh_on_query(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    p = js_repo / "src/middleware/auth.js"
    p.write_text("// header\n" + p.read_text())
    sym = run_ct(js_repo, "symbol", "requireAuth")
    assert sym["symbol"]["start_line"] == 2


def test_change_intelligence(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    p = js_repo / "src/middleware/auth.js"
    p.write_text(p.read_text().replace("  next();", "  if (req.headers.authorization === 'blocked') {\n    return res.status(403).end();\n  }\n  next();"))
    t = js_repo / "src/services/token.js"
    t.write_text(t.read_text().replace("function signToken(user) {", "function signToken(user, ttl) {"))
    ch = run_ct(js_repo, "changes")
    files = {f["path"]: f for f in ch["files"]}
    mod = files["src/middleware/auth.js"]["symbols"]["symbols_modified"][0]
    assert mod["qualname"] == "requireAuth"
    assert "if (req.headers.authorization === 'blocked')" in mod["behaviour_signals"]["conditions_added"]
    assert mod["behaviour_signals"]["status_codes"]["after"] == ["401", "403"]
    tok = files["src/services/token.js"]["symbols"]["symbols_modified"][0]
    assert tok["signature_changed"]
    callers = {c["qualname"] for c in ch["impact"]["callers"]}
    assert "login" in callers  # login calls signToken
    kinds = {r["kind"] for r in ch["risks"]}
    assert {"contract-change", "security-sensitive"} <= kinds
    assert any("auth.test.js" in x["test_file"] for x in ch["impact"]["tests_to_run"])


def test_change_vs_git_ref(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    (js_repo / "src/new.js").write_text("function added() {}\nmodule.exports = { added };\n")
    ch = run_ct(js_repo, "changes", "--since", "git:HEAD")
    assert ch["baseline"]["kind"] == "git-ref"
    assert [f["path"] for f in ch["files"] if f["status"] == "added"] == ["src/new.js"]


def test_context_coverage_table(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    ctx = run_ct(js_repo, "context", "signToken", "--task", "add expiry")
    areas = {c["area"]: c["status"] for c in ctx["coverage"]}
    assert areas["Implementation"] == "Found" and areas["Callers"].startswith("Found")
    assert areas["Configuration / env vars"] == "Found"
    assert areas["Edge cases"] == "Needs agent review"
    assert any(r["path"] == "/api/auth/login" for r in ctx["routes"])


def test_explanations_reject_invented_evidence_and_detect_staleness(js_repo, run_ct, tmp_path):
    run_ct(js_repo, "scan", "--quiet")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"id": "x", "title": {"en": "X"}, "claims": [{"text": {"en": "c"},
                               "evidence": [{"file": "src/nope.js", "lines": "1-2"}]}]}))
    r = run_ct(js_repo, "explain", "add", str(bad))
    assert r["ok"] is False and "file not found" in r["errors"][0]
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"id": "login", "title": {"en": "Login", "hi": "लॉगिन"}, "level": "beginner",
                                "sections": [{"body": {"en": "compare"}, "status": "verified-source",
                                              "evidence": [{"file": "src/controllers/auth.controller.js", "lines": "14-17", "highlight": "14"}]}]}))
    r = run_ct(js_repo, "explain", "add", str(good))
    assert r["ok"] and r["languages"] == ["en", "hi"]
    p = js_repo / "src/controllers/auth.controller.js"
    p.write_text("// moved down\n" + p.read_text())
    v = run_ct(js_repo, "verify")
    assert v["explanations"][0]["evidence"] == {"moved": 1}
    p.write_text(p.read_text().replace("bcrypt.compare(password, user.password)", "bcrypt.compare(password, user.hash)"))
    v = run_ct(js_repo, "verify")
    assert v["explanations"][0]["evidence"] == {"stale": 1}


def test_citation_checker(js_repo, run_ct, tmp_path):
    run_ct(js_repo, "scan", "--quiet")
    md = tmp_path / "a.md"
    md.write_text("See `src/app.js:6` and `src/app.js:99` and `src/ghost.js:1`.")
    v = run_ct(js_repo, "verify", "--file", str(md))
    st = {c["citation"]: c["status"] for c in v["citations"]}
    assert st == {"src/app.js:6": "ok", "src/app.js:99": "out-of-range", "src/ghost.js:1": "missing"}


def test_tests_require_approval_and_report_real_results(py_repo, run_ct):
    run_ct(py_repo, "scan", "--quiet")
    plan = run_ct(py_repo, "tests", "plan", "login_user")
    cmd = plan["commands"][0]["command"]
    assert cmd[:3] == ["python", "-m", "pytest"] and "tests/test_auth.py" in cmd
    gated = run_ct(py_repo, "tests", "run", "--", *cmd)
    assert gated["status"] == "needs-approval"
    import sys
    res = run_ct(py_repo, "tests", "run", "--yes", "--", sys.executable, "-m", "pytest", "-q", "tests/test_auth.py")
    assert res["status"] == "passed" and res["counts"] == {"passed": 3, "failed": 0, "skipped": 0}
    p = py_repo / "app/services/auth.py"
    p.write_text(p.read_text().replace("return password == stored", "return password != stored"))
    res = run_ct(py_repo, "tests", "run", "--yes", "--", sys.executable, "-m", "pytest", "-q", "tests/test_auth.py")
    assert res["status"] == "failed" and res["counts"]["failed"] == 1
    assert "test_check_password" in res["failed_tests"][0]["name"]


def test_runtime_trace_python(py_repo, run_ct):
    import sys
    run_ct(py_repo, "scan", "--quiet")
    gated = run_ct(py_repo, "runtime", "--", sys.executable, "-c", "print(1)")
    assert gated["status"] == "needs-approval"
    r = run_ct(py_repo, "runtime", "--yes", "--", sys.executable, "-c",
               "from app.services.auth import Session; Session('u').refresh()")
    assert r["verification"] == "runtime-observed"
    names = {m["qualname"]: m["calls"] for m in r["mapped_symbols"]}
    assert names["Session.refresh"] == 1 and names["Session.validate"] == 1


def test_python_resolution(py_repo, run_ct):
    run_ct(py_repo, "scan", "--quiet")
    callees = {c["expr"]: c for c in run_ct(py_repo, "callees", "Session.refresh")["callees"]}
    assert callees["self.validate"]["resolution"] == "verified-source"
    callees = {c["expr"]: c for c in run_ct(py_repo, "callees", "login")["callees"]}
    assert callees["login_user"]["target"]["file"] == "app/services/auth.py"
    routes = run_ct(py_repo, "routes")["routes"]
    assert routes[0]["framework"] == "flask" and routes[0]["handler_ids"][0]


def test_report_generation(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    run_ct(js_repo, "trace", "POST /api/auth/login")
    for lang in ("en", "hi", "hinglish"):
        r = run_ct(js_repo, "report", "--lang", lang)
        md = Path(r["report_md"]).read_text()
        assert "src/controllers/auth.controller.js" in md
    out = Path(r["report_dir"])
    for name in ("index.html", "app.js", "styles.css", "data.js", "vendor/cytoscape.min.js"):
        assert (out / name).exists()
    data = json.loads((out / "data.js").read_text()[len("window.CT_DATA="):].rstrip().rstrip(";"))
    assert set(data["i18n"]) >= {"en", "hi", "hinglish"}
    assert "super-secret-value" not in (out / "data.js").read_text()
    assert ".env" not in data["sources"]
    assert data["flows"][0]["steps"]
    v = run_ct(js_repo, "verify", "--file", str(Path(r["report_md"])))
    assert v["citation_problems"] == []


def test_generated_data_stays_in_data_dir(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    run_ct(js_repo, "report")
    out = subprocess.run(["git", "-C", str(js_repo), "status", "--porcelain"], capture_output=True, text=True).stdout
    assert all(line[3:].startswith(".codebase-tutor/") for line in out.splitlines())


def test_system_map_layers_storages_and_evidence(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))
    from codebase_tutor.store import Store
    from codebase_tutor.dataflow import system_map
    st = Store(js_repo / ".codebase-tutor" / "knowledge" / "index.db")
    sm = system_map(st)
    nodes = {n["id"]: n for n in sm["nodes"]}
    assert nodes["@client"]["layer"] == "client"
    assert nodes["src/routes"]["layer"] == "routing"
    assert nodes["src/controllers"]["layer"] == "handlers"
    stores = {n["label"]: n["storage_kind"] for n in sm["nodes"] if n["kind"] == "storage"}
    assert stores == {"Password hashing": "auth", "JWT tokens": "auth"}
    data = [e for e in sm["edges"] if e["kind"] == "data"]
    assert {(e["source"], e["target"]) for e in data} == {("src/controllers", "@Password hashing"), ("src/services", "@JWT tokens")}
    for e in sm["edges"]:
        assert e["evidence"], e
        for ev in e["evidence"]:
            assert (js_repo / ev["file"]).exists() and ev["line"] > 0


def test_mern_frontend_calls_routes_and_models_hit_database(mern_repo, run_ct):
    import json as _json
    run_ct(mern_repo, "scan", "--quiet")
    from codebase_tutor.store import Store
    from codebase_tutor.dataflow import system_map
    st = Store(mern_repo / ".codebase-tutor" / "knowledge" / "index.db")
    # router.get('/') under app.use('/api/notes') answers GET /api/notes (no trailing slash)
    paths = {(r["method"], r["full_path"]) for r in st.q("SELECT method, full_path FROM routes WHERE kind='route'")}
    assert ("GET", "/api/notes") in paths and ("POST", "/api/notes/add") in paths
    sm = system_map(st)
    nodes = {n["id"]: n for n in sm["nodes"]}
    assert nodes["client/src"]["layer"] == "client"
    assert nodes["server/models"]["layer"] == "data"
    req = [e for e in sm["edges"] if e["kind"] == "request" and e["source"] == "client/src"]
    assert len(req) == 1 and req[0]["target"] == "server/routes" and req[0]["weight"] == 2   # incl. URL on next line
    assert "@External HTTP APIs" not in nodes                                               # axios explained by routes
    db = [e for e in sm["edges"] if e["source"] == "server/controllers" and e["target"] == "@MongoDB"][0]
    assert db["ops"] == {"read": 1, "write": 1} and db["verification"] == "structurally-inferred"
    # flow: frontend caller first, then route, then the Mongo write through the model instance
    out = run_ct(mern_repo, "trace", "POST /api/notes/add")
    flow = out.get("flow", out)
    kinds = [s["kind"] for s in flow["steps"]]
    assert kinds[0] == "client-call" and flow["steps"][0]["file"] == "client/src/pages/Notes.jsx"
    dbs = [s for s in flow["steps"] if s.get("db_op")]
    assert [(s["db_op"], s["db_model"]) for s in dbs] == [("write", "Note")]
    assert "error" not in run_ct(mern_repo, "trace", "GET /api/notes/")                       # trailing slash tolerated


def test_http_call_method_scoped_and_same_line_storage_preserved(mern_repo, run_ct):
    (mern_repo / "client/src/pages/Extra.jsx").write_text(
        'import axios from "axios";\n'
        'import fs from "fs";\n'
        "export function check() {\n"
        '  fetch("/api/notes");\n'
        '  fetch("/api/notes/add", {\n'
        '    method: "POST"\n'
        "  });\n"
        '  fetch(/* 1) keep */ "/api/notes/add", { method: "POST" });\n'
        '  fetch("/api/notes/add", { headers: { "X-Pattern": /\\)/.source }, method: "POST" });\n'
        '  axios.post("http://localhost:5000/api/notes/add", fs.readFileSync("note.json"));\n'
        "}\n"
    )
    run_ct(mern_repo, "scan", "--quiet")
    from codebase_tutor.store import Store
    from codebase_tutor.access import AccessIndex, _call_slice
    from codebase_tutor.dataflow import system_map
    st = Store(mern_repo / ".codebase-tutor" / "knowledge" / "index.db")
    calls = [c for c in AccessIndex(st, mern_repo).http_calls() if c["file"] == "client/src/pages/Extra.jsx"]
    by_line = {c["line"]: c["method"] for c in calls}
    assert by_line == {4: "GET", 5: "POST", 8: "POST", 9: "POST", 10: "POST"}
    assert '"/users"' in _call_slice(['requests.get(  # ) ignore', '    "/users")'], 1, "requests.get", is_py=True)
    sm = system_map(st, root=mern_repo)
    assert any(n["id"] == "@File system" for n in sm["nodes"])


def test_same_line_catch_ordered_before_handler_call_and_return(js_repo, run_ct):
    (js_repo / "src/services/recover.js").write_text(
        "function fallback(e) { return e; }\n"
        "function risky() { try { return 1; } catch (err) { return fallback(err); } }\n"
        "module.exports = { risky };\n"
    )
    run_ct(js_repo, "scan", "--quiet")
    flow = run_ct(js_repo, "trace", "risky")
    kinds = [s["kind"] for s in flow["steps"]]
    assert kinds.index("catch") < kinds.index("call") < kinds.index("return", kinds.index("catch"))


def test_evidence_blocks_traversal_and_case_variant_secrets(js_repo, run_ct):
    run_ct(js_repo, "scan", "--quiet")
    for bad in ("src/../.env", "./.env", ".env"):
        res = run_ct(js_repo, "evidence", bad, "1", check=False)
        assert "refusing" in res["error"], (bad, res)
    from codebase_tutor.inventory import classify
    assert classify(".ENV", 10)[1] == "secret"
    assert classify("CREDENTIALS.JSON", 10)[1] == "secret"
