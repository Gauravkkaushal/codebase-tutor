# Report generation (Mode D)

`ct report [--lang en|hi|hinglish] [--out DIR]` writes (default `.codebase-tutor/reports/`):

| File | Content |
|---|---|
| `report.md` | Readable report in the selected language: overview + stack (with evidence), structure, entry points, hubs, routes, env-var names, learning path, explanations with excerpts, flows, contribution contexts, change analysis, test/runtime results, coverage & limitations. |
| `index.html` + `app.js` + `styles.css` | Standalone interactive app (no server, no CDN). |
| `data.js` | All report data (`window.CT_DATA`), including every language's UI strings. |
| `viz.js` | Dependency-free SVG animation: system map, flow stage, count-up. Honors `prefers-reduced-motion`. |
| `vendor/cytoscape.min.js` | Graph layout/interaction (MIT, vendored, ~430 KB). Only third-party dependency. |

Sections of the HTML app: Overview (animated hero with counted stats, detected storages, compact system map) ·
Data Flow (system map from `dataflow.system_map`: layered columns client → entry → routing → middleware → handlers →
services → data → library → storage; storage/external nodes with kind icons — database, cache, session, files,
external API, queue, auth, email, cloud, views; animated packets per edge kind (request / imports-calls /
data read-write), click for connections with evidence lines, pause, and "replay a flow" which moves a comet through
the components a traced flow visits; storage cards with packages and call sites. Full-stack repos: frontend HTTP calls whose URL matches a route in the
repo become request edges from the frontend module (and the first `client-call` step of that route's flow); calls on
names imported from a local file that imports a database package (Mongoose models, a `db.js` pool) and on variables
assigned from them become database read/write edges and steps — both labelled structurally-inferred) · Architecture Explorer (module/file graph from real edges, filters, search, node
details with example edges, drill-down) · Execution Flows (playback: play/pause/prev/next/restart/speed, keyboard:
space/←/→; animated request-journey stage — packet moves client → file → callee file / storage and back, green
on success, red on failure, "play up to here" per outcome; synchronized source with highlighted line; narration from `flow-notes`; outcomes) · Code
Evidence (file tree, syntax highlighting, `#/code/<path>:<start>-<end>` deep links, symbols with callers/callees,
imports/importers) · Learning Center (levels, explanations with evidence blocks + staleness badges, concepts,
interactive checkpoints, learning path) · Contribution Center (coverage tables, callers, tests, routes, branch
conditions, readiness checklist) · Change Analysis (risks, behaviour signals, diffs, impact, tests to run) ·
Simulation Lab (L1 outcomes, L2 test runs per test, L3 runtime traces).

## Before generating

Make sure the knowledge base has what the user needs: `ct trace` for 1–3 key flows, `ct explain add` for the
explanations you gave (all languages the user wants), `ct context` for contribution targets, `ct changes` after edits,
and approved test/runtime runs. The report never invents content: empty sections show how to fill them.

## Size

Source is embedded for every file referenced by flows/explanations/contexts/changes first, then by importance, up to
`report.embed_source_budget_kb` (default 6000 KB) in `.codebase-tutor/config.json`. Other files show as "not embedded".
Symbols are capped by `report.max_symbols_indexed` (default 30000); the file graph shows ≤ `max_graph_nodes` per view.

## Language switching

All languages are embedded; the selector switches UI and explanation text instantly without rebuilding the index.
`--lang` sets the default and the language of `report.md`. To add a language, add `scripts/codebase_tutor/i18n/<code>.json`
with the same keys (tests enforce parity) and include that code in explanation JSON.
