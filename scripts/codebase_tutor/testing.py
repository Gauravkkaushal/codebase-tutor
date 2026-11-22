"""Test-backed verification (Simulation Lab Level 2): detect runners, plan, run ONLY with approval, parse results."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from .config import data_dir, load_config
from .graph import find_symbols, tests_for
from .snapshots import git_info

VALUE_OPTIONS = {"--require", "-r", "--config", "-c", "--file", "--setupFiles", "--rootDir", "--reporter", "-R", "--ui",
                 "-u", "--timeout", "-t", "--exclude", "--ignore", "--spec", "--extension", "--project", "--selectProjects"}


def _pkg(root: Path) -> dict:
    try:
        return json.loads((root / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def detect_runners(root: Path, store) -> dict:
    root = Path(root)
    runners = []
    pkg = _pkg(root)
    script = (pkg.get("scripts") or {}).get("test", "")
    deps = {**(pkg.get("dependencies") or {}), **(pkg.get("devDependencies") or {})}
    nm = root / "node_modules"
    for name in ("jest", "vitest", "mocha", "ava", "tap"):
        if name in deps or re.search(rf"\b{name}\b", script):
            runners.append({"runner": name, "ecosystem": "node", "script": script or None,
                            "installed": (nm / ".bin" / name).exists(),
                            "evidence": "package.json scripts.test / devDependencies"})
    if re.search(r"\bnode\s+--test\b", script):
        runners.append({"runner": "node-test", "ecosystem": "node", "script": script, "installed": True, "evidence": "scripts.test"})
    py_signals = [p for p in ("pytest.ini", "conftest.py", "tox.ini", "setup.cfg") if (root / p).exists()]
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8", errors="replace") if (root / "pyproject.toml").exists() else ""
    if "[tool.pytest" in pyproject:
        py_signals.append("pyproject [tool.pytest]")
    has_py_tests = store.one("SELECT 1 FROM files WHERE role='test' AND lang='python' LIMIT 1") is not None
    if py_signals or has_py_tests:
        try:
            import importlib.util
            installed = importlib.util.find_spec("pytest") is not None
        except Exception:
            installed = False
        runners.append({"runner": "pytest", "ecosystem": "python", "installed": installed,
                        "evidence": ", ".join(py_signals) or "python test files present"})
    if (root / "go.mod").exists():
        runners.append({"runner": "go-test", "ecosystem": "go", "installed": None, "evidence": "go.mod"})
    if (root / "Cargo.toml").exists():
        runners.append({"runner": "cargo-test", "ecosystem": "rust", "installed": None, "evidence": "Cargo.toml"})
    notes = []
    if any(r["ecosystem"] == "node" for r in runners) and not nm.exists():
        notes.append("node_modules/ is missing: dependencies must be installed (e.g. `npm install`) before tests can run. Ask the user first.")
    return {"runners": runners, "notes": notes}


def _base_command(root: Path, runner: str, script: str | None) -> list:
    if runner in ("mocha", "jest", "vitest", "ava", "tap") and script and re.search(rf"\b{runner}\b", script):
        toks = shlex.split(script)
        i = next((k for k, t in enumerate(toks) if t == runner or t.endswith("/" + runner)), None)
        if i is not None:
            toks = toks[i:]
            out, prev = [], ""
            for t in toks:
                p = root / t.rstrip("/")
                positional = not t.startswith("-") and prev not in VALUE_OPTIONS
                if positional and t != runner and (p.exists() or any(ch in t for ch in "*?")):
                    prev = t
                    continue
                out.append(t)
                prev = t
            return ["npx", "--no-install"] + out
    return {"jest": ["npx", "--no-install", "jest"], "vitest": ["npx", "--no-install", "vitest", "run"],
            "mocha": ["npx", "--no-install", "mocha"], "ava": ["npx", "--no-install", "ava"], "tap": ["npx", "--no-install", "tap"],
            "node-test": ["node", "--test"], "pytest": ["python", "-m", "pytest", "-q"],
            "go-test": ["go", "test"], "cargo-test": ["cargo", "test"]}.get(runner, [])


def plan(store, root: Path, target: str) -> dict:
    root = Path(root)
    det = detect_runners(root, store)
    if store.one("SELECT 1 FROM files WHERE path=?", (target,)):
        tests = tests_for(store, root, path=target)
        label = target
    else:
        found = find_symbols(store, target)
        if not found:
            return {"error": f"no symbol or file '{target}'"}
        tests = tests_for(store, root, sid=found[0]["id"])
        label = found[0]["qualname"]
    files = [t["test_file"] for t in tests[:8]]
    commands = []
    for r in det["runners"]:
        langs = ("python",) if r["ecosystem"] == "python" else ("javascript", "typescript", "tsx")
        sel = [f for f in files if store.one("SELECT lang FROM files WHERE path=?", (f,))[0] in langs]
        if not sel:
            continue
        base = _base_command(root, r["runner"], r.get("script"))
        if base:
            commands.append({"runner": r["runner"], "command": base + sel, "display": shlex.join(base + sel),
                             "installed": r.get("installed")})
    return {"target": label, "related_tests": tests[:8], "runners": det["runners"], "commands": commands, "notes": det["notes"],
            "approval": "Running tests executes repository code. Show the command to the user and run `ct tests run --yes -- <command>` only after they approve."}


def _augment(cmd: list, out_dir: Path) -> tuple[list, str | None, Path | None]:
    joined = " ".join(cmd)
    if re.search(r"\bpytest\b", joined):
        f = out_dir / "junit.xml"
        return cmd + [f"--junitxml={f}"], "junit", f
    if re.search(r"\bjest\b", joined):
        f = out_dir / "jest.json"
        return cmd + ["--json", f"--outputFile={f}"], "jest", f
    if re.search(r"\bvitest\b", joined):
        f = out_dir / "vitest.json"
        return cmd + ["--reporter=json", f"--outputFile={f}"], "jest", f
    if re.search(r"\bmocha\b", joined):
        f = out_dir / "mocha.json"
        out, skip = [], False
        for t in cmd:
            if skip:
                skip = False
                continue
            if t in ("--reporter", "-R"):
                skip = True
                continue
            if t.startswith("--reporter="):
                continue
            out.append(t)
        return out + ["--reporter", "json", "--reporter-option", f"output={f}"], "mocha", f
    return cmd, None, None


def _parse(kind: str, path: Path, root: Path) -> list:
    if not path or not path.exists():
        return []
    tests = []
    if kind == "junit":
        tree = ET.parse(path)
        for tc in tree.iter("testcase"):
            status = "passed"
            msg = None
            for child in tc:
                if child.tag in ("failure", "error"):
                    status, msg = "failed", (child.get("message") or child.text or "")[:500]
                elif child.tag == "skipped":
                    status = "skipped"
            f = tc.get("file") or (tc.get("classname", "").replace(".", "/") + ".py")
            tests.append({"name": f"{tc.get('classname')}::{tc.get('name')}", "file": f, "status": status,
                          "duration_ms": round(float(tc.get("time") or 0) * 1000, 1), "message": msg})
    elif kind == "jest":
        data = json.loads(path.read_text(encoding="utf-8"))
        for tr in data.get("testResults", []):
            f = os.path.relpath(tr.get("name") or tr.get("testFilePath") or "", root)
            for a in tr.get("assertionResults", []):
                st = {"passed": "passed", "failed": "failed"}.get(a.get("status"), "skipped")
                tests.append({"name": a.get("fullName") or a.get("title"), "file": f, "status": st,
                              "duration_ms": a.get("duration"), "message": "\n".join(a.get("failureMessages") or [])[:500] or None})
    elif kind == "mocha":
        data = json.loads(path.read_text(encoding="utf-8"))
        failed = {(t.get("fullTitle"), t.get("file")) for t in data.get("failures", [])}
        pending = {(t.get("fullTitle"), t.get("file")) for t in data.get("pending", [])}
        for t in data.get("tests", []):
            key = (t.get("fullTitle"), t.get("file"))
            st = "failed" if key in failed else "skipped" if key in pending else "passed"
            err = t.get("err") or {}
            tests.append({"name": t.get("fullTitle"), "file": os.path.relpath(t.get("file") or "", root) if t.get("file") else None,
                          "status": st, "duration_ms": t.get("duration"), "message": (err.get("message") or "")[:500] or None})
    return tests


def run(store, root: Path, cmd: list, approved: bool, timeout: int = 0, label: str | None = None) -> dict:
    root = Path(root)
    if not cmd:
        return {"error": "no command given. usage: ct tests run --yes -- <command...>"}
    if not approved:
        return {"status": "needs-approval", "command": shlex.join(cmd),
                "message": "Not executed. Running tests executes repository code; ask the user, then re-run with --yes."}
    cfg = load_config(root)
    timeout = timeout or int(cfg.get("tests", {}).get("timeout_seconds", 600))
    rid = time.strftime("T%Y%m%d-%H%M%S", time.gmtime())
    out_dir = data_dir(root) / "runs" / "tests" / rid
    out_dir.mkdir(parents=True, exist_ok=True)
    full, kind, report = _augment(list(cmd), out_dir)
    gi = git_info(root)
    t0 = time.time()
    try:
        proc = subprocess.run(full, cwd=str(root), capture_output=True, timeout=timeout)
        code, status = proc.returncode, None
        stdout, stderr = proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code, status = None, "timeout"
        stdout = (e.stdout or b"").decode("utf-8", "replace")
        stderr = (e.stderr or b"").decode("utf-8", "replace")
    except FileNotFoundError as e:
        code, status, stdout, stderr = None, "error", "", str(e)
    dur = round(time.time() - t0, 2)
    (out_dir / "stdout.log").write_text(stdout[-200_000:], encoding="utf-8")
    (out_dir / "stderr.log").write_text(stderr[-200_000:], encoding="utf-8")
    try:
        tests = _parse(kind, report, root) if kind else []
    except (ValueError, ET.ParseError, OSError) as e:
        tests = []
        stderr += f"\n[ct] could not parse structured results: {e}"
    counts = {s: sum(1 for t in tests if t["status"] == s) for s in ("passed", "failed", "skipped")}
    if status is None:
        if tests:
            status = "failed" if counts["failed"] else ("passed" if code == 0 else "error")
        else:
            status = "passed" if code == 0 else "failed" if code else "error"
    result = {"id": rid, "label": label, "command": shlex.join(cmd), "executed_command": shlex.join(full), "runner_format": kind,
              "started_at": t0, "duration_s": dur, "exit_code": code, "status": status, "counts": counts,
              "tests": tests[:3000], "structured": bool(tests), "git_commit": gi.get("commit"), "dirty": gi.get("dirty"),
              "snapshot": store.get_meta("last_snapshot"),
              "verification": "test-verified (executed)" if tests else "executed; per-test results unavailable (exit code only)",
              "stdout_tail": stdout[-3000:], "stderr_tail": stderr[-3000:]}
    (out_dir / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    result["saved_to"] = str((out_dir / "result.json").relative_to(root))
    brief = {k: v for k, v in result.items() if k not in ("tests",)}
    brief["failed_tests"] = [t for t in tests if t["status"] == "failed"][:50]
    return brief


def list_runs(root: Path) -> dict:
    base = data_dir(root) / "runs" / "tests"
    runs = []
    for p in sorted(base.glob("*/result.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        runs.append({k: d.get(k) for k in ("id", "label", "command", "status", "counts", "duration_s", "git_commit", "dirty")})
    return {"runs": runs}
