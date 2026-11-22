# TASKS

Legend: [x] done · [~] MVP / partial · [ ] not started

## Phase 0 — Research & specification
- [x] Competitor research (Understand Anything, DeepWiki, RepoPrompt, CodeGraph-class tools, Sourcegraph, explorer skills) → `docs/COMPETITOR_ANALYSIS.md`
- [x] Agent skill formats (Agent Skills spec, Claude Code, Codex, Antigravity)
- [x] `docs/PRODUCT_SPEC.md`, `docs/TECHNICAL_ARCHITECTURE.md`, `docs/IMPLEMENTATION_ROADMAP.md`

## Phase 1 — Repository intelligence MVP
- [x] Inventory (git-aware), roles, languages, hashing, exclusions, secret handling
- [x] Stack detection with file:line evidence; entry points; monorepo; CI; containers
- [x] Tree-sitter JS/TS/TSX extractor (+ regex fallback); Python `ast` extractor
- [x] Imports (CJS/ESM/Python, tsconfig paths, workspaces), exports, bindings
- [x] Call resolution with labels; builtins/external separated from unresolved
- [x] Routes: Express-style, mounts, Flask/FastAPI (+prefixes), Django urlpatterns, Next.js file routes
- [x] SQLite knowledge store; snapshots with content-addressed blobs; git metadata
- [x] Evidence excerpts, highlights, redaction, registered refs

## Phase 2 — Learning & evidence
- [x] Overview, hubs, cycles, orphans, learning path, limitations
- [x] Symbol cards, callers/callees, deps, tests-for ranking with signals
- [x] Static flow tracing with branches/outcomes/guards
- [x] Explanation schema + validation + staleness/relocation; citation checker
- [x] SKILL.md + references (explanation framework, levels, checkpoints)

## Phase 3 — Interactive reports
- [x] report.md (localised) + standalone HTML (8 sections), offline, deep links
- [x] Architecture explorer (Cytoscape), flow playback with lanes + synced code, code explorer
- [x] Language switch en/hi/hinglish without re-index; i18n parity test
- [x] Real-browser test (Playwright + Chrome)

## Phase 4 — Contribution workflow
- [x] `ct context` with coverage table; readiness checklist; plan/review explanation types
- [ ] Issue/PR fetching helper (currently done by the agent with `gh`/web tools)

## Phase 5 — Persistent knowledge & change intelligence
- [x] Hash-incremental, resumable scans; auto-refresh on query
- [x] Snapshot / git-ref baselines; symbol + behaviour + contract diffs; impact; risks
- [ ] Persist per-snapshot symbol tables for history browsing without re-parsing

## Phase 6 — Simulation lab
- [x] L1 inferred scenarios; L2 approval-gated test runs (pytest/jest/vitest/mocha/generic)
- [~] L3 runtime tracing (Python full, Node CommonJS exports only)
- [ ] Automated before/after simulation in a temporary git worktree
- [ ] HTTP request-lifecycle capture for running servers

## Phase 7 — Multilingual & cross-agent
- [x] English, Hindi, Hinglish
- [x] Installer + adapters for Claude Code, Codex, Antigravity
- [ ] End-to-end trial inside Codex and Antigravity

## v0.3 — Visual report
- [x] `dataflow.system_map`: layered components + storage/external systems (DB, cache, session, files, queues,
      auth, email, cloud, templates) with call/import evidence on every edge
- [x] Data Flow tab: animated system map, packets per edge kind, evidence details, flow replay on the map
- [x] Flow player stage: animated packet through client → files → callee files → storages, outcome colours
- [x] Overview hero with count-up stats + mini system map; view transitions; reduced-motion support
- [x] i18n keys for all new UI in en/hi/hinglish; browser + engine tests

## Next
- [ ] Go / Java / Rust / C# extractors
- [ ] Type-aware TS resolution (compiler API helper); optional SCIP import
- [ ] NestJS / Spring / Django CBV / `register_blueprint` / `include_router` wiring
- [ ] Validate on React, Next.js and a large TS monorepo
- [ ] Learner study (protocol in `docs/VALIDATION.md`)
