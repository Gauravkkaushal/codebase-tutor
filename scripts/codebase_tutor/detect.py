"""Technology detection from manifests and file inventory. Every finding carries file(+line) evidence."""
from __future__ import annotations

import json
import posixpath
import re
from collections import defaultdict
from pathlib import Path

CATALOG = {
    # name: (category, label)
    "express": ("framework", "Express"), "koa": ("framework", "Koa"), "fastify": ("framework", "Fastify"),
    "@nestjs/core": ("framework", "NestJS"), "next": ("framework", "Next.js"), "react": ("framework", "React"),
    "react-dom": ("framework", "React DOM"), "vue": ("framework", "Vue"), "@angular/core": ("framework", "Angular"),
    "svelte": ("framework", "Svelte"), "nuxt": ("framework", "Nuxt"), "@hapi/hapi": ("framework", "hapi"),
    "hono": ("framework", "Hono"), "electron": ("framework", "Electron"), "react-native": ("framework", "React Native"),
    "django": ("framework", "Django"), "flask": ("framework", "Flask"), "fastapi": ("framework", "FastAPI"),
    "starlette": ("framework", "Starlette"), "tornado": ("framework", "Tornado"), "aiohttp": ("framework", "aiohttp"),
    "djangorestframework": ("framework", "Django REST framework"), "graphql": ("framework", "GraphQL"),
    "apollo-server": ("framework", "Apollo Server"), "@apollo/server": ("framework", "Apollo Server"),
    "mongoose": ("database", "MongoDB (Mongoose)"), "mongodb": ("database", "MongoDB driver"),
    "sequelize": ("database", "Sequelize ORM"), "typeorm": ("database", "TypeORM"), "prisma": ("database", "Prisma"),
    "@prisma/client": ("database", "Prisma client"), "knex": ("database", "Knex"), "pg": ("database", "PostgreSQL (pg)"),
    "mysql": ("database", "MySQL"), "mysql2": ("database", "MySQL"), "sqlite3": ("database", "SQLite"),
    "better-sqlite3": ("database", "SQLite"), "redis": ("database", "Redis"), "ioredis": ("database", "Redis"),
    "sqlalchemy": ("database", "SQLAlchemy"), "psycopg2": ("database", "PostgreSQL (psycopg2)"),
    "psycopg2-binary": ("database", "PostgreSQL (psycopg2)"), "psycopg": ("database", "PostgreSQL (psycopg)"),
    "pymongo": ("database", "MongoDB (pymongo)"), "peewee": ("database", "peewee"), "drizzle-orm": ("database", "Drizzle ORM"),
    "elasticsearch": ("database", "Elasticsearch"), "alembic": ("database", "Alembic migrations"),
    "passport": ("auth", "Passport"), "jsonwebtoken": ("auth", "JWT (jsonwebtoken)"), "bcrypt": ("auth", "bcrypt"),
    "bcryptjs": ("auth", "bcryptjs"), "express-session": ("auth", "express-session"), "cookie-session": ("auth", "cookie-session"),
    "next-auth": ("auth", "NextAuth"), "pyjwt": ("auth", "PyJWT"), "flask-login": ("auth", "Flask-Login"),
    "authlib": ("auth", "Authlib"), "python-jose": ("auth", "python-jose"), "passlib": ("auth", "passlib"),
    "pbkdf2-password": ("auth", "pbkdf2-password"), "argon2": ("auth", "argon2"), "helmet": ("security", "helmet"),
    "cors": ("security", "CORS"), "csurf": ("security", "CSRF"),
    "stripe": ("external", "Stripe"), "aws-sdk": ("external", "AWS SDK"), "axios": ("external", "HTTP client (axios)"),
    "node-fetch": ("external", "HTTP client (node-fetch)"), "got": ("external", "HTTP client (got)"),
    "requests": ("external", "HTTP client (requests)"), "httpx": ("external", "HTTP client (httpx)"),
    "twilio": ("external", "Twilio"), "@sendgrid/mail": ("external", "SendGrid"), "nodemailer": ("external", "Email (nodemailer)"),
    "firebase": ("external", "Firebase"), "firebase-admin": ("external", "Firebase Admin"), "openai": ("external", "OpenAI API"),
    "@anthropic-ai/sdk": ("external", "Anthropic API"), "anthropic": ("external", "Anthropic API"), "boto3": ("external", "AWS (boto3)"),
    "kafkajs": ("queue", "Kafka"), "amqplib": ("queue", "RabbitMQ"), "bull": ("queue", "Bull queue"), "bullmq": ("queue", "BullMQ"),
    "celery": ("queue", "Celery workers"), "rq": ("queue", "RQ workers"), "socket.io": ("realtime", "Socket.IO"), "ws": ("realtime", "WebSocket (ws)"),
    "jest": ("test", "Jest"), "mocha": ("test", "Mocha"), "vitest": ("test", "Vitest"), "chai": ("test", "Chai"),
    "supertest": ("test", "Supertest"), "jasmine": ("test", "Jasmine"), "ava": ("test", "AVA"), "tap": ("test", "tap"),
    "cypress": ("test", "Cypress"), "@playwright/test": ("test", "Playwright"), "pytest": ("test", "pytest"),
    "nose": ("test", "nose"), "hypothesis": ("test", "Hypothesis"), "tox": ("test", "tox"), "nyc": ("test", "nyc coverage"),
    "webpack": ("build", "webpack"), "vite": ("build", "Vite"), "rollup": ("build", "Rollup"), "esbuild": ("build", "esbuild"),
    "parcel": ("build", "Parcel"), "typescript": ("build", "TypeScript compiler"), "@babel/core": ("build", "Babel"),
    "turbo": ("build", "Turborepo"), "nx": ("build", "Nx"), "gulp": ("build", "gulp"), "eslint": ("lint", "ESLint"),
    "prettier": ("lint", "Prettier"), "ruff": ("lint", "Ruff"), "flake8": ("lint", "flake8"), "black": ("lint", "Black"),
    "mypy": ("lint", "mypy"),
}
LOCK_MANAGERS = {"package-lock.json": "npm", "npm-shrinkwrap.json": "npm", "yarn.lock": "yarn", "pnpm-lock.yaml": "pnpm",
                 "bun.lockb": "bun", "poetry.lock": "poetry", "Pipfile.lock": "pipenv", "uv.lock": "uv",
                 "Cargo.lock": "cargo", "go.sum": "go modules", "Gemfile.lock": "bundler", "composer.lock": "composer"}
