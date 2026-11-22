"""Runtime instrumentation (Simulation Lab Level 3, experimental). Executes ONLY with explicit approval."""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
from collections import Counter
from pathlib import Path

from ..config import data_dir, load_config
from ..snapshots import git_info

HERE = Path(__file__).resolve().parent


def _detect_lang(cmd: list) -> str:
    head = " ".join(cmd[:3])
    if re.search(r"\b(python[\d.]*|pytest|uv|poetry)\b", head):
        return "python"
    return "node"


def _map_symbol(store, file: str, name: str):
    name = name.replace("new ", "").replace(".<locals>", "")
    row = store.one("SELECT id, qualname, start_line FROM symbols WHERE file=? AND qualname=?", (file, name))
    if row is None:
        row = store.one("SELECT id, qualname, start_line FROM symbols WHERE file=? AND (name=? OR qualname LIKE ?) "
                        "ORDER BY kind='handler' LIMIT 1", (file, name.split(".")[-1], f"%.{name.split('.')[-1]}"))
    return row


def run_traced(store, root: Path, cmd: list, approved: bool, lang: str = "auto", timeout: int = 0, label: str | None = None) -> dict:
    root = Path(root).resolve()
    if not cmd:
        return {"error": "usage: ct runtime --yes -- <command...>"}
    if not approved:
        return {"status": "needs-approval", "command": shlex.join(cmd),
                "message": "Not executed. Runtime tracing runs repository code; ask the user, then re-run with --yes."}
    lang = _detect_lang(cmd) if lang == "auto" else lang
    timeout = timeout or int(load_config(root).get("tests", {}).get("timeout_seconds", 600))
    rid = time.strftime("R%Y%m%d-%H%M%S", time.gmtime())
    out_dir = data_dir(root) / "runs" / "runtime" / rid
    out_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["CT_TRACE_ROOT"] = str(root)
    env["CT_TRACE_OUT"] = str(out_dir / "events.json")
    if lang == "python":
        env["PYTHONPATH"] = str(HERE / "py") + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    else:
        env["NODE_OPTIONS"] = (env.get("NODE_OPTIONS", "") + f" --require {shlex.quote(str(HERE / 'node_hook.js'))}").strip()
    t0 = time.time()
    try:
        proc = subprocess.run(cmd, cwd=str(root), env=env, capture_output=True, timeout=timeout)
        code, status = proc.returncode, "completed"
        stdout, stderr = proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired as e:
        code, status = None, "timeout"
        stdout, stderr = (e.stdout or b"").decode("utf-8", "replace"), (e.stderr or b"").decode("utf-8", "replace")
    except FileNotFoundError as e:
        code, status, stdout, stderr = None, "error", "", str(e)
    events, dropped, procs = [], 0, 0
    for f in sorted(out_dir.glob("events.*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        procs += 1
        dropped += d.get("dropped", 0)
        for e in d.get("events", []):
            events.append({"t": e[0], "file": e[1], "name": e[2], "us": e[3] if lang == "node" else e[4],
                           "depth": e[4] if lang == "node" else None, "line": e[3] if lang == "python" else None,
                           "error": e[5] if lang == "node" and len(e) > 5 else None, "pid": d.get("pid")})
    calls = Counter((e["file"], e["name"]) for e in events if e["t"] == "c")
    throws = Counter((e["file"], e["name"]) for e in events if e["t"] == "x")
    mapped, unmapped = [], 0
    cache = {}
    for (file, name), n in calls.most_common():
        row = cache.setdefault((file, name), _map_symbol(store, file, name))
        if row:
            mapped.append({"symbol_id": row["id"], "qualname": row["qualname"], "file": file, "line": row["start_line"],
                           "calls": n, "throws": throws.get((file, name), 0)})
        else:
            unmapped += 1
    seq = []
    for e in events[:5000]:
        row = cache.get((e["file"], e["name"])) or _map_symbol(store, e["file"], e["name"])
        seq.append({**e, "symbol_id": row["id"] if row else None})
    result = {"id": rid, "label": label, "lang": lang, "command": shlex.join(cmd), "status": status, "exit_code": code,
              "duration_s": round(time.time() - t0, 2), "processes_traced": procs, "events_total": len(events),
              "events_dropped": dropped, "functions_observed": len(calls), "mapped_symbols": mapped[:500],
              "unmapped_functions": unmapped, "sequence": seq, "git_commit": git_info(root).get("commit"),
              "verification": "runtime-observed" if events else "no events captured",
              "limitations": ("Python: all repo functions via sys.setprofile." if lang == "python" else
                              "Node: only functions reached through repo module exports (CommonJS); ESM and internal calls are not observed."),
              "stdout_tail": stdout[-2000:], "stderr_tail": stderr[-2000:]}
    (out_dir / "trace.json").write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    for f in out_dir.glob("events.*.json"):
        f.unlink()
    brief = {k: v for k, v in result.items() if k != "sequence"}
    brief["mapped_symbols"] = mapped[:40]
    brief["saved_to"] = str((out_dir / "trace.json").relative_to(root))
    return brief


def list_traces(root: Path) -> list:
    out = []
    for p in sorted((data_dir(root) / "runs" / "runtime").glob("*/trace.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out
