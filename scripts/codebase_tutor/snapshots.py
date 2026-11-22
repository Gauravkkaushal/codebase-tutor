"""Repository snapshots: manifests + content-addressed blobs + git metadata."""
from __future__ import annotations

import gzip
import json
import subprocess
import time
from pathlib import Path

from . import DATA_DIR
from .config import data_dir

BLOB_ROLES = {"source", "test", "config", "doc", "asset", "data"}


def git(root: Path, *args, timeout=60) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.decode("utf-8", "replace")


def git_info(root: Path) -> dict:
    inside = git(root, "rev-parse", "--is-inside-work-tree")
    if not inside or inside.strip() != "true":
        return {"is_repo": False}
    commit = (git(root, "rev-parse", "HEAD") or "").strip() or None
    branch = (git(root, "rev-parse", "--abbrev-ref", "HEAD") or "").strip() or None
    status = git(root, "status", "--porcelain", "-uall") or ""
    dirty = []
    for ln in status.splitlines():
        if len(ln) > 3:
            p = ln[3:]
            if " -> " in p:
                p = p.split(" -> ", 1)[1]
            p = p.strip('"')
            if not p.startswith(DATA_DIR + "/") and p != DATA_DIR + "/":
                dirty.append(p)
    shallow = (git(root, "rev-parse", "--is-shallow-repository") or "").strip() == "true"
    remote = (git(root, "config", "--get", "remote.origin.url") or "").strip() or None
    return {"is_repo": True, "commit": commit, "branch": branch, "dirty_files": dirty[:500], "dirty": bool(dirty),
            "shallow": shallow, "remote": remote}


def _blob_path(root: Path, h: str) -> Path:
    return data_dir(root) / "snapshots" / "blobs" / h[:2] / (h + ".gz")


def blob_store_size(root: Path) -> int:
    base = data_dir(root) / "snapshots" / "blobs"
    return sum(p.stat().st_size for p in base.rglob("*.gz")) if base.exists() else 0


def create_snapshot(root: Path, store, inventory, cfg: dict, note: str = "") -> dict:
    root = Path(root)
    info = git_info(root)
    manifest = {f.path: f.hash for f in inventory.files if f.role not in ("binary", "secret")}
    stored, skipped = 0, 0
    if cfg.get("snapshot", {}).get("store_blobs", True):
        budget = int(cfg["snapshot"].get("max_blob_store_mb", 500)) * 1024 * 1024
        used = blob_store_size(root)
        for f in inventory.files:
            if f.role not in BLOB_ROLES or f.note == "too-large" or not f.hash:
                continue
            bp = _blob_path(root, f.hash)
            if bp.exists():
                continue
            if used + f.size > budget:
                skipped += 1
                continue
            try:
                data = (root / f.path).read_bytes()
            except OSError:
                continue
            bp.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(bp, "wb", compresslevel=6) as fh:
                fh.write(data)
            used += bp.stat().st_size
            stored += 1
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    sid = f"S{ts}" + (f"-{info['commit'][:7]}" if info.get("commit") else "")
    n = 1
    while store.one("SELECT 1 FROM snapshots WHERE id=?", (sid,)):
        n += 1
        sid = f"{sid.split('~')[0]}~{n}"
    mpath = data_dir(root) / "snapshots" / "manifests" / f"{sid}.json.gz"
    with gzip.open(mpath, "wt", encoding="utf-8") as fh:
        json.dump({"id": sid, "git": info, "files": manifest}, fh)
    store.db.execute("INSERT INTO snapshots(id,created_at,git_commit,branch,dirty,files,manifest,note) VALUES(?,?,?,?,?,?,?,?)",
                     (sid, time.time(), info.get("commit"), info.get("branch"), int(bool(info.get("dirty"))), len(manifest),
                      str(mpath.relative_to(data_dir(root))), json.dumps({"note": note, "dirty_files": info.get("dirty_files", [])})))
    store.set_meta("last_snapshot", sid)
    store.commit()
    return {"id": sid, "files": len(manifest), "blobs_stored": stored, "blobs_skipped_budget": skipped, "git": info}


def list_snapshots(store) -> list:
    return [dict(r) for r in store.q("SELECT id, created_at, git_commit, branch, dirty, files FROM snapshots ORDER BY created_at")]


def load_manifest(root: Path, store, sid: str) -> dict:
    row = store.one("SELECT manifest FROM snapshots WHERE id=?", (sid,))
    if not row:
        raise KeyError(f"unknown snapshot {sid}")
    with gzip.open(data_dir(root) / row["manifest"], "rt", encoding="utf-8") as fh:
        return json.load(fh)


def read_blob(root: Path, h: str) -> bytes | None:
    bp = _blob_path(root, h)
    if bp.exists():
        with gzip.open(bp, "rb") as fh:
            return fh.read()
    return None


def old_content(root: Path, manifest: dict, path: str) -> tuple[str | None, str]:
    """Content of `path` as of a snapshot manifest. Returns (text|None, source)."""
    h = manifest["files"].get(path)
    if h is None:
        return None, "absent"
    data = read_blob(root, h)
    if data is not None:
        return data.decode("utf-8", "replace"), "blob"
    g = manifest.get("git") or {}
    if g.get("commit") and path not in set(g.get("dirty_files") or []):
        txt = git(root, "show", f"{g['commit']}:{path}")
        if txt is not None:
            return txt, "git"
    return None, "unavailable"


def git_ref_manifest(root: Path, ref: str) -> dict | None:
    """Build a pseudo-manifest for a git ref (content fetched lazily via git show)."""
    commit = (git(root, "rev-parse", ref) or "").strip()
    if not commit:
        return None
    listing = git(root, "ls-tree", "-r", commit) or ""
    files = {}
    for ln in listing.splitlines():
        meta, _, path = ln.partition("\t")
        parts = meta.split()
        if len(parts) == 3 and parts[1] == "blob":
            files[path] = "git:" + parts[2]
    return {"id": f"git:{ref}", "git": {"commit": commit, "dirty_files": []}, "files": files, "ref": ref}


def ref_content(root: Path, manifest: dict, path: str) -> tuple[str | None, str]:
    if manifest.get("ref"):
        if path not in manifest["files"]:
            return None, "absent"
        txt = git(root, "show", f"{manifest['git']['commit']}:{path}")
        return (txt, "git") if txt is not None else (None, "unavailable")
    return old_content(root, manifest, path)


def fresh_signature(root: Path) -> str | None:
    """Cheap fingerprint of the working tree state (git only): HEAD + dirty files with size/mtime."""
    head = git(root, "rev-parse", "HEAD")
    if head is None:
        return None
    status = git(root, "status", "--porcelain", "-uall") or ""
    parts = [head.strip()]
    for ln in sorted(status.splitlines()):
        p = ln[3:].split(" -> ")[-1].strip('"')
        if p.startswith(DATA_DIR + "/"):
            continue
        try:
            st = (Path(root) / p).stat()
            parts.append(f"{ln[:2]}{p}:{st.st_size}:{st.st_mtime_ns}")
        except OSError:
            parts.append(f"{ln[:2]}{p}:gone")
    import hashlib
    return hashlib.sha1("\n".join(parts).encode()).hexdigest()
