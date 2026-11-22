# Evidence rules (Mode C)

## Verification levels

| Level | Use when | Typical source |
|---|---|---|
| `verified-source` | You (or the engine) read the exact lines; the relationship is syntactic (definition, import, call to an imported/local name, route registration). | `ct evidence`, `ct symbol`, resolved calls with `resolution=verified-source` |
| `structurally-inferred` | Reasoned from structure but not proven: `this.x()` matched by name, unique-name matches, layer hints from folder names, guard conditions of an outcome, any static flow as a whole. | `resolution=structurally-inferred`, `ct trace` outcomes |
| `test-verified` | A test that exercises the behaviour was **executed** by `ct tests run --yes` and **passed** in a recorded run (commit + dirty flag recorded). | `.codebase-tutor/runs/tests/*/result.json` |
| `runtime-observed` | The call/event appears in a `ct runtime --yes` trace. | `.codebase-tutor/runs/runtime/*/trace.json` |
| `partially-verified` | Part of a multi-step claim is verified, part is not. Say which part. | — |
| `not-verified` | You believe it but have not checked. Prefer checking; otherwise label it and say how to verify. | — |

Never upgrade a label: a static flow stays inferred even if it "obviously" runs; a test that was planned but not run
proves nothing; a test that ran on a dirty tree proves behaviour of that tree only.

## Citation format

`path/from/repo/root.ext:LINE` or `:START-END`, optionally followed by the symbol in backticks.
Cite the lines that prove the claim, not the file header. Paths are always repo-relative.

## Showing code

```
ct evidence src/controllers/auth.controller.js 39-47 --highlight 44-46 --text
```
prints numbered lines with `▶` on the highlighted ones and an evidence id + text hash. Explain *the highlighted
lines specifically*: what they do, why they matter, what happens on each branch. Keep excerpts short (≤ 25 lines);
link to the rest.

For every important component, establish (and cite) where possible: **called by**, **calls**, **receives**,
**returns**, **depends on**, **affects**. `ct symbol <name>` gives callers, callees, control points and tests in one call.

## Staleness

- Every stored evidence reference carries a hash of the exact cited text.
- `ct verify` re-checks all references: `valid`, `moved` (same text found elsewhere — the new range is given),
  `stale` (text changed), `missing`, `out-of-range`.
- Flows store per-step line hashes; the report flags stale steps. Re-run `ct trace` to regenerate.
- When something is stale, re-read the code and rewrite the claim; never just bump line numbers.

## Checking prose

Before giving a long answer or saving Markdown, run `ct verify --file answer.md` (or `--file -` with stdin). It checks
every `path:line` citation exists and is in range, and prints the first line of each cited range so you can eyeball it.

## Secrets

The engine refuses to read `.env*`, key files and binaries, and redacts private keys, AWS/GitHub/OpenAI-style tokens and
`password/secret/token = "..."` literals in excerpts and reports. Environment variables are reported by **name** only.
