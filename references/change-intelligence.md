# Change intelligence (Mode F)

`ct changes` compares the working tree against a baseline and writes
`.codebase-tutor/knowledge/changes/<timestamp>.json` (+ `latest.json`, shown in the report).

Baselines:
- `--since last` (default): the most recent snapshot that differs from the current tree (i.e. "since the previous
  analysis"). Snapshots are created automatically by `ct scan` when files changed; they store a manifest and
  content-addressed blobs, so uncommitted states can be compared too.
- `--since <snapshot-id>`: any snapshot from `ct snapshots`.
- `--since git:<ref>`: a branch, tag or commit (`git:main`, `git:HEAD~3`), including untracked files.

The engine auto-rescans before comparing.

## What it reports

- **Files**: added / modified / deleted / renamed (git), line counts, unified diff (budgeted).
- **Symbols** (re-parsing old and new versions with the same parsers): added, removed, modified (body hash),
  moved-only, signature changes, exported flag.
- **Behaviour signals** per modified symbol: conditions added/removed, exits (return/throw/raise/respond) added/removed,
  calls added/removed, HTTP status codes before → after, routes reaching it.
- **Contracts**: imports, exports, routes, env-var names added/removed; dependency manifest changes.
- **Impact**: callers up to distance 3 via resolved edges, impacted modules, tests to run (ranked), possibly broken
  references to removed symbols, and a **completeness note** (unresolved calls sharing the changed names).
- **Risks**: contract-change, removed-export, security-sensitive, behaviour-change-without-test-change, missing-tests,
  route-change, new-config, dependency-change (high / medium / low).

## How to present it

1. **Code diff** – the actual lines (short), with what changed.
2. **Behaviour diff** – "Before: … After: …" for each signal; new edge cases; removed functionality; compatibility.
3. **Architecture impact** – callers by distance (cite), routes affected, contract changes, downstream effects,
   regression areas, and the completeness note verbatim.
4. **Review** – blocking issues first; then missing tests; then suggestions. Every point cites evidence.
5. Offer to run the suggested tests (approval). Results become `test-verified` evidence only if they pass.

Static comparison is not execution: always say so when behaviour matters.
