# CLI reference

`python <skill>/scripts/ct.py [-C REPO] [--no-refresh] <command> [...]` — JSON output unless `--text`.
Query commands auto-run an incremental scan if the git working tree changed since the last scan.

| Command | Purpose |
|---|---|
| `init` | Create `.codebase-tutor/` (config, folders, its own `.gitignore`). |
| `scan [--full] [--jobs N] [--quiet] [--note T]` | Incremental index + resolution + detection + snapshot. Prints coverage and changes since last scan. |
| `status` | Unscanned changes, last snapshot, evidence status. |
| `overview [--section a,b]` | Stack, structure, entry points, hubs, routes, env names, learning path, coverage, limitations. |
| `search TEXT` | Symbols, files, routes matching TEXT. |
| `symbol TARGET [--text]` | Definition excerpt, callers, callees, control points, routes, ranked tests. TARGET: name, qualname, id, `file#name`, `file:line`. |
| `evidence PATH N[-M] [--highlight a,b-c] [--context K] [--register] [--text]` | Exact excerpt with line numbers and highlights; `--register` tracks it for staleness. |
| `callers TARGET` / `callees TARGET` | Resolved call edges with resolution labels. |
| `deps PATH` | Imports and importers of a file. |
| `routes` | All routes, mounts, middleware with handler ids and full paths. |
| `tests-for TARGET` | Ranked related tests with explicit signals. |
| `graph [--depth N] [--include-tests]` | Module graph, cycles, orphans. |
| `trace TARGET [--depth N] [--title T] [--no-save] [--text]` | Static flow (Level 1). |
| `context TARGET [--task T] [--text]` | Contribution context + coverage table. |
| `changes [--since last\|SNAP\|git:REF] [--text]` | Change intelligence (code, behaviour, impact, risks). |
| `snapshots` | List snapshots. |
| `tests detect` / `tests plan TARGET` / `tests run --yes -- CMD…` / `tests list` | Test-backed verification (Level 2). |
| `runtime --yes [--lang python\|node] -- CMD…` | Runtime tracing (Level 3, experimental). |
| `explain add FILE` / `explain validate FILE` / `explain list` | Agent-authored explanations, validated against source. |
| `verify [--file MD\|-]` | Re-check evidence refs, explanations, and citations in Markdown. |
| `report [--lang L] [--out DIR]` | report.md + interactive index.html. |

## Data layout (`<repo>/.codebase-tutor/`)

```
config.json                 user settings (language, include/exclude, budgets)
knowledge/index.db          SQLite: files, symbols, imports, exports, calls, routes, control, env_vars, test_links, evidence, snapshots, meta
knowledge/flows/*.json      saved static flows
knowledge/explanations/*.json  agent-authored, validated explanations (commit these if the team wants)
knowledge/contexts/*.json   contribution contexts
knowledge/changes/*.json    change analyses (+ latest.json)
snapshots/manifests/*.json.gz, snapshots/blobs/   repository states
runs/tests/<id>/            test runs (result.json, logs)
runs/runtime/<id>/          runtime traces
reports/                    generated report
```
Exit codes: 0 ok · 2 no knowledge base / usage · 3 target not found · 4 evidence error.
