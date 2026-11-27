"""Repository file inventory: discovery, classification, hashing, exclusions."""
from __future__ import annotations

import fnmatch
import hashlib
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

LANG_BY_EXT = {
    ".py": "python", ".pyi": "python",
    ".js": "javascript", ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".mts": "typescript", ".cts": "typescript", ".tsx": "tsx",
    ".go": "go", ".java": "java", ".kt": "kotlin", ".kts": "kotlin", ".scala": "scala",
    ".rb": "ruby", ".php": "php", ".rs": "rust", ".cs": "csharp", ".swift": "swift",
    ".c": "c", ".h": "c", ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp",
    ".m": "objective-c", ".dart": "dart", ".lua": "lua", ".r": "r", ".ex": "elixir", ".exs": "elixir",
    ".erl": "erlang", ".hs": "haskell", ".clj": "clojure", ".groovy": "groovy", ".vue": "vue",
    ".svelte": "svelte", ".sql": "sql", ".sh": "shell", ".bash": "shell", ".zsh": "shell", ".ps1": "powershell",
    ".html": "html", ".htm": "html", ".css": "css", ".scss": "scss", ".sass": "sass", ".less": "less",
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml", ".ini": "ini", ".cfg": "ini",
    ".xml": "xml", ".md": "markdown", ".mdx": "markdown", ".rst": "rst", ".txt": "text", ".proto": "protobuf",
    ".graphql": "graphql", ".gql": "graphql", ".tf": "terraform", ".ejs": "template", ".hbs": "template",
    ".jade": "template", ".pug": "template", ".jinja": "template", ".j2": "template",
}
CODE_LANGS = {
    "python", "javascript", "typescript", "tsx", "go", "java", "kotlin", "scala", "ruby", "php", "rust",
    "csharp", "swift", "c", "cpp", "objective-c", "dart", "lua", "r", "elixir", "erlang", "haskell",
    "clojure", "groovy", "vue", "svelte", "shell", "powershell", "sql",
}
PARSEABLE_LANGS = {"python", "javascript", "typescript", "tsx"}
NAME_LANG = {"Dockerfile": "docker", "Makefile": "make", "Jenkinsfile": "groovy", "Procfile": "procfile",
             "Gemfile": "ruby", "Rakefile": "ruby", "Vagrantfile": "ruby"}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svgz", ".pdf", ".zip", ".gz", ".tgz",
    ".bz2", ".xz", ".7z", ".rar", ".jar", ".war", ".class", ".so", ".dylib", ".dll", ".exe", ".bin",
    ".o", ".a", ".pyc", ".pyo", ".whl", ".woff", ".woff2", ".ttf", ".otf", ".eot", ".mp3", ".mp4",
    ".mov", ".avi", ".wav", ".ogg", ".webm", ".sqlite", ".db", ".psd", ".ai", ".sketch", ".fig",
}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
             "Cargo.lock", "composer.lock", "Gemfile.lock", "go.sum", "uv.lock", "bun.lockb", "npm-shrinkwrap.json"}
CONFIG_NAMES = {
    "package.json", "tsconfig.json", "jsconfig.json", "pyproject.toml", "setup.py", "setup.cfg",
    "requirements.txt", "Pipfile", "go.mod", "Cargo.toml", "pom.xml", "build.gradle", "settings.gradle",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml", "compose.yaml", "Makefile", "Procfile",
    ".eslintrc", ".eslintrc.json", ".eslintrc.js", ".prettierrc", "babel.config.js", ".babelrc",
    "webpack.config.js", "vite.config.ts", "vite.config.js", "rollup.config.js", "jest.config.js",
    "jest.config.ts", "vitest.config.ts", "pytest.ini", "tox.ini", "manage.py", "Gemfile", "composer.json",
    ".editorconfig", ".gitignore", ".npmignore", ".nvmrc", ".python-version", "next.config.js", "next.config.mjs",
    "nx.json", "turbo.json", "lerna.json", "pnpm-workspace.yaml", "Jenkinsfile", ".gitlab-ci.yml",
}
SECRET_FILE_PREFIXES = (".env",)
SECRET_SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist")
SECRET_NAMES = {"credentials.json", "secrets.json", "id_rsa", "id_ed25519", ".npmrc", ".pypirc", ".netrc"}

TEST_DIR_NAMES = {"test", "tests", "__tests__", "spec", "specs", "testing", "e2e", "integration_tests"}


@dataclass
class FileEntry:
    path: str  # repo-relative POSIX
    size: int
    mtime_ns: int
    lang: str
    role: str  # source|test|config|doc|generated|binary|secret|data|asset
    hash: str = ""
    note: str = ""


@dataclass
class Inventory:
    root: Path
    files: list = field(default_factory=list)
    excluded_dirs: dict = field(default_factory=dict)  # dir -> reason
    excluded_files: dict = field(default_factory=dict)  # reason -> count
    used_git: bool = False

    def by_path(self) -> dict:
        return {f.path: f for f in self.files}


def is_test_path(path: str) -> bool:
    p = PurePosixPath(path)
    name = p.name
    parts = set(p.parts[:-1])
    if parts & TEST_DIR_NAMES:
        return True
    stem = name.split(".")[0]
    return (name.startswith("test_") and name.endswith(".py")) or name.endswith("_test.py") \
        or name.endswith("_test.go") or ".test." in name or ".spec." in name \
        or stem in ("conftest",) or name.endswith("Test.java") or name.endswith("_spec.rb")


