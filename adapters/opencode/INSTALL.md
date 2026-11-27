# OpenCode (and DeepSeek through OpenCode)

OpenCode discovers Agent Skills in `~/.config/opencode/skills/`, and also in the Claude-compatible
`~/.claude/skills/` and agent-compatible `~/.agents/skills/` folders (plus the same folders inside a project).
So `python scripts/install_skill.py --agent all` is already enough; `--agent opencode` installs an extra copy into
`~/.config/opencode/skills/codebase-tutor` if you only use OpenCode.

## Use
Name the skill in your prompt (e.g. `use codebase-tutor: explain this repo`) or just ask naturally; OpenCode loads the skill with its `skill` tool (installing a skill does not create a `/codebase-tutor` slash command).

## DeepSeek
Run `/connect` in OpenCode, choose DeepSeek and paste your API key, then select the model with `/models`.
The skill is model-independent: the engine does the parsing; the model writes the explanations.
