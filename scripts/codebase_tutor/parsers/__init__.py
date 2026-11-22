"""Language parsers producing FileFacts."""
from __future__ import annotations

from .base import FileFacts


def parse_file(path: str, lang: str, text: str) -> FileFacts:
    if lang == "python":
        from .python_parser import parse_python
        return parse_python(path, text)
    if lang in ("javascript", "typescript", "tsx"):
        from .js_parser import parse_js
        return parse_js(path, lang, text)
    facts = FileFacts(parser="none")
    return facts