def classify(path: str, size: int) -> tuple[str, str]:
    p = PurePosixPath(path)
    name, ext = p.name, p.suffix.lower()
    lang = LANG_BY_EXT.get(ext) or NAME_LANG.get(name) or ("text" if not ext else ext.lstrip("."))
    low = name.lower()
    if low in SECRET_NAMES or (low.startswith(SECRET_FILE_PREFIXES) and not low.endswith(SECRET_SAFE_SUFFIXES)
                               and low != ".envrc.example"):
        return lang, "secret"
    if ext in BINARY_EXT:
        return lang, "binary"
    if name in LOCKFILES or name.endswith((".min.js", ".min.css", ".map", ".bundle.js", "_pb2.py", "_pb2_grpc.py",
                                            ".pb.go", ".generated.ts", ".generated.js", ".g.dart")):
        return lang, "generated"
    if name in CONFIG_NAMES or p.parts[0:2] == (".github", "workflows") or name.endswith((".config.js", ".config.ts", ".config.mjs", ".config.cjs")):
        return lang, "config"
    if lang in ("markdown", "rst") or name.lower().startswith(("readme", "changelog", "history", "contributing", "license")):
        return lang, "doc"
    if lang in CODE_LANGS:
        return lang, "test" if is_test_path(path) else "source"
    if lang in ("json", "yaml", "toml", "ini", "xml"):
        return lang, "config"
    if lang in ("html", "css", "scss", "sass", "less", "template"):
        return lang, "asset"
    return lang, "data"


def _match_any(path: str, patterns: list) -> bool:
    return any(fnmatch.fnmatch(path, pat) or fnmatch.fnmatch(path + "/", pat) for pat in patterns)


def _git_files(root: Path) -> list | None:
    try:
        out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "-co", "--exclude-standard"],
                             capture_output=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def scan_inventory(root: Path, cfg: dict, previous: dict | None = None) -> Inventory:
    """previous: {path: (size, mtime_ns, hash)} for hash reuse."""
    root = Path(root).resolve()
    inv = Inventory(root=root)
    excluded_dir_names = set(cfg.get("default_excluded_dirs", []))
    include, exclude = cfg.get("include", []), cfg.get("exclude", [])
    max_bytes = int(cfg.get("max_file_bytes", 1_000_000))
    previous = previous or {}

    candidates = _git_files(root)
    if candidates is not None:
        inv.used_git = True
    else:
        candidates = []
        for dirpath, dirnames, filenames in os.walk(root):
            rel_dir = os.path.relpath(dirpath, root)
            keep = []
            for d in dirnames:
                rel = d if rel_dir == "." else f"{rel_dir}/{d}".replace(os.sep, "/")
                if d in excluded_dir_names and not _match_any(rel, include):
                    inv.excluded_dirs[rel] = "default-excluded"
                elif _match_any(rel, exclude):
                    inv.excluded_dirs[rel] = "config-excluded"
                else:
                    keep.append(d)
            dirnames[:] = keep
            for fn in filenames:
                rel = fn if rel_dir == "." else f"{rel_dir}/{fn}"
                candidates.append(rel.replace(os.sep, "/"))

    for rel in sorted(candidates):
        parts = rel.split("/")
        if not _match_any(rel, include):
            hit = next((i for i, part in enumerate(parts[:-1]) if part in excluded_dir_names), None)
            if hit is not None:
                d = "/".join(parts[:hit + 1])
                inv.excluded_dirs.setdefault(d, "default-excluded")
                continue
            if exclude and _match_any(rel, exclude):
                inv.excluded_files["config-excluded"] = inv.excluded_files.get("config-excluded", 0) + 1
                continue
        absp = root / rel
        try:
            st = absp.stat()
        except OSError:
            continue  # deleted but still in git index, or broken symlink
        if not absp.is_file():
            continue
        lang, role = classify(rel, st.st_size)
        entry = FileEntry(rel, st.st_size, st.st_mtime_ns, lang, role)
        if st.st_size > max_bytes and role not in ("binary", "secret"):
            entry.note = "too-large"
        prev = previous.get(rel)
        if role == "secret":
            entry.hash = f"meta:{st.st_size}:{st.st_mtime_ns}"  # never read secret files
        elif prev and prev[0] == st.st_size and prev[1] == st.st_mtime_ns and prev[2]:
            entry.hash = prev[2]
        else:
            entry.hash = hash_file(absp)
        if role == "source" and lang in ("javascript", "typescript") and _looks_generated(absp):
            entry.role = "generated"
        inv.files.append(entry)
    return inv


def hash_file(path: Path) -> str:
    h = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 16), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def hash_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _looks_generated(path: Path) -> bool:
    try:
        with open(path, "rb") as fh:
            head = fh.read(2048)
    except OSError:
        return False
    text = head.decode("utf-8", "ignore")
    first = text.splitlines()[:3]
    if any("generated" in ln.lower() and ("do not edit" in ln.lower() or "@generated" in ln) for ln in first):
        return True
    # Minified heuristic: very long first line without newlines.
    return len(head) >= 2048 and "\n" not in text[:2000]


def read_text(path: Path) -> str:
    data = path.read_bytes()
    if b"\0" in data[:8192]:
        raise ValueError("binary content")
    return data.decode("utf-8", "replace")
