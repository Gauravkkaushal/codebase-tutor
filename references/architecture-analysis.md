# Architecture analysis (Mode A)

## Procedure

1. `ct scan` → check `coverage` (analysed / partial / inventory-only languages, excluded dirs, unresolved calls).
2. `ct overview` → project description, languages, stack (each item has `file:line` evidence), package managers, CI,
   containers, monorepo layout, entry points (with reasons), most-connected files (`hubs`), routes, env-var names,
   cycles, orphans, a suggested learning path, and limitations.
3. `ct graph --depth 2` → module-level dependency graph from **real** imports + resolved calls (with example edges).
   Use `--depth 1/3` to zoom. `cycles` and `orphans` are architectural smells worth mentioning (cite them).
4. Read 2–5 key files: the main entry point, the top hubs, one route handler end to end (`ct trace`).
5. Explain: purpose → layers/modules and their responsibilities → how a request/event flows → data & external
   integrations → conventions → inconsistencies/risks → what is unexplored.

Layer names from folder conventions (`routes/`, `controllers/`, `services/`, `models/`…) are **hints** — label them
`structurally-inferred`. Edges in the graph are parsed facts.

## What the engine detects today

- Languages (all files), symbol extraction for **Python, JavaScript, TypeScript, TSX**. Other languages: inventory and
  line counts only (say so).
- Frameworks/libraries from `package.json`, `requirements*.txt`, `pyproject.toml`, `setup.py/cfg`, `Pipfile`.
- Routes: Express/Koa/Fastify-style `app|router.METHOD(path, ...handlers)`, `app.route(path).get(...)`,
  `app.use(prefix, router)` mounts (prefix applied), Flask/FastAPI decorators (Blueprint `url_prefix`, APIRouter
  `prefix`), Django `urlpatterns` (`path`, `re_path`, `include`), Next.js `pages/api` and `app/**/route.ts`.
- Entry points: `package.json` main/bin/start, Node default `index.js`, `app.listen()`, `if __name__ == "__main__"`,
  `manage.py`/`wsgi.py`/`asgi.py`, console scripts, Dockerfile CMD/ENTRYPOINT, Procfile.
- Tests: path conventions + import links (+ name mentions at query time).

## Hidden wiring (where static traces go cold)

| Stack | Look for |
|---|---|
| Express/Koa | middleware registered in loops or from arrays; routers built in factories; `app.set`/`app.locals` configuration; error middleware `(err, req, res, next)` |
| NestJS / Angular | decorators (`@Controller`, `@Get`, `@Injectable`), DI container, module `providers` arrays — not resolved yet |
| Django | `settings.py` (`INSTALLED_APPS`, `MIDDLEWARE`, `ROOT_URLCONF`), signals, class-based views (`as_view()`), admin autodiscovery |
| Flask | `app.register_blueprint(bp, url_prefix=...)` (prefix at registration is not applied yet), app factories, `before_request` hooks |
| FastAPI | `include_router(prefix=...)`, `Depends(...)` dependency injection |
| Python generally | `getattr`, plugin registries, entry points in `pyproject`, metaclasses, monkeypatching |
| JS generally | dynamic `require(variable)`, event emitters (`on/emit`), `Object.assign`/mixins (resolved only by name), DI containers |
| Any | message queues/topics, cron/schedulers, feature flags, config-driven routing, generated code |

When you hit one: read the registration site, cite it, and label the edge you add by reasoning as `structurally-inferred`.

## Trap questions

If asked about something that does not exist ("which file implements the service mesh?"), say it was not found,
show what you searched (`ct search`), and cite what actually handles the concern.
