"""Common, language-independent fact structures emitted by parsers."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field


@dataclass
class Symbol:
    name: str
    qualname: str
    kind: str  # function|method|class|interface|type|enum|handler|variable
    start: int
    end: int
    signature: str = ""
    exported: bool = False
    parent: str | None = None
    body_hash: str = ""


@dataclass
class Import:
    line: int
    module: str
    names: list  # list of [imported_name, local_name]; imported '*' = namespace, 'default' = default export
    kind: str  # esm|cjs|py|dynamic
    reexport: bool = False


@dataclass
class Call:
    line: int
    caller: str | None
    expr: str
    name: str
    receiver: str | None


@dataclass
class Route:
    line: int
    framework: str
    method: str  # GET/POST/... USE for mounts, ALL
    path: str
    handlers: list  # handler expressions or synthetic symbol qualnames
    router: str = ""  # variable the route is registered on (app/router)
    kind: str = "route"  # route|mount|middleware


@dataclass
class Control:
    line: int
    symbol: str | None
    kind: str  # if|else|return|throw|raise|catch|respond|next-error|assert|loop
    text: str
    outcome: str = "neutral"  # success|failure|neutral


@dataclass
class FileFacts:
    parser: str = "none"  # python-ast|tree-sitter|heuristic|none
    symbols: list = field(default_factory=list)
    imports: list = field(default_factory=list)
    calls: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    controls: list = field(default_factory=list)
    env_vars: list = field(default_factory=list)  # [line, name]
    exports: list = field(default_factory=list)  # [exported_name, local_qualname]
    entry_reasons: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


FAILURE_STATUS = re.compile(r"\b(4\d\d|5\d\d)\b")


def classify_outcome(kind: str, text: str) -> str:
    t = text.lower()
    if kind in ("throw", "raise", "next-error"):
        return "failure"
    if FAILURE_STATUS.search(text) and kind in ("return", "respond"):
        return "failure"
    if kind == "return" and any(k in t for k in ("abort(", "httpexception", "unauthorized", "forbidden",
                                                   "error(", "not found", "invalid")):
        return "failure"
    if kind in ("return", "respond"):
        return "success"
    if kind == "catch":
        return "failure"
    return "neutral"


def short(text: str, limit: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def body_hash(text: str) -> str:
    return hashlib.sha1(" ".join(text.split()).encode("utf-8", "replace")).hexdigest()[:16]
