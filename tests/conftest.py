import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
FIXTURES = Path(__file__).resolve().parent / "fixtures"
CT = [sys.executable, str(ROOT / "scripts" / "ct.py")]


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def make_repo(tmp_path: Path, name: str) -> Path:
    dst = tmp_path / name
    shutil.copytree(FIXTURES / name, dst)
    _git(dst, "init", "-q")
    _git(dst, "config", "user.email", "t@example.com")
    _git(dst, "config", "user.name", "t")
    _git(dst, "add", "-A")
    _git(dst, "commit", "-qm", "init")
    return dst


@pytest.fixture
def js_repo(tmp_path):
    return make_repo(tmp_path, "js_app")


@pytest.fixture
def py_repo(tmp_path):
    return make_repo(tmp_path, "py_app")


def ct(repo, *args, check=True):
    out = subprocess.run(CT + ["-C", str(repo), *args], capture_output=True, text=True)
    if check and out.returncode != 0:
        raise AssertionError(f"ct {args} failed: {out.stderr}\n{out.stdout}")
    try:
        return json.loads(out.stdout)
    except ValueError:
        return out.stdout


@pytest.fixture
def run_ct():
    return ct


@pytest.fixture
def mern_repo(tmp_path):
    return make_repo(tmp_path, "mern_app")
