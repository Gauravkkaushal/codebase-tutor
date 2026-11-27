#!/usr/bin/env python3
"""Install Codebase Tutor into one or more AI coding tools, so `/codebase-tutor <task>` works there.

Examples:
  python scripts/install_skill.py --agent all                      # every supported tool, user-wide
  python scripts/install_skill.py --agent claude                   # Claude Code (also DeepSeek via Claude Code)
  python scripts/install_skill.py --agent codex                    # OpenAI Codex  ($codebase-tutor)
  python scripts/install_skill.py --agent antigravity              # Google Antigravity
  python scripts/install_skill.py --agent opencode                 # OpenCode (also DeepSeek via OpenCode)
  python scripts/install_skill.py --agent all --scope project --project ~/code/myrepo
  python scripts/install_skill.py --agent all --uninstall
"""
import argparse
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
NAME = "codebase-tutor"
HOME = Path.home()

# agent: (user-scope skills dir, project-scope dir relative to the project root, how the user invokes it)
TARGETS = {
    "claude": (HOME / ".claude" / "skills", Path(".claude") / "skills", "/codebase-tutor <task>"),
    "codex": (HOME / ".agents" / "skills", Path(".agents") / "skills", "$codebase-tutor <task>   (or /skills)"),
    "antigravity": (HOME / ".gemini" / "config" / "skills", Path(".agents") / "skills", "/codebase-tutor <task>"),
    "opencode": (HOME / ".config" / "opencode" / "skills", Path(".opencode") / "skills", "name codebase-tutor in your prompt (skill tool)"),
}
ALIASES = {"claude-code": "claude", "deepseek": "claude", "gemini": "antigravity", "openai": "codex"}
# `all` installs to distinct folders only: OpenCode already reads ~/.claude/skills and ~/.agents/skills,
# so a separate OpenCode copy would just duplicate the skill name.
ALL = ["claude", "codex", "antigravity"]
IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache", "tests", ".codebase-tutor",
                                "node_modules", "*.bundle")


def install_one(agent: str, scope: str, project: Path, link: bool, force: bool) -> str:
    user_dir, proj_rel, how = TARGETS[agent]
    base = user_dir if scope == "user" else project / proj_rel
    dest = base / NAME
    if dest.resolve() == SKILL_DIR:
        return f"[{agent}] already running from {dest} (nothing to do) — use: {how}"
    if not link and dest.resolve().is_relative_to(SKILL_DIR):
        # copytree would recurse into its own destination
        return f"[{agent}] FAILED: {dest} is inside the skill source {SKILL_DIR}; use --link or another --project"
    if dest.exists() or dest.is_symlink():
        if not force:
            return f"[{agent}] {dest} exists — re-run with --force to update it"
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    base.mkdir(parents=True, exist_ok=True)
    if link:
        dest.symlink_to(SKILL_DIR, target_is_directory=True)
    else:
        shutil.copytree(SKILL_DIR, dest, ignore=IGNORE)
    if not (dest / "SKILL.md").exists():
        return f"[{agent}] FAILED: {dest / 'SKILL.md'} missing after install"
    return f"[{agent}] installed -> {dest}   use: {how}"


def uninstall_one(agent: str, scope: str, project: Path) -> str:
    user_dir, proj_rel, _ = TARGETS[agent]
    dest = (user_dir if scope == "user" else project / proj_rel) / NAME
    if not (dest.exists() or dest.is_symlink()):
        return f"[{agent}] not installed at {dest}"
    if dest.is_symlink() or dest.is_file():
        dest.unlink()
    else:
        shutil.rmtree(dest)
    return f"[{agent}] removed {dest}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", required=True, help="all | claude | codex | antigravity | opencode | deepseek (comma-separated ok)")
    ap.add_argument("--scope", choices=["user", "project"], default="user")
    ap.add_argument("--project", default=".", help="project root for --scope project")
    ap.add_argument("--link", action="store_true", help="symlink instead of copy (one source of truth)")
    ap.add_argument("--force", action="store_true", help="replace an existing installation (use this to update)")
    ap.add_argument("--uninstall", action="store_true")
    a = ap.parse_args()
    wanted = []
    for part in a.agent.lower().split(","):
        part = part.strip()
        if part == "all":
            wanted += list(TARGETS) if a.uninstall else ALL
        elif part in TARGETS or part in ALIASES:
            wanted.append(ALIASES.get(part, part))
        else:
            print(f"unknown agent '{part}'. choose from: all, {', '.join(TARGETS)}, deepseek", file=sys.stderr)
            return 2
    wanted = list(dict.fromkeys(wanted))
    project = Path(a.project).expanduser().resolve()
    if a.scope == "project":
        # Codex, Antigravity and OpenCode all read <project>/.agents/skills — install it once.
        seen, dedup = set(), []
        for ag in wanted:
            rel = TARGETS[ag][1]
            if rel not in seen:
                seen.add(rel)
                dedup.append(ag)
        wanted = dedup
    failed = False
    for ag in wanted:
        msg = uninstall_one(ag, a.scope, project) if a.uninstall else install_one(ag, a.scope, project, a.link, a.force)
        print(msg)
        failed |= "FAILED" in msg or "re-run with --force" in msg
    if not a.uninstall:
        print("\nOnce per machine, for precise JS/TS parsing:  python -m pip install -r "
              f"\"{SKILL_DIR / 'requirements.txt'}\"")
        print("Restart your AI tool, open a project, and type the command shown above.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
