# Report generation (Mode D)

`ct report [--lang en|hi|hinglish] [--out DIR]` writes (default `.codebase-tutor/reports/`):

| File | Content |
|---|---|
| `report.md` | Readable report in the selected language: overview + stack (with evidence), structure, entry points, hubs, routes, env-var names, learning path, explanations with excerpts, flows, contribution contexts, change analysis, test/runtime results, coverage & limitations. |
| `index.html` + `app.js` + `styles.css` | Standalone interactive app (no server, no CDN). |
| `data.js` | All report data (`window.CT_DATA`), including every language's UI strings. |
| `vendor/cytoscape.min.js` | Graph layout/interaction (MIT, vendored, ~430 KB). Only third-party dependency. |

Sections of the HTML app: Overview · Architecture Explorer (module/file graph from real edges, filters, search, node
details with example edges, drill-down) · Execution Flows (playback: play/pause/prev/next/restart/speed, keyboard:
space/←/→; lane diagram; synchronized source with highlighted line; narration from `flow-notes`; outcomes) · Code
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
