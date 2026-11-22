# Google Antigravity

Antigravity skills are directories with a `SKILL.md` (YAML frontmatter `name`, `description`) and optional scripts and
resources. Workspace skills live in `<workspace-root>/.agents/skills/<skill>/` (the older `.agent/skills/` is still
read); global skills live in `~/.gemini/config/skills/<skill>/`, shared by the Antigravity App and CLI (the legacy
`~/.gemini/antigravity/skills/` is still read).

## Install
```bash
python scripts/install_skill.py --agent antigravity --scope project --project /path/to/workspace   # -> .agents/skills/codebase-tutor
python scripts/install_skill.py --agent antigravity --scope user                                   # -> ~/.gemini/config/skills/codebase-tutor (App + CLI)
pip install -r <installed path>/requirements.txt
```

## Invoke
Type `/codebase-tutor <task>` — Antigravity turns every skill into a slash command — or ask naturally and the agent picks it from its description.

## Permissions
Antigravity's terminal/auto-execution policy applies. Keep auto-execution off (or "request review") for commands
containing `ct.py tests run` or `ct.py runtime` — they execute repository code and are approval-gated by the skill.

## Differences
- Same `SKILL.md`; scripts are invoked as black boxes (`python scripts/ct.py --help`), which matches Antigravity's
  guidance for skills with scripts.
- Not yet tested end-to-end inside Antigravity by the author (documented in docs/VALIDATION.md).
