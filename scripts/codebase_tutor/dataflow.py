"""System map: layered components + storages/external systems, built only from parsed imports and calls."""
from __future__ import annotations

import json
from collections import defaultdict

from .graph import layer_hint, module_graph, module_of

# package root -> (kind, label). Kinds drive the icon and colour in the report.
STORAGE = {
    # databases / ORMs
    "mongoose": ("database", "MongoDB"), "mongodb": ("database", "MongoDB"), "pg": ("database", "PostgreSQL"),
    "postgres": ("database", "PostgreSQL"), "mysql": ("database", "MySQL"), "mysql2": ("database", "MySQL"),
    "sqlite3": ("database", "SQLite"), "better-sqlite3": ("database", "SQLite"), "sequelize": ("database", "SQL (Sequelize)"),
    "typeorm": ("database", "SQL (TypeORM)"), "@prisma/client": ("database", "Database (Prisma)"), "prisma": ("database", "Database (Prisma)"),
    "knex": ("database", "SQL (Knex)"), "drizzle-orm": ("database", "SQL (Drizzle)"), "sqlalchemy": ("database", "SQL (SQLAlchemy)"),
    "psycopg2": ("database", "PostgreSQL"), "psycopg": ("database", "PostgreSQL"), "pymongo": ("database", "MongoDB"),
    "peewee": ("database", "SQL (peewee)"), "django.db": ("database", "Database (Django ORM)"), "redis-om": ("database", "Redis"),
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


def system_map(store, max_modules: int = 16) -> dict:
    roles = {r["path"]: (r["role"], r["lines"] or 0, r["entry"]) for r in store.q("SELECT path, role, lines, entry FROM files")}
    src = {p for p, v in roles.items() if v[0] == "source"}
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
    mod = defaultdict(lambda: {"files": 0, "lines": 0, "routes": 0, "entry": 0, "handlers": 0, "hints": defaultdict(int), "file_list": []})
    for p in src:
        m = module_of(p)
        d = mod[m]
        d["files"] += 1
        d["lines"] += roles[p][1]
        d["routes"] += route_files.get(p, 0)
        d["entry"] += p in entry_files
        d["handlers"] += p in handler_files
        h = layer_hint(p)
        if h:
            d["hints"][h] += 1
        if len(d["file_list"]) < 40:
            d["file_list"].append(p)

    # storage usage per module from external imports + external calls (with evidence)
    usage = defaultdict(lambda: {"count": 0, "evidence": [], "modules": set()})  # (module, storage_label) -> ...
    storage_kind = {}
    for r in store.q("SELECT file, line, expr, external FROM calls WHERE resolution='external'"):
        if r["file"] not in src:
            continue
        cls = classify_external(r["external"])
        if not cls:
            continue
        key = (module_of(r["file"]), cls[1])
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
        key = (module_of(r["file"]), cls[1])
        storage_kind[cls[1]] = cls[0]
        u = usage[key]
        u["modules"].add(r["module"])
        if u["count"] == 0 and len(u["evidence"]) < 6:
            u["evidence"].append({"file": r["file"], "line": r["line"], "text": f"import {r['module']}", "via": "import"})
    # Python: builtin open() is file I/O
    for r in store.q("SELECT c.file, c.line, c.expr FROM calls c JOIN files f ON f.path=c.file "
                     "WHERE f.lang='python' AND c.name='open' AND c.receiver IS NULL AND c.resolution='builtin' LIMIT 400"):
        if r["file"] in src:
            key = (module_of(r["file"]), "File system")
            storage_kind["File system"] = "files"
            u = usage[key]
            u["count"] += 1
            u["modules"].add("open()")
            if len(u["evidence"]) < 6:
                u["evidence"].append({"file": r["file"], "line": r["line"], "text": "open()", "via": "call"})

    mg = module_graph(store, depth=2)
    indeg, outdeg = defaultdict(int), defaultdict(int)
    for e in mg["edges"]:
        indeg[e["target"]] += e["imports"] + e["calls"]
        outdeg[e["source"]] += e["imports"] + e["calls"]

    def score(m, d):
        ext = sum(u["count"] + 1 for (mm, _), u in usage.items() if mm == m)
        return (d["routes"] * 6 + d["entry"] * 10 + d["handlers"] * 4 + ext * 2 + min(d["lines"], 4000) / 400
                + min(indeg[m], 200) * 0.5 + min(outdeg[m], 50) * 0.2)

    def noise(m):
        first = m.split("/")[0]
        return first.startswith(".") or first in ("docs", "doc", "documentation", "benchmarks", "bench")

    ranked = sorted(((m, d) for m, d in mod.items() if not noise(m)), key=lambda kv: -score(*kv))
    keep = {m for m, _ in ranked[:max_modules]}
    nodes, edges = [], []
    for m, d in ranked[:max_modules]:
        if d["entry"]:
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
                      "layer_basis": "entry point" if d["entry"] else "defines routes" if d["routes"] else
                      "contains route handlers" if d["handlers"] else "folder naming (inferred)"})
    has_routes = any(n["routes"] for n in nodes)
    if has_routes:
        nodes.insert(0, {"id": "@client", "label": "HTTP client", "kind": "client", "layer": "client", "files": 0, "lines": 0})
        for n in nodes:
            if n.get("routes"):
                ev = [{"file": r["file"], "line": r["line"], "text": f"{r['method']} {r['full_path'] or r['path']}", "via": "route"}
                      for r in store.q("SELECT file, line, method, path, full_path FROM routes WHERE kind='route' AND file LIKE ? LIMIT 6",
                                       (n["id"].rstrip("/") + "/%" if n["id"] != "(root)" else "%",))]
                edges.append({"source": "@client", "target": n["id"], "kind": "request", "weight": n["routes"],
                              "label": f"{n['routes']} route(s)", "evidence": ev, "verification": "verified-source"})
    for e in mg["edges"]:
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
        edges.append({"source": m, "target": sid, "kind": "data", "weight": max(1, u["count"]),
                      "label": f"{u['count']} call(s)" if u["count"] else "imported", "evidence": u["evidence"],
                      "verification": "verified-source" if u["count"] else "structurally-inferred"})
    for s in storages.values():
        s["packages"] = sorted(s["packages"])[:8]
        nodes.append(s)
    return {"nodes": nodes, "edges": edges, "layers": LAYER_ORDER, "modules_total": len(mod),
            "modules_shown": len(keep),
            "note": "Components and storages come from parsed imports and external calls. Layers come from entry points, "
                    "routes and handlers (verified) or folder names (inferred). Dynamic wiring is not shown."}
