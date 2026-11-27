"""System map: layered components + storages/external systems, built only from parsed imports and calls."""
from __future__ import annotations

import json
from collections import defaultdict

from .graph import layer_hint, module_of

# package root -> (kind, label). Kinds drive the icon and colour in the report.
STORAGE = {
    # databases / ORMs
    "mongoose": ("database", "MongoDB"), "mongodb": ("database", "MongoDB"), "pg": ("database", "PostgreSQL"),
    "postgres": ("database", "PostgreSQL"), "mysql": ("database", "MySQL"), "mysql2": ("database", "MySQL"),
    "sqlite3": ("database", "SQLite"), "better-sqlite3": ("database", "SQLite"), "sequelize": ("database", "SQL (Sequelize)"),
    "typeorm": ("database", "SQL (TypeORM)"), "@prisma/client": ("database", "Database (Prisma)"), "prisma": ("database", "Database (Prisma)"),
    "knex": ("database", "SQL (Knex)"), "drizzle-orm": ("database", "SQL (Drizzle)"), "sqlalchemy": ("database", "SQL (SQLAlchemy)"),
    "psycopg2": ("database", "PostgreSQL"), "psycopg": ("database", "PostgreSQL"), "pymongo": ("database", "MongoDB"),
    "peewee": ("database", "SQL (peewee)"), "flask_sqlalchemy": ("database", "SQL (SQLAlchemy)"),
    "mongoengine": ("database", "MongoDB"), "motor": ("database", "MongoDB"), "tortoise": ("database", "SQL (Tortoise)"), "django.db": ("database", "Database (Django ORM)"), "redis-om": ("database", "Redis (OM)"),
    "elasticsearch": ("database", "Elasticsearch"), "@supabase/supabase-js": ("database", "Supabase"), "firebase-admin": ("database", "Firebase"),
    # caches
    "redis": ("cache", "Redis"), "ioredis": ("cache", "Redis"), "memcached": ("cache", "Memcached"), "lru-cache": ("cache", "In-memory cache"),
    "node-cache": ("cache", "In-memory cache"), "cachetools": ("cache", "In-memory cache"), "functools.lru_cache": ("cache", "In-memory cache"),
    # sessions / cookies
    "express-session": ("session", "Session store"), "cookie-session": ("session", "Cookie session"), "cookie-parser": ("session", "Cookies"),
    "flask_login": ("session", "Session (Flask-Login)"), "django.contrib.sessions": ("session", "Session store"),
    # files
    "fs": ("files", "File system"), "fs/promises": ("files", "File system"), "node:fs": ("files", "File system"),
    "node:fs/promises": ("files", "File system"), "multer": ("files", "File uploads"), "shutil": ("files", "File system"),
    "pathlib": ("files", "File system"), "tempfile": ("files", "File system"), "glob": ("files", "File system"),
    # external HTTP APIs
    "axios": ("external", "External HTTP APIs"), "node-fetch": ("external", "External HTTP APIs"), "got": ("external", "External HTTP APIs"),
    "request": ("external", "External HTTP APIs"), "superagent": ("external", "External HTTP APIs"), "requests": ("external", "External HTTP APIs"),
    "httpx": ("external", "External HTTP APIs"), "urllib.request": ("external", "External HTTP APIs"), "aiohttp": ("external", "External HTTP APIs"),
    "stripe": ("external", "Stripe"), "openai": ("external", "OpenAI API"), "@anthropic-ai/sdk": ("external", "Anthropic API"),
    "anthropic": ("external", "Anthropic API"), "twilio": ("external", "Twilio"),
    # queues / events
    "amqplib": ("queue", "RabbitMQ"), "kafkajs": ("queue", "Kafka"), "bull": ("queue", "Job queue"), "bullmq": ("queue", "Job queue"),
    "celery": ("queue", "Celery queue"), "rq": ("queue", "Job queue"), "socket.io": ("queue", "WebSocket events"), "ws": ("queue", "WebSocket events"),
    # auth / crypto
    "bcrypt": ("auth", "Password hashing"), "bcryptjs": ("auth", "Password hashing"), "argon2": ("auth", "Password hashing"),
    "pbkdf2-password": ("auth", "Password hashing"), "jsonwebtoken": ("auth", "JWT tokens"), "jose": ("auth", "JWT tokens"),
    "passport": ("auth", "Passport auth"), "crypto": ("auth", "Crypto"), "node:crypto": ("auth", "Crypto"), "jwt": ("auth", "JWT tokens"),
    "hashlib": ("auth", "Crypto"), "passlib": ("auth", "Password hashing"), "werkzeug.security": ("auth", "Password hashing"),
    # email
    "nodemailer": ("email", "Email"), "@sendgrid/mail": ("email", "Email (SendGrid)"), "smtplib": ("email", "Email (SMTP)"),
    # cloud
    "aws-sdk": ("cloud", "AWS"), "boto3": ("cloud", "AWS"), "@google-cloud/storage": ("cloud", "Google Cloud Storage"),
    "firebase": ("cloud", "Firebase"),
    # templates / views
    "ejs": ("views", "Templates"), "pug": ("views", "Templates"), "hbs": ("views", "Templates"), "handlebars": ("views", "Templates"),
    "jinja2": ("views", "Templates"), "flask.render_template": ("views", "Templates"), "django.shortcuts": ("views", "Templates"),
}
LAYER_ORDER = ["client", "entry", "routing", "middleware", "handlers", "services", "data", "library", "storage"]
HINT_TO_LAYER = {"routing": "routing", "controller": "handlers", "view": "handlers", "middleware": "middleware",
                 "service": "services", "model": "data", "data": "data", "utility": "library", "library": "library",
                 "api": "routing", "ui": "client", "config": "services", "example": None, "test": None}


