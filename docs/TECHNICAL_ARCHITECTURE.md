# Technical Architecture — Codebase Tutor

## 1. Division of labour

```
            ┌──────────────── Agent (Claude Code / Codex / Antigravity) ────────────────┐
            │  SKILL.md workflow · explanations · teaching · plans · reviews (LLM)      │
            └──────────────┬─────────────────────────────────────────────▲──────────────┘
                           │ CLI calls (JSON out)                         │ verified facts
            ┌──────────────▼─────────────────────────────────────────────┴──────────────┐
            │                 Engine: scripts/ct.py  (deterministic, no LLM)             │
            │ inventory → detect → parse (tree-sitter / ast) → resolve → store (SQLite) │
            │ evidence · flows · context · changes · tests · runtime · report           │
            └──────────────┬─────────────────────────────────────────────────────────────┘
                           │
            ┌──────────────▼──────────── target-repo/.codebase-tutor/ ──────────────────┐
            │ config.json · knowledge/index.db · knowledge/{flows,explanations,contexts} │
            │ snapshots/{manifests,blobs} · runs/{tests,runtime} · reports/ · cache/     │
            └────────────────────────────────────────────────────────────────────────────┘
```

The engine never guesses: it emits only what it parsed, resolved, or executed, each with a resolution/verification
label. The agent turns facts into explanations, and every explanation it saves is validated by the engine
(paths exist, line ranges exist, content hashes recorded).

## 2. Modules (`scripts/codebase_tutor/`)

| Module | Responsibility |
|---|---|
| `config.py` | `.codebase-tutor/config.json` defaults, include/exclude globs, limits |
| `inventory.py` | Walk repo (git-aware when possible), classify role (source/test/config/doc/generated/vendor/binary), language, hash |
| `detect.py` | Manifests → frameworks, package managers, build, CI, monorepo, DB/auth/external services, entry points |
| `parsers/python_parser.py` | stdlib `ast`: symbols, imports, calls, routes (Flask/FastAPI/Django), control points, env vars |
| `parsers/js_parser.py` | Tree-sitter JS/TS/TSX: same outputs; Express/Koa/Fastify routes; CJS + ESM imports; heuristic fallback |
| `resolve.py` | Import resolution (relative, index files, tsconfig paths, Python packages/src layout); call resolution strategies |
| `store.py` | SQLite schema + queries; meta; snapshot table |
| `analyzer.py` | Orchestrates scan: incremental diffing by hash, parallel parse, batch commits, resolution, test links, coverage |
| `graph.py` | Module graph, SCC cycles, orphans, importers, call graph traversal (callers/callees, transitive) |
| `evidence.py` | Excerpts with line numbers + highlights, secret redaction, evidence refs (sha1 of exact text), staleness |
| `flows.py` | Static flow tracing from symbol / `file:line` / route with branches and outcomes |
| `context.py` | Contribution context expansion + coverage table |
| `snapshots.py` | Manifests + content-addressed gzip blobs; git metadata; old-content retrieval (blob → git fallback) |
| `changes.py` | File/symbol/signature/import/route/dependency/env diffs, behaviour signals, impact analysis |
| `testing.py` | Runner detection, related-test planning, approval-gated execution, result parsing |
| `runtime/` | Python `sitecustomize` profiler hook; Node `--require` hook (Proxy-wrapped exports) |
| `explain.py` | Explanation/flow schema validation and storage |
| `report.py` | Builds data bundle, `report.md`, copies HTML app assets, writes `data.js` |
| `i18n/*.json` | UI strings + templated sentences (en, hi, hinglish) |

## 3. Data model (SQLite `knowledge/index.db`)

- `files(path, lang, role, size, lines, hash, status, parser, error, analyzed_at)`
- `symbols(id, file, name, qualname, kind, start_line, end_line, signature, exported, parent, body_hash)`
- `imports(file, line, module, resolved, names, kind, external)`
- `calls(file, line, caller, callee_expr, callee_name, resolved_id, resolution)`
- `routes(file, line, framework, method, path, handlers, mount_prefix)`
- `control(file, symbol, line, kind, text, outcome)` — if/else/return/throw/try/catch/await; outcome success/failure/neutral
- `env_vars(file, line, name)` — names only
- `test_links(test_file, target_file, via, confidence)`
- `evidence(id, file, start, end, text_hash, snapshot)`
- `snapshots(id, created_at, commit, branch, dirty, files, manifest)`
- `meta(key, value)`

Every row carries file + line provenance; `analyzed_at`/snapshot ties it to the state under which it was derived.

## 4. Resolution and verification labels

| Edge | How resolved | Label |
|---|---|---|
| Import of relative path / package module found on disk | path resolution | `verified-source` |
| Call to a name imported from a resolved module and defined there | import binding | `verified-source` |
| Call to function defined in same file / same class (`self.x`) | lexical | `verified-source` |
| `this.x()` / `obj.x()` matched by member name in same file, or unique global name | heuristic | `structurally-inferred` |
| Everything else | — | `unresolved` (counted, never drawn as a verified edge) |

Flow steps inherit the weakest label along their path. Test runs produce `test-verified` only for executed, passed
tests. Runtime traces produce `runtime-observed` events.

## 5. Incremental algorithm

1. Inventory → `(path, size, mtime, hash)`; hashes reused when size+mtime unchanged (fast path).
2. Compare with `files` table → added / modified / deleted / unchanged.
3. Delete rows for deleted+modified files; parse added+modified (process pool for large batches); commit every 200 files.
4. Re-run resolution for edges whose source or target file changed (global resolution pass is cheap and is used when > 5% changed).
5. Rebuild test links and graph caches; write snapshot manifest; store new blobs.
6. `evidence` refs whose file hash changed are re-checked; mismatches flagged `stale`.

An interrupted scan leaves already-committed files marked with their hash; the next run continues from there.

## 6. Change intelligence

Baseline = previous snapshot (default), a named snapshot, or a git ref. Old content comes from the blob store,
falling back to `git show <commit>:<path>`. Old and new versions are re-parsed with the same deterministic
parsers, so symbol-level diffs need no stored historical ASTs. Impact = reverse call graph from changed/removed
symbols (depth ≤ 3) + importers of changed files + routes whose handler chain reaches changed symbols + tests linked
to any impacted file. Unresolved call counts in impacted files are reported as an incompleteness warning.

## 7. Report

`ct report` writes `.codebase-tutor/reports/` with `report.md`, `index.html`, `app.js`, `styles.css`,
`vendor/cytoscape.min.js` and `data.js` (`window.CT_DATA = …`). Loading data through a script tag keeps the report
working from `file://`. Source is embedded only for files referenced by flows/explanations/symbol evidence plus the
most important files, up to a size budget (config). Language switching is client-side; all languages are embedded.

## 8. Security model

- Execution only via `ct tests run --yes` / `ct runtime --yes`; the SKILL requires the agent to show the command and
  get user approval first. Commands run with a timeout in the repo directory; output is captured, not streamed to reports.
- `.env*` files are listed but never read (except `.env.example`/`.env.sample`, for key names only).
- Excerpts pass through a redactor (private keys, AWS keys, `password/secret/token = "…"` literals).
- No network calls from the engine. No writes outside `.codebase-tutor/` (except `--out` paths given by the user).

## 9. Extensibility

- New language: add `parsers/<lang>_parser.py` returning the common `FileFacts` structure.
- New UI language: add `i18n/<code>.json` with the same keys; `tests/test_i18n.py` enforces parity.
- New agent platform: add `adapters/<platform>/INSTALL.md`; the core is plain files + Python.
