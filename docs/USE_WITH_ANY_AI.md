# Use Codebase Tutor from any AI coding tool

One install, then type the skill name plus your task. The AI loads `SKILL.md`, runs the engine
(`scripts/ct.py`) and answers with `file:line` evidence.

## 1. Install once

```bash
# from a clone of this repo (Windows: use `python`; macOS/Linux: `python3`)
python scripts/install_skill.py --agent all
python -m pip install -r requirements.txt        # precise JS/TS parsing (once per machine)

# or, after the npm package is published
npx codebase-tutor install --agent all

# or with the open skills CLI
npx skills add Gauravkkaushal/codebase-tutor
```

`--agent all` copies the skill to:

| Folder | Read by |
|---|---|
| `~/.claude/skills/codebase-tutor` | Claude Code (and DeepSeek / other models run through Claude Code), OpenCode |
| `~/.agents/skills/codebase-tutor` | OpenAI Codex, OpenCode |
| `~/.gemini/config/skills/codebase-tutor` | Google Antigravity (App and CLI) |

Per-project instead of per-user: `--scope project --project <repo>` (writes `.claude/skills/` and `.agents/skills/`
inside the repo, so teammates get it through git). Update later with `--force`; remove with `--uninstall`.

Restart the AI tool after installing.

## 2. Use it — same skill, each tool's own syntax

Open the project you want to understand, then:

| Tool | Type |
|---|---|
| Claude Code | `/codebase-tutor how does login work here?` |
| Google Antigravity | `/codebase-tutor explain the architecture` |
| OpenAI Codex | `$codebase-tutor trace POST /api/orders` (Codex invokes skills with `$`, or pick it from `/skills`) |
| OpenCode | `/codebase-tutor what did my last change break?` (or just ask; the agent loads the skill itself) |
| DeepSeek | Run DeepSeek inside Claude Code or OpenCode (below), then use that tool's syntax |

The text after the skill name is the task. With no task (`/codebase-tutor` alone) it scans the repo and gives an
overview plus a learning path. Hindi or Hinglish tasks are answered in that language.

Examples:

```text
/codebase-tutor
/codebase-tutor is repo ka architecture beginner level pe samjhao
/codebase-tutor trace "POST /login" and show the exact lines for each step
/codebase-tutor who calls res.status and which tests cover it?
/codebase-tutor I want to fix https://github.com/org/repo/issues/123 — what do I need to read first?
/codebase-tutor what did my changes break?
/codebase-tutor make an interactive HTML report in Hinglish
```

All tools also pick the skill **automatically** when you ask something that matches its description
("explain this codebase", "how does X work here"), without typing the command.

## 3. DeepSeek

DeepSeek is a model, not an agent app. Use it through an agent that supports skills:

**Claude Code + DeepSeek** (DeepSeek provides an Anthropic-compatible endpoint):

```powershell
# Windows PowerShell — current terminal only; never commit your key
$env:ANTHROPIC_BASE_URL="https://api.deepseek.com/anthropic"
$env:ANTHROPIC_AUTH_TOKEN="<your DeepSeek API key>"
$env:ANTHROPIC_MODEL="deepseek-v4-pro"
claude
```
```bash
# macOS / Linux
export ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
export ANTHROPIC_AUTH_TOKEN=<your DeepSeek API key>
export ANTHROPIC_MODEL=deepseek-v4-pro
claude
```
Then `/codebase-tutor <task>` as usual. Check DeepSeek's current model names in their docs.

**OpenCode + DeepSeek**: in OpenCode run `/connect`, choose DeepSeek, pick the model with `/models`; the skill is
already discovered from `~/.claude/skills` / `~/.agents/skills`.

## 4. Any other agent (Cursor, Copilot, Gemini CLI, Aider, …)

If the tool supports Agent Skills, point it at the folder above. If it does not, it can still use the engine:
tell it "Read `<skill>/SKILL.md` and follow it for this task: …" — everything the skill needs is a shell and Python.

## 5. Troubleshooting

| Symptom | Fix |
|---|---|
| Command not in the `/` menu | Restart the tool; check the folder above contains `SKILL.md`; run the installer again with `--force` |
| "python not found" | Install Python 3.9+; on Windows tick "Add to PATH" or use the `py -3` launcher |
| JS/TS answers say "heuristic" | `python -m pip install -r requirements.txt` |
| Tool asks before running `ct.py` | Normal: approve read-only commands (`scan`, `overview`, `trace`…). Test/runtime commands always need your yes. |