def classify_external(module: str):
    """Map an external module specifier to (kind, label) or None."""
    if not module:
        return None
    m = module.strip()
    if m in STORAGE:
        return STORAGE[m]
    if m.startswith("@aws-sdk/"):
        return ("cloud", "AWS")
    if m.startswith("@google-cloud/"):
        return ("cloud", "Google Cloud")
    parts = m.split("/")
    root = "/".join(parts[:2]) if m.startswith("@") else parts[0]
    if root in STORAGE:
        return STORAGE[root]
    dotted = m.split(".")
    for i in range(len(dotted), 0, -1):
        cand = ".".join(dotted[:i])
        if cand in STORAGE:
            return STORAGE[cand]
    return None


FRONTEND_EXT = (".jsx", ".tsx", ".vue", ".svelte")
FRONTEND_DIRS = {"frontend", "client", "web", "webapp", "ui", "front-end", "front"}


def pick_modules(src, max_modules: int) -> dict:
    """file -> module id. Folders two levels deep; small repos get split one level deeper while it stays readable."""
    out = {p: module_of(p, 2) for p in src}
    groups = defaultdict(list)
    for p in src:
        groups[out[p]].append(p)
    count = len(groups)
    for m, files in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        sub = {module_of(p, 3) for p in files}
        if len(sub) >= 2 and count - 1 + len(sub) <= int(max_modules * 0.75):
            for p in files:
                out[p] = module_of(p, 3)
            count += len(sub) - 1
    return out


def _module_edges(store, modmap) -> dict:
    edges = defaultdict(lambda: {"imports": 0, "calls": 0, "examples": []})
    for r in store.q("SELECT file, line, resolved FROM imports WHERE resolved IS NOT NULL"):
        a, b = modmap.get(r["file"]), modmap.get(r["resolved"])
        if a and b and a != b:
            e = edges[(a, b)]
            e["imports"] += 1
            if len(e["examples"]) < 3:
                e["examples"].append({"file": r["file"], "line": r["line"], "to": r["resolved"]})
    for r in store.q("SELECT c.file, s.file AS tfile FROM calls c JOIN symbols s ON s.id=c.resolved_id"):
        a, b = modmap.get(r["file"]), modmap.get(r["tfile"])
        if a and b and a != b:
            edges[(a, b)]["calls"] += 1
    return edges