MANIFEST_MANAGERS = {"package.json": "npm-compatible (package.json)", "requirements.txt": "pip (requirements.txt)",
                     "pyproject.toml": "pyproject", "setup.py": "setuptools", "Pipfile": "pipenv", "go.mod": "go modules",
                     "Cargo.toml": "cargo", "pom.xml": "maven", "build.gradle": "gradle", "build.gradle.kts": "gradle",
                     "Gemfile": "bundler", "composer.json": "composer"}
CI_PATTERNS = [(re.compile(r"^\.github/workflows/.+\.ya?ml$"), "GitHub Actions"), (re.compile(r"^\.gitlab-ci\.yml$"), "GitLab CI"),
               (re.compile(r"^\.circleci/config\.ya?ml$"), "CircleCI"), (re.compile(r"(^|/)Jenkinsfile$"), "Jenkins"),
               (re.compile(r"^azure-pipelines\.ya?ml$"), "Azure Pipelines"), (re.compile(r"^\.travis\.yml$"), "Travis CI"),
               (re.compile(r"^bitbucket-pipelines\.yml$"), "Bitbucket Pipelines"), (re.compile(r"^appveyor\.yml$"), "AppVeyor")]


def _read(root: Path, rel: str, limit: int = 2_000_000) -> str:
    try:
        p = root / rel
        if p.stat().st_size > limit:
            return ""
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _line_of(text: str, needle: str) -> int | None:
    idx = text.find(needle)
    return text.count("\n", 0, idx) + 1 if idx >= 0 else None


def _py_deps(root: Path, rel: str) -> list:
    text = _read(root, rel)
    deps = []
    base = posixpath.basename(rel)
    if base.startswith("requirements") and base.endswith(".txt"):
        for i, ln in enumerate(text.splitlines(), 1):
            ln = ln.split("#")[0].strip()
            if ln and not ln.startswith("-"):
                m = re.match(r"([A-Za-z0-9_.\-]+)", ln)
                if m:
                    deps.append((m.group(1).lower(), i, "runtime"))
    elif base == "pyproject.toml":
        section = None
        for i, ln in enumerate(text.splitlines(), 1):
            s = ln.strip()
            if s.startswith("["):
                section = s
                continue
            m = re.match(r'^\s*"([A-Za-z0-9_.\-]+)', ln)
            if m and section in ("[project]", "[project.optional-dependencies]", "[dependency-groups]") or \
                    (m and section and "dependencies" in section):
                deps.append((m.group(1).lower(), i, "dev" if "dev" in (section or "") or "test" in (section or "") else "runtime"))
            m2 = re.match(r"^([A-Za-z0-9_.\-]+)\s*=", s)
            if m2 and section and "poetry" in section and "dependencies" in section and m2.group(1) != "python":
                deps.append((m2.group(1).lower(), i, "dev" if "dev" in section else "runtime"))
    elif base in ("setup.py", "setup.cfg", "Pipfile"):
        for i, ln in enumerate(text.splitlines(), 1):
            for m in re.finditer(r"""['"]([A-Za-z0-9_.\-]+)\s*(?:[<>=~!].*?)?['"]""", ln):
                name = m.group(1).lower()
                if name in CATALOG:
                    deps.append((name, i, "runtime"))
    return deps


