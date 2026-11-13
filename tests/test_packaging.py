"""Packages are a reproducible projection of committed source, never the worktree."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile

from scripts.package_plugin import build_package, check_package


class PackagingTests(unittest.TestCase):
    def test_committed_bytes_only_with_modes_assets_and_exclusions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            for args in (("init", "-q"), ("config", "user.name", "Fixture"),
                         ("config", "user.email", "fixture@example.invalid")):
                subprocess.run(["git", *args], cwd=root, check=True)
            for relative in ("README.md", "scripts/entry", "tests/e2e/fixture.json",
                             "evals/shared/triggers/case.json", ".engineering-method/state.json",
                             "__pycache__/cache.pyc", "dist/old.zip", ".superpowers/run.md"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("committed\n")
            (root / "scripts/entry").chmod(0o755)
            subprocess.run(["git", "add", "-f", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-qm", "fixture"], cwd=root, check=True)
            (root / "README.md").write_text("uncommitted secret\n")
            subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
            (root / "untracked-secret").write_text("private\n")
            output = Path(directory) / "artifact.zip"
            result = check_package(root, output)
            self.assertEqual(hashlib.sha256(output.read_bytes()).hexdigest(), result["sha256"])
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
                self.assertEqual({"engineering-method/" + name for name in (
                    "README.md", "scripts/entry", "tests/e2e/fixture.json", "evals/shared/triggers/case.json")}, names)
                self.assertEqual(b"committed\n", archive.read("engineering-method/README.md"))
                self.assertEqual(0o755, (archive.getinfo("engineering-method/scripts/entry").external_attr >> 16) & 0o777)
            second = Path(directory) / "second.zip"
            build_package(root, second)
            self.assertEqual(output.read_bytes(), second.read_bytes())

    def test_rejects_non_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                build_package(Path(directory), Path(directory) / "out.zip")
