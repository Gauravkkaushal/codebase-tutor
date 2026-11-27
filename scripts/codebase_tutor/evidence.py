"""Evidence engine: exact excerpts, highlights, redaction, hash-checked references, citation checks."""
from __future__ import annotations

import hashlib
import re
import time
from pathlib import Path

from .inventory import classify

SECRET_PATTERNS = [
    (re.compile(r"AKIA[0-9A-Z]{16}"), "«redacted-aws-key»"),
    (re.compile(r"\bghp_[A-Za-z0-9]{36}\b"), "«redacted-token»"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}\b"), "«redacted-key»"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b"), "«redacted-token»"),
]
ASSIGN_SECRET = re.compile(
    r"""(?i)((?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?key|private[_-]?key|client[_-]?secret)\w*["']?\s*[:=]\s*)(["'])([^"'\n]{6,})\2""")
URL_QUERY_SECRET = re.compile(
    r"""(?i)([?&](?:token|access_token|refresh_token|api_key|apikey|secret|password|passwd|pwd|auth|key|signature|sig|x-amz-credential|x-amz-signature)=)([^&#\s"'`]+)"""
)
VERIFICATION_LEVELS = ("verified-source", "structurally-inferred", "test-verified", "runtime-observed",
                       "partially-verified", "not-verified")


class EvidenceError(ValueError):
    pass


def text_hash(lines: list) -> str:
    return hashlib.sha1("\n".join(lines).encode("utf-8", "replace")).hexdigest()[:16]


def evidence_id(path: str, start: int, end: int, thash: str) -> str:
    return "E" + hashlib.sha1(f"{path}:{start}-{end}:{thash}".encode()).hexdigest()[:12]


def redact_line(line: str) -> tuple[str, int]:
    n = 0
    for rx, rep in SECRET_PATTERNS:
        line, k = rx.subn(rep, line)
        n += k
    line, k = ASSIGN_SECRET.subn(lambda m: f"{m.group(1)}{m.group(2)}«redacted»{m.group(2)}", line)
    n += k
    line, k = URL_QUERY_SECRET.subn(r"\1«redacted»", line)
    return line, n + k


def safe_path(root: Path, path: str) -> Path:
    root = Path(root).resolve()
    p = (root / path).resolve()
    if root not in p.parents and p != root:
        raise EvidenceError(f"path escapes repository: {path}")
    if not p.is_file():
        raise EvidenceError(f"file not found: {path}")
    req_rel = path.replace("\\", "/")
    while req_rel.startswith("./"):
        req_rel = req_rel[2:]
    rel = p.relative_to(root).as_posix()
    for candidate in (req_rel, rel):
        _, role = classify(candidate, 0)
        if role in ("secret", "binary"):
            raise EvidenceError(f"refusing to read {role} file: {path}")
    return p


def read_lines(root: Path, path: str) -> list:
    data = safe_path(root, path).read_bytes()
    if b"\0" in data[:8192]:
        raise EvidenceError(f"binary file: {path}")
    return data.decode("utf-8", "replace").splitlines()


def excerpt(root: Path, path: str, start: int, end: int | None = None, highlight=None, context: int = 0,
            redact: bool = True) -> dict:
    lines = read_lines(root, path)
    end = end or start
    if start < 1 or end < start or end > len(lines):
        raise EvidenceError(f"line range {start}-{end} out of bounds for {path} ({len(lines)} lines)")
    hl = set(highlight or [])
    s, e = max(1, start - context), min(len(lines), end + context)
    out, red = [], 0
    in_key = False
    for n in range(s, e + 1):
        raw = lines[n - 1]
        if redact:
            if "-----BEGIN" in raw and "PRIVATE KEY" in raw:
                in_key = True
            if in_key:
                shown, k = "«redacted private key material»", 1
                if "-----END" in raw:
                    in_key = False
            else:
                shown, k = redact_line(raw)
            red += k
        else:
            shown = raw
        out.append({"n": n, "text": shown, "hl": n in hl, "in_range": start <= n <= end})
    th = text_hash(lines[start - 1:end])
    return {"id": evidence_id(path, start, end, th), "file": path, "start": start, "end": end, "shown_start": s,
            "shown_end": e, "highlight": sorted(hl), "lines": out, "text_hash": th, "redactions": red,
            "total_lines": len(lines)}


def format_excerpt(ev: dict, symbol: str | None = None) -> str:
    width = len(str(ev["shown_end"]))
    head = f"File: {ev['file']}  lines {ev['start']}-{ev['end']}" + (f"  symbol: {symbol}" if symbol else "")
    body = []
    for ln in ev["lines"]:
        mark = "▶" if ln["hl"] else (" " if ln["in_range"] else "·")
        body.append(f"{mark} {str(ln['n']).rjust(width)}  {ln['text']}")
    tail = f"(evidence {ev['id']}, text-hash {ev['text_hash']}" + (f", {ev['redactions']} redaction(s)" if ev["redactions"] else "") + ")"
    return "\n".join([head, *body, tail])


def register(store, root: Path, ev: dict, file_hash: str | None = None):
    store.db.execute("INSERT OR REPLACE INTO evidence(id,file,start_line,end_line,text_hash,file_hash,created_at,status)"
                     " VALUES(?,?,?,?,?,?,?,?)", (ev["id"], ev["file"], ev["start"], ev["end"], ev["text_hash"],
                                                   file_hash, time.time(), "valid"))


def check_ref(root: Path, path: str, start: int, end: int, expected_hash: str | None) -> dict:
    """Return {'status': valid|stale|missing|out-of-range, 'relocated': (s,e)|None}."""
    try:
        lines = read_lines(root, path)
    except EvidenceError:
        return {"status": "missing", "relocated": None}
    if end > len(lines) or start < 1:
        status = "out-of-range"
    elif expected_hash is None or text_hash(lines[start - 1:end]) == expected_hash:
        return {"status": "valid", "relocated": None}
    else:
        status = "stale"
    if expected_hash:
        span = end - start + 1
        for s in range(1, len(lines) - span + 2):
            if text_hash(lines[s - 1:s - 1 + span]) == expected_hash:
                return {"status": "moved", "relocated": [s, s + span - 1]}
    return {"status": status, "relocated": None}


def refresh_evidence_status(root: Path, store) -> dict:
    counts = {}
    rows = store.q("SELECT id, file, start_line, end_line, text_hash FROM evidence")
    for r in rows:
        res = check_ref(root, r["file"], r["start_line"], r["end_line"], r["text_hash"])
        store.db.execute("UPDATE evidence SET status=? WHERE id=?", (res["status"], r["id"]))
        counts[res["status"]] = counts.get(res["status"], 0) + 1
    store.commit()
    return counts


CITATION = re.compile(r"(?<![\w/.-])((?:[\w.@-]+/)*[\w.@-]+\.[A-Za-z0-9]{1,6}):(\d+)(?:-(\d+))?")


def verify_citations(root: Path, text: str) -> list:
    """Check `path:line` / `path:start-end` citations in prose. Returns list of findings."""
    findings = []
    for m in CITATION.finditer(text):
        path, s, e = m.group(1), int(m.group(2)), int(m.group(3) or m.group(2))
        try:
            lines = read_lines(root, path)
        except EvidenceError as ex:
            findings.append({"citation": m.group(0), "status": "missing", "detail": str(ex)})
            continue
        if s < 1 or e < s or e > len(lines):
            findings.append({"citation": m.group(0), "status": "out-of-range", "detail": f"file has {len(lines)} lines"})
        else:
            findings.append({"citation": m.group(0), "status": "ok", "first_line": lines[s - 1].strip()[:120]})
    return findings