def system_map(store, max_modules: int = 16, root=None) -> dict:
    from .access import AccessIndex
    roles = {r["path"]: (r["role"], r["lines"] or 0, r["entry"]) for r in store.q("SELECT path, role, lines, entry FROM files")}
    src = {p for p, v in roles.items() if v[0] == "source"}
    modmap = pick_modules(src, max_modules)
    acc = AccessIndex(store, root)
    http = [h for h in acc.http_calls() if h["file"] in src]
    http_ids = {h["id"] for h in http}
    route_files = defaultdict(int)
    for r in store.q("SELECT file FROM routes WHERE kind='route'"):
        if r["file"] in src:
            route_files[r["file"]] += 1
    handler_files = set()
    for r in store.q("SELECT handler_ids FROM routes WHERE kind='route'"):
        for hid in json.loads(r["handler_ids"] or "[]"):
            if hid:
                row = store.one("SELECT file FROM symbols WHERE id=?", (hid,))
                if row and row["file"] in src:
                    handler_files.add(row["file"])
    entry_files = {p for p, v in roles.items() if v[2] and p in src}

    # module activity: lines + routes + external use; keep the most relevant modules
    mod = defaultdict(lambda: {"files": 0, "lines": 0, "routes": 0, "entry": 0, "handlers": 0, "hints": defaultdict(int),
                               "file_list": [], "front": 0})
    for p in src:
        m = modmap[p]
        d = mod[m]
        d["files"] += 1
        d["lines"] += roles[p][1]
        d["routes"] += route_files.get(p, 0)
        d["entry"] += p in entry_files
        d["handlers"] += p in handler_files
        d["front"] += p.endswith(FRONTEND_EXT) or p.split("/")[0].lower() in FRONTEND_DIRS
        h = layer_hint(p)
        if h:
            d["hints"][h] += 1
        if len(d["file_list"]) < 40:
            d["file_list"].append(p)

    # storage usage per module from external imports + external calls (with evidence)
    usage = defaultdict(lambda: {"count": 0, "evidence": [], "modules": set()})  # (module, storage_label) -> ...
    storage_kind = {}
    covered = set()  # (module, label) whose package use is fully explained by in-repo HTTP calls
    for r in store.q("SELECT id, file, line, expr, external FROM calls WHERE resolution='external'"):
        if r["file"] not in src:
            continue
        if r["id"] in http_ids:
            cls = classify_external(r["external"])
            if cls:
                covered.add((modmap[r["file"]], cls[1]))
            continue
        cls = classify_external(r["external"])
        if not cls:
            continue
        key = (modmap[r["file"]], cls[1])
        storage_kind[cls[1]] = cls[0]
        u = usage[key]
        u["count"] += 1
        u["modules"].add(r["external"])
        if len(u["evidence"]) < 6:
            u["evidence"].append({"file": r["file"], "line": r["line"], "text": f"{r['expr']}()", "via": "call"})
    for r in store.q("SELECT file, line, module FROM imports WHERE external=1"):
        if r["file"] not in src:
            continue
        cls = classify_external(r["module"])
        if not cls:
            continue
        key = (modmap[r["file"]], cls[1])
        if key in covered and key not in usage:
            continue
        storage_kind[cls[1]] = cls[0]
        u = usage[key]
        u["modules"].add(r["module"])
        if u["count"] == 0 and len(u["evidence"]) < 6:
            u["evidence"].append({"file": r["file"], "line": r["line"], "text": f"import {r['module']}", "via": "import"})
    # Python: builtin open() is file I/O
    for r in store.q("SELECT c.file, c.line, c.expr FROM calls c JOIN files f ON f.path=c.file "
                     "WHERE f.lang='python' AND c.name='open' AND c.receiver IS NULL AND c.resolution='builtin' LIMIT 400"):
        if r["file"] in src:
            key = (modmap[r["file"]], "File system")
            storage_kind["File system"] = "files"
            u = usage[key]
            u["count"] += 1
            u["modules"].add("open()")
            if len(u["evidence"]) < 6:
                u["evidence"].append({"file": r["file"], "line": r["line"], "text": "open()", "via": "call"})

    # database reads/writes through local model files (Mongoose models, db handles) — structurally inferred
    db_ops = defaultdict(lambda: defaultdict(int))
    for r in store.q("SELECT file, line, expr, name, receiver FROM calls WHERE resolved_id IS NULL AND "
                     "(resolution IS NULL OR resolution NOT IN ('external','builtin')) AND receiver IS NOT NULL"):
        if r["file"] not in src or r["file"] in acc.model_files:
            continue
        dbx = acc.classify_call(r["file"], r["expr"], r["name"], r["receiver"])
        if not dbx:
            continue
        key = (modmap[r["file"]], dbx["label"])
        storage_kind[dbx["label"]] = "database"
        u = usage[key]
        u["count"] += 1
        u["modules"].add(dbx["package"])
        u.setdefault("inferred", 0)
        u["inferred"] += 1
        db_ops[key][dbx["op"]] += 1
        if len(u["evidence"]) < 6:
            u["evidence"].append({"file": r["file"], "line": r["line"], "text": f"{r['expr']}() — {dbx['op']} via {dbx['model']}",
                                  "via": "model"})

    mg_edges = _module_edges(store, modmap)
    indeg, outdeg = defaultdict(int), defaultdict(int)
    for (a, b), e in mg_edges.items():
        indeg[b] += e["imports"] + e["calls"]
        outdeg[a] += e["imports"] + e["calls"]
    http_by_mod = defaultdict(lambda: {"n": 0, "evidence": [], "routes": set()})
    for h in http:
        tm = modmap.get(h["route"]["file"])
        if not tm:
            continue
        x = http_by_mod[(modmap[h["file"]], tm)]
        x["n"] += 1
        x["routes"].add(f"{h['method']} {h['route']['full_path'] or h['route']['path']}")
        if len(x["evidence"]) < 6:
            x["evidence"].append({"file": h["file"], "line": h["line"], "text": f"{h['expr']}('{h['url']}')", "via": "http-call"})
            x["evidence"].append({"file": h["route"]["file"], "line": h["route"]["line"],
                                  "text": f"{h['method']} {h['route']['full_path'] or h['route']['path']}", "via": "route"})

    def score(m, d):
        ext = sum(u["count"] + 1 for (mm, _), u in usage.items() if mm == m)
        return (d["routes"] * 6 + d["entry"] * 10 + sum(x["n"] for (a, _), x in http_by_mod.items() if a == m) * 2 + d["handlers"] * 4 + ext * 2 + min(d["lines"], 4000) / 400
                + min(indeg[m], 200) * 0.5 + min(outdeg[m], 50) * 0.2)

    def noise(m):
        first = m.split("/")[0]
        return first.startswith(".") or first in ("docs", "doc", "documentation", "benchmarks", "bench")

    ranked = sorted(((m, d) for m, d in mod.items() if not noise(m)), key=lambda kv: -score(*kv))
    keep = {m for m, _ in ranked[:max_modules]}
    nodes, edges = [], []
    for m, d in ranked[:max_modules]:
        models = sum(1 for f in d["file_list"] if f in acc.model_files)
        if d["front"] * 2 > d["files"] and not d["routes"] and not d["handlers"]:
            layer = "client"
        elif models * 2 > d["files"] and not d["routes"] and not d["entry"]:
            layer = "data"
        elif d["entry"]:
            layer = "entry"
        elif d["routes"]:
            layer = "routing"
        elif d["handlers"]:
            layer = "handlers"
        else:
            top = max(d["hints"].items(), key=lambda kv: kv[1])[0] if d["hints"] else None
            layer = HINT_TO_LAYER.get(top) or "services"
        nodes.append({"id": m, "label": m, "kind": "module", "layer": layer, "files": d["files"], "lines": d["lines"],
                      "routes": d["routes"], "file_list": sorted(d["file_list"]),
                      "layer_basis": "frontend code (inferred)" if layer == "client" else
                      "database models" if layer == "data" and models * 2 > d["files"] else "entry point" if d["entry"] else "defines routes" if d["routes"] else
                      "contains route handlers" if d["handlers"] else "folder naming (inferred)"})
    has_routes = any(n["routes"] for n in nodes)
    if has_routes:
        nodes.insert(0, {"id": "@client", "label": "HTTP client", "kind": "client", "layer": "client", "files": 0, "lines": 0})
        for n in nodes:
            if n.get("routes"):
                ev = [{"file": r["file"], "line": r["line"], "text": f"{r['method']} {r['full_path'] or r['path']}", "via": "route"}
                      for r in store.q("SELECT file, line, method, path, full_path FROM routes WHERE kind='route' AND file LIKE ? ESCAPE '!' LIMIT 6",
                                       (_like_prefix(n["id"]) if n["id"] != "(root)" else "%",))]
                edges.append({"source": "@client", "target": n["id"], "kind": "request", "weight": n["routes"],
                              "label": f"{n['routes']} route(s)", "evidence": ev, "verification": "verified-source"})
    for (a, b), x in http_by_mod.items():
        if a in keep and b in keep:
            edges.append({"source": a, "target": b, "kind": "request", "weight": x["n"],
                          "label": f"{x['n']} HTTP call(s): " + ", ".join(sorted(x["routes"])[:4]),
                          "evidence": x["evidence"], "verification": "structurally-inferred"})
    for (a, b), e in mg_edges.items():
        e = dict(e, source=a, target=b)
        if e["source"] in keep and e["target"] in keep:
            edges.append({"source": e["source"], "target": e["target"], "kind": "call", "weight": e["imports"] + e["calls"],
                          "label": f"{e['imports']} import(s), {e['calls']} call(s)",
                          "evidence": [{"file": x["file"], "line": x["line"], "text": f"imports {x['to']}", "via": "import"} for x in e["examples"]],
                          "verification": "verified-source"})
    storages = {}
    for (m, label), u in usage.items():
        if m not in keep:
            continue
        sid = "@" + label
        if sid not in storages:
            storages[sid] = {"id": sid, "label": label, "kind": "storage", "storage_kind": storage_kind[label],
                             "layer": "storage", "packages": set()}
        storages[sid]["packages"] |= u["modules"]
        ops = db_ops.get((m, label))
        lab = (", ".join(f"{n} {op}(s)" for op, n in sorted(ops.items())) if ops else
               f"{u['count']} call(s)" if u["count"] else "imported")
        edges.append({"source": m, "target": sid, "kind": "data", "weight": max(1, u["count"]),
                      "label": lab, "evidence": u["evidence"], "ops": dict(ops) if ops else None,
                      "verification": "structurally-inferred" if (u.get("inferred") or not u["count"]) else "verified-source"})
    for s in storages.values():
        s["packages"] = sorted(s["packages"])[:8]
        nodes.append(s)
    return {"nodes": nodes, "edges": edges, "layers": LAYER_ORDER, "modules_total": len(mod),
            "modules_shown": len(keep),
            "note": "Components and storages come from parsed imports and external calls. Layers come from entry points, "
                    "routes and handlers (verified) or folder names (inferred). Dynamic wiring is not shown."}


def _like_prefix(module_id: str) -> str:
    """LIKE pattern (ESCAPE '!') for files under module_id, so `my_app` cannot match `myXapp`."""
    esc = module_id.rstrip("/").replace("!", "!!").replace("%", "!%").replace("_", "!_")
    return esc + "/%"