def detect(root: Path, paths: list, store) -> dict:
    root = Path(root)
    pathset = set(paths)
    out = defaultdict(list)
    seen = set()

    def add(cat, label, file, line=None, detail=None):
        key = (cat, label, file)
        if key in seen:
            return
        seen.add(key)
        out[cat].append({"name": label, "file": file, "line": line, **({"detail": detail} if detail else {})})

    manifests_js = sorted(p for p in paths if posixpath.basename(p) == "package.json")
    manifests_py = sorted(p for p in paths if posixpath.basename(p) in ("pyproject.toml", "setup.py", "setup.cfg", "Pipfile")
                          or (posixpath.basename(p).startswith("requirements") and p.endswith(".txt")))
    entry_points = []
    scripts = {}
    workspaces = None
    for m in manifests_js:
        text = _read(root, m)
        try:
            data = json.loads(text)
        except ValueError:
            continue
        for sect, kind in (("dependencies", "runtime"), ("devDependencies", "dev"), ("peerDependencies", "peer"),
                           ("optionalDependencies", "optional")):
            for dep in (data.get(sect) or {}):
                info = CATALOG.get(dep)
                if info is None and dep.startswith("@aws-sdk/"):
                    info = ("external", "AWS SDK v3")
                if info is None and dep.startswith("@google-cloud/"):
                    info = ("external", "Google Cloud SDK")
                if info:
                    add(info[0], info[1], m, _line_of(text, f'"{dep}"'), kind)
        d = posixpath.dirname(m)
        if m == "package.json" or not scripts:
            scripts = {k: v for k, v in (data.get("scripts") or {}).items()}
            if scripts:
                out["scripts"] = [{"name": k, "command": v, "file": m, "line": _line_of(text, f'"{k}"')} for k, v in scripts.items()]
        main = data.get("main")
        if main:
            target = posixpath.normpath(posixpath.join(d, main))
            for cand in (target, target + ".js", posixpath.join(target, "index.js")):
                if cand in pathset:
                    entry_points.append({"file": cand, "reason": f'package.json "main" ({m})', "evidence": {"file": m, "line": _line_of(text, '"main"')}})
                    break
        elif not main and m == "package.json":
            for cand in ("index.js", "index.mjs", "index.ts"):
                if cand in pathset:
                    entry_points.append({"file": cand, "reason": 'Node default entry (package.json has no "main")',
                                         "evidence": {"file": m, "line": 1}})
                    break
        bins = data.get("bin")
        if isinstance(bins, str):
            bins = {data.get("name", "bin"): bins}
        for bname, bpath in (bins or {}).items():
            target = posixpath.normpath(posixpath.join(d, bpath))
            if target in pathset:
                entry_points.append({"file": target, "reason": f'package.json "bin" {bname}', "evidence": {"file": m, "line": _line_of(text, '"bin"')}})
        start = (data.get("scripts") or {}).get("start", "")
        mm = re.search(r"\bnode(?:mon)?\s+([\w./\-]+)", start)
        if mm:
            target = posixpath.normpath(posixpath.join(d, mm.group(1)))
            for cand in (target, target + ".js"):
                if cand in pathset:
                    entry_points.append({"file": cand, "reason": "npm start script", "evidence": {"file": m, "line": _line_of(text, '"start"')}})
        if m == "package.json" and data.get("workspaces"):
            ws = data["workspaces"]
            workspaces = {"type": "npm/yarn workspaces", "patterns": ws if isinstance(ws, list) else ws.get("packages", []),
                          "evidence": {"file": m, "line": _line_of(text, '"workspaces"')}}
        if m == "package.json":
            out["project"] = [{"name": data.get("name"), "version": data.get("version"), "description": data.get("description"),
                               "file": m, "line": 1}]
    for m in manifests_py:
        for dep, line, kind in _py_deps(root, m):
            info = CATALOG.get(dep)
            if info:
                add(info[0], info[1], m, line, kind)
        if posixpath.basename(m) == "pyproject.toml":
            text = _read(root, m)
            sec = re.search(r"^\[project\.scripts\]\s*$(.*?)(?=^\[|\Z)", text, re.M | re.S)
            if sec:
                for ln in sec.group(1).splitlines():
                    mm = re.match(r'\s*([\w\-]+)\s*=\s*"([\w.]+):(\w+)"', ln)
                    if mm:
                        entry_points.append({"file": None, "reason": f"console script {mm.group(1)} -> {mm.group(2)}:{mm.group(3)}",
                                             "evidence": {"file": m, "line": _line_of(text, mm.group(0).strip())}})
            if not out.get("project"):
                nm = re.search(r'^name\s*=\s*"([^"]+)"', text, re.M)
                desc = re.search(r'^description\s*=\s*"([^"]+)"', text, re.M)
                if nm:
                    out["project"] = [{"name": nm.group(1), "description": desc.group(1) if desc else None, "file": m,
                                       "line": _line_of(text, nm.group(0))}]
    for p in paths:
        base = posixpath.basename(p)
        if base in LOCK_MANAGERS:
            add("package_managers", LOCK_MANAGERS[base], p)
        elif base in MANIFEST_MANAGERS and "/" not in p:
            add("package_managers", MANIFEST_MANAGERS[base], p)
        for rx, label in CI_PATTERNS:
            if rx.search(p):
                add("ci", label, p)
        if base.startswith("Dockerfile") or base.endswith(".dockerfile"):
            add("containers", "Docker", p)
            text = _read(root, p)
            for i, ln in enumerate(text.splitlines(), 1):
                if re.match(r"\s*(CMD|ENTRYPOINT)\b", ln):
                    entry_points.append({"file": None, "reason": f"Dockerfile {ln.strip()[:100]}", "evidence": {"file": p, "line": i}})
        elif base in ("docker-compose.yml", "docker-compose.yaml", "compose.yaml", "compose.yml"):
            add("containers", "Docker Compose", p)
        elif base == "Procfile":
            text = _read(root, p)
            for i, ln in enumerate(text.splitlines(), 1):
                if ":" in ln:
                    entry_points.append({"file": None, "reason": f"Procfile {ln.strip()[:100]}", "evidence": {"file": p, "line": i}})
        elif base in ("Makefile",) and "/" not in p:
            add("build", "Make", p)
        elif base in ("pnpm-workspace.yaml", "lerna.json", "nx.json", "turbo.json", "rush.json"):
            workspaces = workspaces or {"type": base.split(".")[0], "patterns": [], "evidence": {"file": p, "line": 1}}
        elif base in ("tsconfig.json",) and "/" not in p:
            add("build", "TypeScript project", p)
        if re.match(r"^(README|readme|Readme)(\.\w+)?$", base) or base in ("CONTRIBUTING.md", "ARCHITECTURE.md", "CODEOWNERS"):
            add("docs", base, p)
        if re.search(r"(^|/)(docs?/(adr|decisions)|architecture/decisions)/", p):
            add("docs", "ADR", p)
    nested_manifests = [m for m in manifests_js if m != "package.json"] + [m for m in manifests_py if "/" in m and m.endswith(("pyproject.toml", "setup.py"))]
    if workspaces is None and len(nested_manifests) >= 3:
        workspaces = {"type": "multiple packages (no workspace config)", "patterns": [], "evidence": {"file": nested_manifests[0], "line": 1}}
    if workspaces:
        workspaces["packages"] = sorted({posixpath.dirname(m) for m in nested_manifests})[:200]
        out["monorepo"] = [workspaces]

    # entry points recorded by parsers
    for r in store.q("SELECT path, entry FROM files WHERE entry IS NOT NULL AND role='source'"):
        for reason in json.loads(r["entry"]):
            mline = re.search(r"\(line (\d+)\)", reason)
            entry_points.append({"file": r["path"], "reason": reason,
                                 "evidence": {"file": r["path"], "line": int(mline.group(1)) if mline else 1}})
    uniq, keys = [], set()
    for e in entry_points:
        k = (e["file"], e["reason"])
        if k not in keys:
            keys.add(k)
            uniq.append(e)
    out["entry_points"] = uniq
    return dict(out)
