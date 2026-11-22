"""Agent-authored explanations: schema validation, evidence verification, storage (language-separated content)."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .config import data_dir
from .evidence import VERIFICATION_LEVELS, EvidenceError, check_ref, evidence_id, read_lines, register, text_hash

LEVELS = {"beginner", "developer", "deep-dive", "contribution"}
TYPES = {"explanation", "flow-notes", "concept", "contribution-plan", "review"}
ID_RX = re.compile(r"^[a-z0-9][a-z0-9\-_.]{0,80}$")


def _texts(obj) -> list:
    """All localized-text dicts inside an object (for language coverage)."""
    out = []
    if isinstance(obj, dict):
        if obj and all(isinstance(k, str) and len(k) <= 10 and isinstance(v, (str, list)) for k, v in obj.items()) and "en" in obj:
            out.append(obj)
        else:
            for v in obj.values():
                out += _texts(v)
    elif isinstance(obj, list):
        for v in obj:
            out += _texts(v)
    return out


def _range(spec) -> tuple[int, int]:
    if isinstance(spec, int):
        return spec, spec
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        return int(spec[0]), int(spec[1])
    s = str(spec)
    if "-" in s:
        a, b = s.split("-", 1)
        return int(a), int(b)
    return int(s), int(s)


def _check_evidence(root: Path, ev: dict, where: str, errors: list, lines_cache: dict):
    f = ev.get("file")
    if not f or "lines" not in ev:
        errors.append(f"{where}: evidence needs 'file' and 'lines'")
        return
    try:
        s, e = _range(ev["lines"])
    except (TypeError, ValueError):
        errors.append(f"{where}: bad 'lines' value {ev.get('lines')!r}")
        return
    if f not in lines_cache:
        try:
            lines_cache[f] = read_lines(root, f)
        except EvidenceError as ex:
            errors.append(f"{where}: {ex}")
            lines_cache[f] = None
    lines = lines_cache[f]
    if lines is None:
        return
    if s < 1 or e < s or e > len(lines):
        errors.append(f"{where}: lines {s}-{e} out of range for {f} ({len(lines)} lines)")
        return
    for h in str(ev.get("highlight", "")).split(","):
        if h.strip():
            hs, he = _range(h.strip())
            if hs < s or he > e:
                errors.append(f"{where}: highlight {h} outside evidence range {s}-{e}")
    th = text_hash(lines[s - 1:e])
    if ev.get("text_hash") and ev["text_hash"] != th:
        errors.append(f"{where}: text_hash mismatch for {f}:{s}-{e} (code changed since the claim was written)")
    ev["lines"] = f"{s}-{e}" if s != e else str(s)
    ev["text_hash"] = th
    ev["id"] = evidence_id(f, s, e, th)
    if ev.get("status") and ev["status"] not in VERIFICATION_LEVELS:
        errors.append(f"{where}: status must be one of {VERIFICATION_LEVELS}")


def validate(root: Path, doc: dict) -> tuple[dict, list, list]:
    errors, warnings = [], []
    if not isinstance(doc, dict):
        return doc, ["top-level JSON must be an object"], []
    if not ID_RX.match(str(doc.get("id", ""))):
        errors.append("id must be lowercase letters/digits/-/_ (max 80 chars)")
    doc.setdefault("type", "explanation")
    if doc["type"] not in TYPES:
        errors.append(f"type must be one of {sorted(TYPES)}")
    if not isinstance(doc.get("title"), dict) or not doc["title"].get("en"):
        errors.append("title must be an object with at least an 'en' entry")
    if doc.get("level") and doc["level"] not in LEVELS:
        errors.append(f"level must be one of {sorted(LEVELS)}")
    if doc["type"] == "flow-notes" and not doc.get("flow"):
        errors.append("flow-notes require a 'flow' id (from `ct trace`)")
    cache = {}
    n_ev = 0

    def walk(obj, where):
        nonlocal n_ev
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "evidence":
                    if not isinstance(v, list):
                        errors.append(f"{where}.evidence must be a list")
                        continue
                    for i, ev in enumerate(v):
                        n_ev += 1
                        _check_evidence(root, ev, f"{where}.evidence[{i}]", errors, cache)
                else:
                    walk(v, f"{where}.{k}")
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{where}[{i}]")

    walk(doc, doc.get("id", "doc"))
    for i, sec in enumerate(doc.get("sections", []) or []):
        if not sec.get("evidence") and sec.get("status") not in ("not-verified", None):
            warnings.append(f"section[{i}] claims status '{sec.get('status')}' without evidence")
        if not sec.get("evidence") and sec.get("kind") not in ("concept", "analogy", "general"):
            warnings.append(f"section[{i}] has no evidence; mark kind 'concept'/'general' or status 'not-verified' if intended")
    for i, c in enumerate(doc.get("claims", []) or []):
        if not c.get("evidence"):
            if c.get("status") not in ("not-verified", "partially-verified"):
                errors.append(f"claims[{i}] has no evidence; give evidence or mark status 'not-verified'")
    langs = set()
    for t in _texts(doc):
        langs |= set(t)
    doc["languages"] = sorted(langs)
    doc["evidence_count"] = n_ev
    return doc, errors, warnings


def add(store, root: Path, path: Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"ok": False, "errors": [f"cannot read JSON: {e}"]}
    doc, errors, warnings = validate(root, doc)
    if errors:
        return {"ok": False, "errors": errors, "warnings": warnings, "stored": False}
    doc["validated_at"] = time.time()
    doc["snapshot"] = store.get_meta("last_snapshot")
    out = data_dir(root) / "knowledge" / "explanations" / f"{doc['id']}.json"
    out.write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")

    def reg(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "evidence" and isinstance(v, list):
                    for ev in v:
                        s, e = _range(ev["lines"])
                        fh = store.one("SELECT hash FROM files WHERE path=?", (ev["file"],))
                        register(store, root, {"id": ev["id"], "file": ev["file"], "start": s, "end": e, "text_hash": ev["text_hash"]},
                                 fh[0] if fh else None)
                else:
                    reg(v)
        elif isinstance(obj, list):
            for v in obj:
                reg(v)
    reg(doc)
    store.commit()
    return {"ok": True, "stored": str(out.relative_to(root)), "languages": doc["languages"], "evidence_refs": doc["evidence_count"],
            "warnings": warnings}


def validate_file(root: Path, path: Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"ok": False, "errors": [f"cannot read JSON: {e}"]}
    _, errors, warnings = validate(root, doc)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def load_all(root: Path) -> list:
    out = []
    for p in sorted((data_dir(root) / "knowledge" / "explanations").glob("*.json")):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def list_items(root: Path) -> dict:
    return {"items": [{"id": d.get("id"), "type": d.get("type"), "title": d.get("title", {}).get("en"), "level": d.get("level"),
                       "languages": d.get("languages"), "evidence_refs": d.get("evidence_count")} for d in load_all(root)]}


def evidence_status(root: Path, doc: dict) -> dict:
    """Annotate each evidence ref with current status (valid / moved / stale / missing)."""
    counts = {}

    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "evidence" and isinstance(v, list):
                    for ev in v:
                        try:
                            s, e = _range(ev["lines"])
                        except (KeyError, ValueError, TypeError):
                            continue
                        res = check_ref(root, ev["file"], s, e, ev.get("text_hash"))
                        ev["current_status"] = res["status"]
                        if res["relocated"]:
                            ev["relocated_lines"] = f"{res['relocated'][0]}-{res['relocated'][1]}"
                        counts[res["status"]] = counts.get(res["status"], 0) + 1
                else:
                    walk(v)
        elif isinstance(obj, list):
            for v in obj:
                walk(v)
    walk(doc)
    return counts


def verify_all(store, root: Path) -> list:
    out = []
    for d in load_all(root):
        out.append({"id": d.get("id"), "evidence": evidence_status(root, d)})
    return out
