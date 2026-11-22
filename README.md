# Codebase Tutor

An evidence-driven AI agent skill for understanding unfamiliar — including very large — repositories, preparing safe
contributions, and verifying what a change actually did. Works with Claude Code, OpenAI Codex and Google Antigravity
(Agent Skills format).

**Understand → Explore → Trace → Learn → Modify → Simulate → Verify → Compare → Understand again.**

- A deterministic engine (`scripts/ct.py`, Python, no LLM) indexes the repo with Tree-sitter / Python `ast` into a local
  SQLite knowledge base, incrementally.
- The agent explains, teaches and reviews — and every explanation it saves is validated against exact, hash-checked
  source lines.
- Every claim carries a verification level: *verified in source*, *structurally inferred*, *test verified*,
  *runtime observed*, *partially verified*, *not verified*.
- A standalone interactive HTML report (architecture graph, flow playback, code evidence, learning center,
  contribution center, change analysis, simulation lab) in **English, हिन्दी and Hinglish**.

## Install

Requires Python 3.9+ (and Node only if you use `npx`).

```bash
# Option 1 — skills CLI (installs into your agent's skills folder)
npx skills add Gauravkkaushal/codebase-tutor

# Option 2 — this repo's own installer via npx (after the npm package is published)
npx codebase-tutor install --agent claude        # or: --agent codex | --agent antigravity, --scope project

# Option 3 — from a clone
git clone https://github.com/Gauravkkaushal/codebase-tutor.git
cd codebase-tutor
python scripts/install_skill.py --agent claude --scope user

# Then, once: precise JS/TS parsing (Python analysis needs nothing extra)
pip install -r requirements.txt
```

## Quick start

```bash
# Use it from your agent ("explain this repository"), or run the engine directly:
python scripts/ct.py -C /path/to/repo scan
python scripts/ct.py -C /path/to/repo overview
python scripts/ct.py -C /path/to/repo trace "POST /login" --text
python scripts/ct.py -C /path/to/repo symbol authenticate --text
python scripts/ct.py -C /path/to/repo context authenticate --task "lock account after 5 failures" --text
# …edit code…
python scripts/ct.py -C /path/to/repo changes --text
python scripts/ct.py -C /path/to/repo tests plan authenticate
python scripts/ct.py -C /path/to/repo tests run --yes -- npx --no-install mocha test/acceptance/auth.js   # only after you approve
python scripts/ct.py -C /path/to/repo report --lang hinglish     # -> .codebase-tutor/reports/index.html
```

## What is in this folder

| Path | Purpose |
|---|---|
| `SKILL.md` | The canonical, agent-independent skill instructions |
| `references/` | Mode playbooks loaded on demand (evidence rules, architecture, learning, contribution, change intelligence, simulation, reports, large repos, CLI, explanation schema) |
| `bin/codebase-tutor.js`, `package.json` | `npx codebase-tutor …` launcher (installer + engine) |
| `scripts/ct.py`, `scripts/codebase_tutor/` | The engine (inventory, detection, parsers, resolution, store, evidence, flows, context, snapshots, changes, testing, runtime tracers, explanations, report) |
| `assets/report/` | HTML/CSS/JS report app + vendored Cytoscape.js (MIT) |
| `adapters/` | Install/permission notes per agent |
| `docs/` | Product spec, technical architecture, competitor analysis, roadmap, validation results |
| `tests/` | 28 automated tests with fixture repos (incl. a real-browser report test) + `acceptance_test.py` (Definition of Done, run against an Express clone) |

## Safety model

No repository code runs without `--yes`, and the skill requires the agent to show the command and get your approval
first. `.env` values are never read; obvious secrets are redacted in excerpts and reports. Generated data stays in
`<repo>/.codebase-tutor/` (it ships its own `.gitignore`; explanations and config can be committed).

## Honest limitations (v0.1)

- Symbol-level analysis for Python, JavaScript, TypeScript, TSX only; other languages are inventoried, not parsed.
- Static call resolution is heuristic beyond imports/lexical scope; 37–71% of call sites stay unresolved on real repos
  (reported per step, never drawn as verified).
- DI/decorator frameworks (NestJS, Spring), `register_blueprint(url_prefix=…)`, FastAPI `include_router(prefix=…)`
  are not wired yet.
- Node runtime tracing sees only calls through repo module exports (CommonJS); marked experimental.
- Not yet run inside Codex/Antigravity, on React/Next.js repos, or with real learners — see `docs/VALIDATION.md`.

MIT licensed.
