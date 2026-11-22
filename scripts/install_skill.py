#!/usr/bin/env python3
"""Copy (or symlink) Codebase Tutor into an agent's skill directory.

Examples:
  python scripts/install_skill.py --agent claude --scope user
  python scripts/install_skill.py --agent codex --scope project --project ~/code/myrepo
  python scripts/install_skill.py --agent antigravity --scope project --project . --link
"""
import argparse
import shutil
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
NAME = "codebase-tutor"
TARGETS = {
    # agent: (user-scope dir, project-scope dir relative to project root)
    "claude": (Path.home() / ".claude" / "skills", Path(".claude") / "skills"),
    "codex": (Path.home() / ".codex" / "skills", Path(".agents") / "skills"),
    "antigravity": (Path.home() / ".gemini" / "antigravity" / "skills", Path(".agents") / "skills"),
}
IGNORE = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", ".pytest_cache", "tests", ".codebase-tutor")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent", choices=sorted(TARGETS), required=True)
    ap.add_argument("--scope", choices=["user", "project"], default="user")
    ap.add_argument("--project", default=".", help="project root for --scope project")
    ap.add_argument("--dest", help="override destination skills directory")
    ap.add_argument("--link", action="store_true", help="symlink instead of copy (keeps one source of truth)")
    ap.add_argument("--force", action="store_true", help="replace an existing installation")
    a = ap.parse_args()
    user_dir, proj_rel = TARGETS[a.agent]
    base = Path(a.dest).expanduser() if a.dest else (user_dir if a.scope == "user" else Path(a.project).expanduser().resolve() / proj_rel)
    dest = base / NAME
    if dest.exists() or dest.is_symlink():
        if not a.force:
            print(f"{dest} exists; re-run with --force to replace it", file=sys.stderr)
            return 1
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    base.mkdir(parents=True, exist_ok=True)
    if a.link:
        dest.symlink_to(SKILL_DIR, target_is_directory=True)
    else:
        shutil.copytree(SKILL_DIR, dest, ignore=IGNORE)
    print(f"installed {NAME} -> {dest}")
    print("next: pip install -r", dest / "requirements.txt", "(tree-sitter for JS/TS; Python analysis needs nothing extra)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
