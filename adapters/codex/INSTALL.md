# OpenAI Codex

Codex supports the open Agent Skills format: a folder with `SKILL.md` (`name` + `description` required) plus optional
`scripts/`, `references/`, `assets/`. It scans `.agents/skills` from the working directory up to the repository root
(repo scope) and a user-level skills folder; it loads only name/description until a skill is selected
(progressive disclosure).

## Install
```bash
# repository scope (shared with the team via git)
python scripts/install_skill.py --agent codex --scope project --project /path/to/repo   # -> .agents/skills/codebase-tutor
# user scope
python scripts/install_skill.py --agent codex --scope user                              # -> ~/.agents/skills/codebase-tutor
pip install -r <installed path>/requirements.txt
```
Restart Codex if the skill does not appear. Skills can be disabled per path in `~/.codex/config.toml`
(`[[skills.config]] path = ".../SKILL.md"  enabled = false`).

## Invoke
Type `$codebase-tutor <task>` (Codex invokes skills with `$`; you can also pick it from `/skills`), or ask naturally and Codex matches the description. Codex's old `/prompts:` custom prompts are deprecated, so there is no `/codebase-tutor` slash form in Codex.

## Permissions / sandbox
Codex's sandbox may block writing outside the workspace or running subprocesses; the engine writes only to
`<repo>/.codebase-tutor/`. Test and runtime commands require your explicit approval in the conversation (the skill
enforces `--yes` only after you agree) and may additionally trigger Codex approval prompts.

## Differences
- Codex uses `$` to invoke skills explicitly (Claude Code uses `/`).
- No Claude-specific frontmatter is used, so the same `SKILL.md` works unchanged.
- Not yet tested end-to-end inside Codex by the author (documented in docs/VALIDATION.md).
