# Simulation & verification lab (Mode G)

Three levels, always labelled, never mixed.

## Level 1 — source-inferred (`structurally-inferred`)

`ct trace <target> [--depth N] [--title T] --text`
Targets: `"METHOD /path"` (uses detected routes, applies mount prefixes), a symbol (`login`, `User.findByEmail`,
`file.js#name`), or `file:line`. Output: ordered steps (route registration, mounts, middleware dispatch, function
entry, branch points, calls with resolution, library calls, returns/throws/responses with success/failure outcome),
plus `outcomes`: terminal results with the nearest guarding conditions. Saved to `knowledge/flows/<id>.json` and
playable in the report's Flow Explorer.

Use it to build scenarios for the user ("valid credentials", "unknown user", "wrong password", "missing input") by
mapping each scenario to the outcome and its guard conditions. Say clearly this is reconstructed, not observed.

## Level 2 — test-backed (`test-verified`)

1. `ct tests detect` – runners (jest, vitest, mocha, ava, tap, node --test, pytest, go, cargo) and whether deps are installed.
2. `ct tests plan <symbol|file>` – ranked related tests + ready commands that reuse the project's own test script options.
3. Show the command, explain what it executes, ask for approval.
4. `ct tests run --yes [--label L] -- <command…>` – runs with a timeout in the repo, adds a structured reporter
   (pytest junit, jest/vitest json, mocha json), records per-test pass/fail/skip, commit and dirty flag in
   `runs/tests/<id>/result.json`.
Only executed tests are reported. Failing tests are reported as failing — never paraphrased as "mostly works".
Uncovered scenarios: compare Level-1 outcomes with test names/files and say which outcomes have no test.

## Level 3 — runtime instrumentation (`runtime-observed`, experimental)

`ct runtime --yes [--label L] -- <command…>` (approval required)
- Python: injected `sitecustomize` + `sys.setprofile` records call/return of functions defined in the repo (not
  site-packages), per process, capped at 200k events.
- Node (CommonJS): `--require` hook wraps functions exported by repo modules (not `node_modules`) in transparent
  Proxies and records call/return/throw with depth and timing. Internal calls that bypass module exports and ESM
  modules are **not** observed.
Results map events to indexed symbols and appear in the Simulation Lab (top functions, throw counts, event sequence).
Prefer running a focused test file under the tracer rather than a long-running server.

## Before/after comparison

Run the same test command before and after a change (two labelled runs) and compare counts/failures; run `ct changes`
for the static side. (Automated worktree-based before/after simulation is on the roadmap.)

## Safety

Never run without approval; explain potentially destructive commands; prefer isolated environments (containers,
venvs); never point at production services or real credentials; never expose env values; preserve the user's work.
