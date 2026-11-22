# Validation & benchmarking — v0.1 (2026-11-20)

Everything below was run in the build environment (Linux, Python 3.13, Node 22, Chrome) against real clones.
Numbers are measurements, not estimates. Where something was not measured, it says so.

## 1. Automated tests

`python -m pytest` → **28 passed** (parsers, scan/incremental, resolution, routes/mounts, flows, evidence + redaction,
explanations + staleness, citations, change intelligence vs snapshot and git ref, contribution context, approval gate,
real pytest execution incl. a deliberately failing run, Python runtime tracing, report generation in 3 languages,
secret exclusion, i18n parity, and a real-browser test of the HTML report via Playwright + Chrome with zero console errors).

## 2. Scale and speed

| Repo | Files | Parsed lines (langs) | analysed/partial/failed | Full scan | No-change re-scan | Call sites | verified | inferred | external+builtin | unresolved |
|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| expressjs/express | 216 | 22,049 (JS) | 142/0/0 | 0.7 s | 0.12 s | 11,666 | 3% | 12% | 43% | 42% |
| pallets/flask | 236 | 18,392 (Python) | 83/0/0 | 0.5 s | 0.11 s | 3,961 | 18% | 14% | 30% | 37% |
| honojs/hono (TS, pnpm workspace) | 573 | 95,726 (TS/TSX/JS) | 433/8/0 | 1.7 s | 0.13 s | 45,723 | 14% | 5% | 10% | 71% |
| django/django | 7,032 | 537,998 (Python/JS) | 2,984/3/0 | 9.2 s | 0.37 s | 193,754 | 22% | 8% | 14% | 56% |

Django index: 91 MB SQLite; snapshot blobs 31 MB; report `data.js` 16 MB, generated in 1.9 s. Peak RSS of the scan
process ≈ 112 MB. "Unresolved" counts every call site the engine could not bind statically (e.g. `self.assertEqual`
inherited from a framework class, method calls on typed objects in TS, supertest chains). They are reported, never drawn
as edges.

## 3. Correctness spot checks (manually verified against source)

| # | Check | Result |
|---|---|---|
| 1 | Express `res.status` extracted at `lib/response.js:65-77`; flow shows the two `throw`s and `return this` at the right lines | correct |
| 2 | Express `POST /login` (examples/auth) flow: guard `!req.body` → 400, `authenticate()` resolved locally, `next(err)` failure path, success/failure redirects; `req.session.regenerate` honestly marked unresolved | correct |
| 3 | Express mounted router: `GET /api/v1/users` resolved through `app.use('/api/v1', require('./controllers/api_v1'))` | correct (after fixing a re-resolution bug, see §6) |
| 4 | Django `get_object_or_404`: 15 resolved callers. `grep` finds 20 textual occurrences outside the definition/`aget_`/docs; the 5 not resolved are all strings/docstrings | 15/15 real call sites found, 0 false positives |
| 5 | Flask tutorial `POST /auth/register` with Blueprint `url_prefix="/auth"`; `get_db()` resolved into `flaskr/db.py`; `IntegrityError` handler shown as failure path | correct (after adding Blueprint prefixes, see §6) |
| 6 | Express change (added `if (code === 418) throw …` to `res.status`): detected condition + exit added, 208 impacted symbols by distance, tests to run led by `test/res.status.js`, risk "behaviour change without test change" | correct; change reverted |
| 7 | Express change in `examples/auth` login handler: behaviour signals, route reaching (`POST /login`), security-sensitive risk, `test/acceptance/auth.js` suggested | correct |
| 8 | Explanation validator: invented path `src/nope.js` and range `130-999` rejected; after a code edit, 8 refs valid, 1 moved (new range given), 1 stale | correct |
| 9 | `.env` with a fake secret never appears in `data.js`; `secret: 'shhhh…'` literal shown as `«redacted»` in excerpts | correct |

## 4. Execution evidence (approval-gated runs)

| Run | Result |
|---|---|
| Express `mocha test/res.status.js test/res.sendStatus.js` via `ct tests run --yes` | 19 passed, 0 failed (per-test results parsed from mocha JSON) |
| Express `mocha test/acceptance/auth.js` (with the login change applied) | 10 passed |
| Express runtime trace of `test/res.status.js` (Node hook) | 988 events, 13 functions; `res.status` 16 calls / 7 throws, `app.handle` 16 calls — matches the test file's invalid-status cases |
| Fixture pytest run, then a deliberately broken `check_password` | 3 passed → 1 failed, failing test named correctly |
| Fixture Python runtime trace | `Session.refresh` → `Session.validate` observed once each |

Without `--yes`, both `tests run` and `runtime` returned `needs-approval` and executed nothing.

## 5. Report

Generated for Express in en / hi / hinglish; opened in Chrome via Playwright: all 8 sections render, graph canvas
draws, flow player steps and syncs code, deep links highlight the exact range, language switch works, mobile width
(390 px) collapses navigation. No console errors (one Cytoscape warning about wheel sensitivity was found and removed).

## 6. Bugs found by validation (all fixed)

1. Class bodies were walked twice (Tree-sitter node identity comparison) → duplicated calls.
2. Re-resolution turned `mount` routes back without targets on the second scan → mount prefixes lost.
3. Missing SQLite indexes made a forced full re-scan of Django take 26.9 s → 9.2 s after indexes.
4. A fresh database failed because an index was declared before its table (caught by the test suite).
5. `return res.status(401).json()` produced duplicated flow steps → merged.
6. Test ranking counted every call row (score inflation) → one signal per file.
7. Flask Blueprint `url_prefix` and FastAPI `APIRouter(prefix=)` were ignored → applied.

## 7. Rubric (provisional, author-assessed — not an independent benchmark)

| Category (weight) | Provisional | Basis |
|---|---:|---|
| Technical correctness (25%) | 80 | All spot checks correct after fixes; dynamic wiring not resolved |
| Evidence accuracy (20%) | 95 | Lines come from parsers and are hash-checked; validator rejects invented refs |
| Beginner comprehension (15%) | not measured | Requires learner study (§8) |
| Execution-flow accuracy (15%) | 70 | Correct where resolved; 37–71% of call sites unresolved, flagged per step |
| Context completeness (10%) | 70 | Callers/tests/routes found; DI/decorator frameworks missing |
| Report usability (5%) | 75 | Browser-tested by the author, no user testing yet |
| Performance (5%) | 90 | 538k lines in 9 s; sub-second incremental |
| Change-impact analysis (5%) | 75 | Symbol/behaviour diff + callers; impact limited to resolved edges |

A weighted total is deliberately **not** reported because one category is unmeasured.

## 8. Not yet validated

- **React and Next.js repositories, and a large TypeScript monorepo beyond Hono** — not run in this session. Next.js
  file routes are implemented but untested on a real Next.js app.
- **Learner study** (beginners before/after). Protocol: give 6–10 learners a task in an unfamiliar repo (e.g. "make
  Express's `res.redirect` reject non-http URLs and add a test"); half with Codebase Tutor, half with editor + search;
  measure time to locate code, accuracy of an architecture explanation (rubric), ability to trace the request (graded
  against `ct trace` + manual key), tests identified, change correctness (tests pass), and an explain-back interview.
- **Inside Codex and Antigravity**: install layouts follow their docs, but the skill was exercised only through the CLI here.
- **Windows/macOS**: written to be portable (pathlib, no shell-specific code) but only run on Linux.
