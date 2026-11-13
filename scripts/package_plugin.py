"""Deterministic release archive built exclusively from immutable Git blobs."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import zipfile


EXCLUDED = {".git", ".engineering-method", ".superpowers", ".worktrees", ".venv",
            "__pycache__", ".pytest_cache", ".cache", ".codex", ".claude",
            "dist", "build", "htmlcov", "test-results", "eval-results", "release-evidence"}


def git(root: Path, *args: str) -> bytes:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError(f"Git operation failed: {args[0]}")
    return result.stdout


def source_commit(root: Path) -> str:
    return git(root, "rev-parse", "HEAD^{commit}").decode().strip()


def included(name: str) -> bool:
    path = PurePosixPath(name)
    return not (EXCLUDED.intersection(path.parts) or path.name in {".DS_Store", ".coverage"}
                or path.suffix in {".pyc", ".pyo", ".log"})


def build_package(root: Path, output: Path, *, commit: str | None = None) -> dict:
    commit = commit or source_commit(root)
    tree = git(root, "ls-tree", "--name-only", commit).decode().splitlines()
    if ".codex-plugin" in tree:
        name = json.loads(git(root, "show", commit + ":.codex-plugin/plugin.json"))["name"]
    elif "method-core.json" in tree:
        name = "method-core"
    else:
        name = "engineering-method"
    if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError("invalid committed package identity")
    entries = git(root, "ls-tree", "-rz", "--full-tree", commit).split(b"\0")
    output.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    package_prefix = name + "/"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for entry in sorted(item for item in entries if item):
            metadata, raw_name = entry.split(b"\t", 1)
            mode, kind, object_id = metadata.decode().split()
            name = raw_name.decode("utf-8")
            if not included(name):
                continue
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise ValueError(f"unsupported package entry (symlink/submodule): {name}")
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("unsafe Git package path")
            info = zipfile.ZipInfo(package_prefix + name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = int(mode, 8) << 16
            archive.writestr(info, git(root, "cat-file", "blob", object_id))
            count += 1
    return {"source_commit": commit, "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "file_count": count, "package": str(output.resolve())}


def check_package(root: Path, output: Path) -> dict:
    commit = source_commit(root)
    first = build_package(root, output, commit=commit)
    with tempfile.TemporaryDirectory(prefix="em-reproduce-") as directory:
        second = build_package(root, Path(directory) / "second.zip", commit=commit)
    if first["sha256"] != second["sha256"]:
        raise ValueError("package builds are not reproducible")
    first["reproducible"] = True
    return first


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=Path("dist/engineering-method.zip"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = (check_package if args.check else build_package)(args.root, args.output)
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))
        return 1
    print(json.dumps({"status": "passed", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
