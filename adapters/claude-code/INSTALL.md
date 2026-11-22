# Claude Code

Claude Code skills follow the Agent Skills standard (`SKILL.md` with YAML frontmatter + supporting files) and are
discovered from `~/.claude/skills/<name>/` (all projects) or `<project>/.claude/skills/<name>/` (one project, can be
committed). Plugins can also ship skills under `<plugin>/skills/`.

## Install
```bash
python scripts/install_skill.py --agent claude --scope user            # or --scope project --project /path/to/repo
pip install -r ~/.claude/skills/codebase-tutor/requirements.txt         # tree-sitter for JS/TS
```
Use `--link` to symlink a git checkout instead of copying (updates with `git pull`).

## Invoke
Type `/codebase-tutor <task>` (e.g. `/codebase-tutor how does login work here?`) or just ask naturally. The text after the command reaches the skill as its task. DeepSeek: see `docs/USE_WITH_ANY_AI.md`. Claude loads `SKILL.md`, then reads `references/*.md` on demand.

## Permissions
The skill runs `python <skill>/scripts/ct.py …` through Bash. Read-only commands (`scan`, `overview`, `symbol`,
`trace`, `changes`, `report`, …) write only to `<repo>/.codebase-tutor/`. Commands that execute repository code
(`ct tests run --yes`, `ct runtime --yes`) must be approved by you in chat first; keep them out of any auto-allow list.
Optional `.claude/settings.json` allow rule for the safe subset:
```json
{"permissions": {"allow": ["Bash(python *codebase-tutor/scripts/ct.py -C * scan*)", "Bash(python *codebase-tutor/scripts/ct.py -C * overview*)"]}}
```
(The `allowed-tools` frontmatter field is intentionally not set, so Claude Code's normal permission prompts apply.)

## Notes
- Claude Code-only frontmatter (`context: fork`, `model`, hooks) is not used, keeping the skill portable.
- Subagents: for huge monorepos, Claude may fan out reads per package; the engine index is shared through the repo's `.codebase-tutor/`.
