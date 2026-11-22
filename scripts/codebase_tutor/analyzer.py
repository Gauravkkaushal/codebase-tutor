"""Scan orchestration: incremental, resumable, parallel parsing into the knowledge store."""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from .config import data_dir, init_data_dir, load_config
from .detect import detect
from .inventory import PARSEABLE_LANGS, read_text, scan_inventory
from .parsers import parse_file
from .resolve import resolve_all
from .snapshots import create_snapshot, git_info
from .store import Store

PARSE_ROLES = {"source", "test"}


def open_store(root: Path) -> Store:
    return Store(data_dir(root) / "knowledge" / "index.db")


def _parse_job(args):
    root, path, lang = args
    try:
        text = read_text(Path(root) / path)
    except (OSError, ValueError) as e:
        return path, None, 0, f"read error: {e}"
    try:
        facts = parse_file(path, lang, text)
    except Exception as e:  # never let one file kill the scan
        return path, None, text.count("\n") + 1, f"parser exception: {type(e).__name__}: {e}"
    return path, facts.to_dict(), text.count("\n") + (0 if text.endswith("\n") or not text else 1), None


def _count_lines(path: Path) -> int:
    try:
        with open(path, "rb") as fh:
            return sum(chunk.count(b"\n") for chunk in iter(lambda: fh.read(1 << 16), b""))
    except OSError:
        return 0


def scan(root: Path, full: bool = False, jobs: int = 0, quiet: bool = False, note: str = "") -> dict:
    t0 = time.time()
    root = Path(root).resolve()
    init_data_dir(root)
    cfg = load_config(root)
    store = open_store(root)
    prev = store.file_index()
    inv = scan_inventory(root, cfg, previous={p: (v[0], v[1], v[2]) for p, v in prev.items()})
    current = inv.by_path()

    added = sorted(p for p in current if p not in prev)
    modified = sorted(p for p in current if p in prev and (prev[p][2] != current[p].hash or prev[p][3] == "pending"))
    deleted = sorted(p for p in prev if p not in current)
    targets = sorted(current) if full else added + modified

    def log(msg):
        if not quiet:
            print(msg, file=sys.stderr, flush=True)

    log(f"[ct] inventory: {len(current)} files ({'git' if inv.used_git else 'walk'}); "
        f"+{len(added)} ~{len(modified)} -{len(deleted)}; analysing {len(targets)}")

    for p in deleted:
        store.delete_file(p)

    parse_jobs, meta_only = [], []
    for p in targets:
        e = current[p]
        if e.lang in PARSEABLE_LANGS and e.role in PARSE_ROLES and e.note != "too-large":
            parse_jobs.append((str(root), p, e.lang))
        else:
            meta_only.append(e)

    for e in meta_only:
        store.delete_file_facts(e.path)
        if e.role in ("binary", "secret"):
            status, lines = e.role, 0
        elif e.note == "too-large":
            status, lines = "skipped-large", 0
        elif e.role == "generated":
            status, lines = "skipped-generated", 0
        else:
            status, lines = "inventory", _count_lines(root / e.path)
        store.upsert_file(e, lines, status, "none", e.note or None, [])
    store.commit()

    n_jobs = jobs or int(cfg.get("parse_jobs") or 0) or min(8, os.cpu_count() or 2)
    done = 0
    errors = 0

    def handle(result):
        nonlocal done, errors
        path, facts, lines, err = result
        e = current[path]
        store.delete_file_facts(path)
        if facts is None:
            errors += 1
            store.upsert_file(e, lines, "failed", "none", err, [])
        else:
            status = "analyzed" if not facts["errors"] and facts["parser"] != "heuristic" else "partial"
            store.insert_facts(path, facts)
            store.upsert_file(e, lines, status, facts["parser"], "; ".join(facts["errors"]) or None, facts["entry_reasons"])
        done += 1
        if done % 200 == 0:
            store.commit()
            log(f"[ct] parsed {done}/{len(parse_jobs)}")

    if len(parse_jobs) > 150 and n_jobs > 1:
        with ProcessPoolExecutor(max_workers=n_jobs) as ex:
            for result in ex.map(_parse_job, parse_jobs, chunksize=16):
                handle(result)
    else:
        for job in parse_jobs:
            handle(_parse_job(job))
    store.commit()

    changed = bool(added or modified or deleted or full or store.get_meta("resolved_at") is None)
    resolution_stats = store.get_json("resolution_stats", {})
    if changed:
        log("[ct] resolving imports, calls, routes, test links")
        resolution_stats = resolve_all(root, store, set(current))
        store.set_json("resolution_stats", resolution_stats)
        store.set_meta("resolved_at", str(time.time()))
        store.set_json("detect", detect(root, sorted(current), store))
    store.set_json("excluded", {"dirs": inv.excluded_dirs, "files": inv.excluded_files})

    from .evidence import refresh_evidence_status
    stale = refresh_evidence_status(root, store)

    snap = None
    last = store.get_meta("last_snapshot")
    if changed or last is None:
        snap = create_snapshot(root, store, inv, cfg, note=note)
    store.set_meta("last_scan", str(time.time()))
    from .snapshots import fresh_signature
    sig = fresh_signature(root)
    if sig:
        store.set_meta("fresh_sig", sig)
    store.set_meta("repo_root", str(root))
    store.commit()
    summary = {
        "repo": str(root),
        "git": git_info(root),
        "files_total": len(current),
        "changes_since_last_scan": {"added": added[:200], "modified": modified[:200], "deleted": deleted[:200],
                                    "counts": {"added": len(added), "modified": len(modified), "deleted": len(deleted)}},
        "parsed_now": len(parse_jobs), "parse_failures": errors,
        "previous_snapshot": last, "snapshot": snap["id"] if snap else last,
        "coverage": coverage(store),
        "resolution": resolution_stats,
        "stale_evidence": stale,
        "seconds": round(time.time() - t0, 2),
        "first_scan": not prev,
    }
    store.set_json("last_scan_summary", {k: v for k, v in summary.items() if k != "changes_since_last_scan"} |
                   {"change_counts": summary["changes_since_last_scan"]["counts"]})
    store.commit()
    store.close()
    return summary


