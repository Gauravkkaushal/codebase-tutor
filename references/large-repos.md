# Large repositories and monorepos

Measured on this machine (see `docs/VALIDATION.md`): Django (7,032 files, ~532k Python lines) first scan ≈ 9 s,
unchanged re-scan ≈ 0.35 s, index ≈ 91 MB SQLite.

## Strategy

1. Never read broadly. Ask the index (`overview`, `search`, `graph`, `symbol`, `callers`, `trace`) and read only cited ranges.
2. Scope when needed: add `exclude` globs in `.codebase-tutor/config.json` (e.g. `"docs/**"`, `"**/fixtures/**"`),
   or `include` to re-admit a default-excluded folder. Re-run `ct scan --full` after changing scope.
3. Monorepos: `overview.monorepo` lists packages; workspace package names resolve to their local folders, so
   cross-package imports become real edges. Explain the package map first, then zoom into one package.
4. Use `ct graph --depth 1` for the big picture, `--depth 3` to zoom; in the HTML report double-click a module to see its files.
5. Delegate broad sweeps to parallel subagents only if your agent supports them and the user agrees; ask each for
   cited findings, not file dumps.
6. Budget the report: lower `report.embed_source_budget_kb` for very large repos; the report stays usable because
   referenced files are embedded first.

## Incremental behaviour

- File hashes (size+mtime fast path), per-file fact replacement, batch commits every 200 files → interrupted scans
  resume where they stopped.
- Global resolution pass after changes (cheap compared with parsing).
- Query commands auto-refresh when the git working tree fingerprint changed (`--no-refresh` to skip).
- Snapshots store blobs only for new content hashes (budget `snapshot.max_blob_store_mb`, default 500 MB).

## Known scale limits

- Unresolved-call ratios are high for heavily object-oriented/typed code (method calls on typed variables). This is
  reported, not hidden. Type-aware TS resolution and SCIP import are on the roadmap.
- Very deep nesting falls back to partial facts for that file (reported).
