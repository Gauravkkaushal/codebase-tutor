# Product Specification — Codebase Tutor

Version 0.1 (first meaningful release). Status labels in this document: **Shipped**, **MVP** (works, limited),
**Planned**.

## 1. Problem

A developer facing an unfamiliar repository needs to (a) find the code responsible for a behaviour, (b) follow it
across files, (c) understand why it is built that way, (d) change it safely, and (e) know what the change did.
Today they grep, read, guess, and ask. AI summaries help with (a) but often hallucinate paths and relationships,
and rarely help with (c)–(e). Developers who let AI answer for them also tend to learn less, so a tool that
*replaces* reading makes the problem worse.

## 2. Product principle

> Make developers capable of understanding the codebase themselves.
> Understand → Explore → Trace → Learn → Modify → Simulate → Verify → Compare → Understand again.

Three non-negotiables:
1. **Evidence or silence.** Every repository-specific claim points to an exact, hash-checked line range, or is
   explicitly labelled as inferred / unverified.
2. **Honest verification levels.** `verified-source`, `structurally-inferred`, `test-verified`, `runtime-observed`,
   `partially-verified`, `not-verified`. A static guess is never shown as an observed run; a test is never shown
   as passing unless it ran and passed.
3. **Teach, then let them do.** Layered explanations, checkpoints, and a learning path; the developer stays in charge.

## 3. Users and jobs

| User | Primary job | Key modes |
|---|---|---|
| CS student / intern | "Help me understand how this project works" | A, B, D (beginner) |
| Junior dev joining a team | "Where is X, how does a request flow?" | A, B, C, D |
| OSS contributor | "Can I fix issue #123 safely?" | E, F, G |
| Language/framework switcher | "Explain the concepts in terms I know" | B (concept layer) |
| Engineer on legacy code | "What breaks if I change this?" | C, F, G |

## 4. Modes and scope of this release

| Mode | What the user gets | Status |
|---|---|---|
| A. Codebase understanding | Stack, package managers, build/CI, monorepo, entry points, env-var *names*, routes, DB/auth/external deps, tests, generated/vendor exclusion, module dependency graph, cycles, orphans, coverage report (analyzed / partial / skipped / failed / excluded) | **Shipped** (JS/TS/Python full; other languages inventory-only) |
| B. Deep dive & learning | Agent explains at Beginner / Developer / Deep / Contribution depth using the explanation framework; engine supplies symbols, callers, callees, evidence | **Shipped** (agent-authored content, engine-verified) |
| C. Evidence engine | `evidence` excerpts with line numbers + highlights, stored refs with content hash, `verify` detects stale refs, citation checker for Markdown | **Shipped** |
| D. Interactive report | `report.md` + standalone `index.html`: Overview, Architecture Explorer, Flow Explorer (playback), Code Evidence Explorer, Learning Center, Contribution Center, Change Analysis, Simulation Lab; en / hi / Hinglish | **Shipped** |
| E. Contribution guide | `context` command: implementation, callers, callees, imports, routes, tests, env vars, config, coverage table; plan + checklist written by agent | **Shipped** |
| F. Change intelligence | Snapshot vs working tree or vs git ref: file / symbol / signature / import / route / dependency / env-var diffs, behaviour signals, affected callers (transitive), routes and tests, incompleteness notes | **Shipped** |
| G. Simulation lab | L1 static flows with branches (inferred); L2 approval-gated test runs with parsed results (pytest, jest, mocha, vitest, generic); L3 runtime tracing (Python, Node) | L1/L2 **Shipped**, L3 **MVP (experimental)** |
| Persistence | `.codebase-tutor/` with SQLite index, snapshots (content-addressed blobs), flows, explanations, test runs, traces | **Shipped** |
| Multilingual | UI + templated text in en/hi/hinglish; explanation content per language; switch without re-index | **Shipped** |
| Cross-agent | Canonical skill + adapters for Claude Code, Codex, Antigravity | **Shipped** (docs + layout; not tested inside Codex/Antigravity) |
| Precise refs via SCIP/LSP | Import external precise indexes | **Planned** |
| Go/Java/Rust/C# symbol extraction | Tree-sitter grammars exist; extractors not written | **Planned** |
| Learner study | Before/after comprehension measurement | **Planned** (protocol written) |

## 5. Key user flows

1. **First run.** "Explain this repo." → agent runs `ct init` + `ct scan` → reads `ct overview` → explains purpose,
   stack, structure, entry points with evidence → offers learning path → optionally `ct report`.
2. **Feature deep dive.** "How does login work?" → `ct search login` → `ct symbol` / `ct trace` → agent explains
   with `ct evidence` excerpts → saves explanation JSON (`ct explain add`) → flow appears in report with playback.
3. **Contribution.** Issue URL → agent reads issue → `ct context <target>` → coverage table → concepts → plan →
   user implements → `ct changes` → `ct tests plan` → user approves → `ct tests run --yes` → review.
4. **Second run.** `ct scan` re-parses only changed files, records a snapshot, and `ct changes --since last`
   reports what moved; stale evidence is flagged in the report.

## 6. Non-functional requirements

- Never read entire repo into the model; engine answers structural questions from the index.
- Default exclusions: VCS dirs, dependency dirs, build output, minified/bundled files, lockfiles, binaries, files > 1 MB.
- Incremental and resumable: per-file content hashes; batches committed to SQLite; interrupted scans resume.
- Safety: no repository code executed without explicit `--yes` (the agent must ask the user first); `.env` values
  never read or emitted; obvious secrets redacted in excerpts; generated data confined to `.codebase-tutor/`.
- Report works offline from `file://`, no CDN; one vendored library (Cytoscape.js, MIT) for graph layout.
- Python ≥ 3.9; Tree-sitter wheels optional (heuristic fallback for JS/TS with lower confidence).

## 7. Success measures

- Evidence accuracy: 100% of emitted line references resolve to the cited text at the analysed commit.
- Zero fabricated test results (enforced by design: results only from executed runs).
- Benchmark rubric (see `VALIDATION.md`) on Express, Flask and Django.
- Learner outcomes (time to locate code, ability to trace, ability to make and explain a change) — planned study.