def coverage(store) -> dict:
    by_status = {r[0]: r[1] for r in store.q("SELECT status, COUNT(*) FROM files GROUP BY status")}
    by_lang = {}
    for r in store.q("SELECT lang, status, COUNT(*) AS n, SUM(lines) AS l FROM files WHERE role IN ('source','test') GROUP BY lang, status"):
        d = by_lang.setdefault(r["lang"], {"files": 0, "lines": 0, "analyzed": 0, "partial": 0, "inventory_only": 0, "failed": 0})
        d["files"] += r["n"]
        d["lines"] += r["l"] or 0
        key = {"analyzed": "analyzed", "partial": "partial", "failed": "failed"}.get(r["status"], "inventory_only")
        d[key] += r["n"]
    by_role = {r[0]: r[1] for r in store.q("SELECT role, COUNT(*) FROM files GROUP BY role")}
    excluded = store.get_json("excluded", {"dirs": {}, "files": {}})
    unresolved = store.one("SELECT COUNT(*) FROM calls WHERE resolution='unresolved'")[0]
    total_calls = store.one("SELECT COUNT(*) FROM calls")[0]
    return {"by_status": by_status, "by_language": by_lang, "by_role": by_role,
            "excluded_dirs": dict(list(excluded.get("dirs", {}).items())[:50]),
            "excluded_dir_count": len(excluded.get("dirs", {})),
            "calls_total": total_calls, "calls_unresolved": unresolved}


def ensure_fresh(root: Path) -> dict | None:
    """Re-scan incrementally if the git working tree changed since the last scan. Returns scan summary or None."""
    from .snapshots import fresh_signature
    root = Path(root).resolve()
    if not (data_dir(root) / "knowledge" / "index.db").exists():
        return None
    sig = fresh_signature(root)
    if sig is None:
        return None
    st = open_store(root)
    old = st.get_meta("fresh_sig")
    st.close()
    if old == sig:
        return None
    return scan(root, quiet=True, note="auto-refresh")
