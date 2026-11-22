# Google Antigravity

Antigravity skills are directories with a `SKILL.md` (YAML frontmatter `name`, `description`) and optional scripts and
resources. Workspace skills live in `<workspace-root>/.agents/skills/<skill>/` (the older `.agent/skills/` is still
read); global skills live under the user's Gemini/Antigravity config directory (documented as
`~/.gemini/antigravity/skills/` for the IDE; newer docs for Antigravity 2.0 also mention `~/.gemini/config/skills/` —
check your version's docs).

## Install
```bash
python scripts/install_skill.py --agent antigravity --scope project --project /path/to/workspace   # -> .agents/skills/codebase-tutor
python scripts/install_skill.py --agent antigravity --scope user                                   # -> ~/.gemini/antigravity/skills/codebase-tutor
python scripts/install_skill.py --agent antigravity --dest ~/.gemini/config/skills                  # Antigravity 2.0 global path
pip install -r <installed path>/requirements.txt
```

## Invoke
The agent picks the skill from its description; you can also name it ("use codebase-tutor to …") or use the
slash-command form your Antigravity surface offers.

## Permissions
Antigravity's terminal/auto-execution policy applies. Keep auto-execution off (or "request review") for commands
containing `ct.py tests run` or `ct.py runtime` — they execute repository code and are approval-gated by the skill.

## Differences
- Same `SKILL.md`; scripts are invoked as black boxes (`python scripts/ct.py --help`), which matches Antigravity's
  guidance for skills with scripts.
- Not yet tested end-to-end inside Antigravity by the author (documented in docs/VALIDATION.md).
