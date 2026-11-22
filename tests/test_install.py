"""Installer: every supported tool gets a valid copy at its documented path; update, project scope, uninstall."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(home, *args):
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home))
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "install_skill.py"), *args],
                          capture_output=True, text=True, env=env)


def test_install_all_user_scope(tmp_path):
    r = run(tmp_path, "--agent", "all")
    assert r.returncode == 0, r.stderr
    for rel in (".claude/skills", ".agents/skills", ".gemini/config/skills"):
        skill = tmp_path / rel / "codebase-tutor"
        assert (skill / "SKILL.md").exists() and (skill / "scripts" / "ct.py").exists()
        assert not (skill / "tests").exists()
        out = subprocess.run([sys.executable, str(skill / "scripts" / "ct.py"), "--version"], capture_output=True, text=True)
        assert out.stdout.strip() == "0.2.0"
    assert "/codebase-tutor <task>" in r.stdout and "$codebase-tutor <task>" in r.stdout


def test_update_requires_force_and_aliases(tmp_path):
    run(tmp_path, "--agent", "claude")
    assert "exists" in run(tmp_path, "--agent", "claude").stdout
    r = run(tmp_path, "--agent", "deepseek,opencode", "--force")
    assert "[claude] installed" in r.stdout and "[opencode] installed" in r.stdout
    assert (tmp_path / ".config/opencode/skills/codebase-tutor/SKILL.md").exists()


def test_project_scope_and_uninstall(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    r = run(tmp_path, "--agent", "all", "--scope", "project", "--project", str(proj))
    assert (proj / ".claude/skills/codebase-tutor/SKILL.md").exists()
    assert (proj / ".agents/skills/codebase-tutor/SKILL.md").exists()
    assert r.stdout.count("installed ->") == 2  # codex + antigravity share .agents/skills
    run(tmp_path, "--agent", "all")
    run(tmp_path, "--agent", "all", "--uninstall")
    assert not list(tmp_path.glob(".*/**/codebase-tutor/SKILL.md"))


def test_unknown_agent_rejected(tmp_path):
    assert run(tmp_path, "--agent", "bogus").returncode == 2


def test_skill_md_tells_agent_to_take_task_from_command():
    text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "/codebase-tutor <task>" in text and "$codebase-tutor <task>" in text
    front = text.split("---")[1]
    import yaml
    meta = yaml.safe_load(front)
    assert meta["name"] == "codebase-tutor" and len(meta["description"]) <= 1024
    assert set(meta) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
