"""Codebase Tutor runtime tracer for Python (loaded via PYTHONPATH). Records call/return of repo functions only."""
import atexit
import json
import os
import sys
import threading
import time

_ROOT = os.path.realpath(os.environ.get("CT_TRACE_ROOT", "")) + os.sep
_OUT = os.environ.get("CT_TRACE_OUT", "")
_MAX = int(os.environ.get("CT_TRACE_MAX", "200000"))
_HERE = os.path.dirname(os.path.realpath(__file__))
_events = []
_state = {"dropped": 0}
_t0 = time.perf_counter()
_skip = (os.path.join(_ROOT, ".codebase-tutor"),)
_cache = {}


def _relpath(fn):
    r = _cache.get(fn)
    if r is None:
        real = os.path.realpath(fn) if fn and not fn.startswith("<") else ""
        ok = real.startswith(_ROOT) and "site-packages" not in real and not real.startswith(_skip) and not real.startswith(_HERE)
        r = os.path.relpath(real, _ROOT).replace(os.sep, "/") if ok else ""
        _cache[fn] = r
    return r


def _prof(frame, event, arg):
    if event != "call" and event != "return":
        return
    rel = _relpath(frame.f_code.co_filename)
    if not rel:
        return
    if len(_events) >= _MAX:
        _state["dropped"] += 1
        return
    co = frame.f_code
    _events.append([event[0], rel, getattr(co, "co_qualname", co.co_name), frame.f_lineno,
                    int((time.perf_counter() - _t0) * 1e6), threading.get_ident() % 100000])


if _OUT and _ROOT != os.sep:
    sys.setprofile(_prof)
    threading.setprofile(_prof)

    @atexit.register
    def _dump():
        sys.setprofile(None)
        out = _OUT.replace(".json", f".{os.getpid()}.json")
        try:
            with open(out, "w", encoding="utf-8") as fh:
                json.dump({"lang": "python", "pid": os.getpid(), "argv": sys.argv[:6], "events": _events,
                           "dropped": _state["dropped"]}, fh)
        except OSError:
            pass

# Chain to any other sitecustomize that ours shadows.
try:
    import importlib.machinery
    import importlib.util
    _paths = [p for p in sys.path if p and os.path.realpath(p) != _HERE]
    _spec = importlib.machinery.PathFinder.find_spec("sitecustomize", _paths)
    if _spec and _spec.origin and os.path.realpath(os.path.dirname(_spec.origin)) != _HERE:
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
except Exception:
    pass
