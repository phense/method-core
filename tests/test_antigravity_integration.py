"""Exercise the Antigravity installer: ownership, coexistence, safety and config preservation."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class AntigravityIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="em antigravity ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.config = self.base / "config"
        self.source = self.make_source(self.base / "source tree", "engineering-method", "0.3.2")

    def make_source(self, path: Path, name: str, version: str) -> Path:
        (path / ".antigravity-plugin").mkdir(parents=True, exist_ok=True)
        (path / ".antigravity-plugin/plugin.json").write_text(
            json.dumps(
                {
                    "$schema": "https://antigravity.google/schemas/v1/plugin.json",
                    "name": name,
                    "displayName": name,
                    "version": version,
                    "description": "Test plugin.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (path / "shared/platform").mkdir(parents=True, exist_ok=True)
        (path / "shared/platform/antigravity.md").write_text("# Antigravity adapter\n", encoding="utf-8")
        (path / "skills/example").mkdir(parents=True, exist_ok=True)
        (path / "skills/example/SKILL.md").write_text(
            "---\nname: example\ndescription: An example skill.\n---\n\n# Example\n",
            encoding="utf-8",
        )
        (path / "scripts").mkdir(parents=True, exist_ok=True)
        helper = path / "scripts/helper"
        helper.write_text("#!/usr/bin/env python3\nprint('ok')\n", encoding="utf-8")
        helper.chmod(0o755)
        # Excluded runtime/build paths must never be copied into the installed plugin.
        (path / ".git").mkdir(parents=True, exist_ok=True)
        (path / ".git/HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        (path / "dist").mkdir(parents=True, exist_ok=True)
        (path / "dist/old.zip").write_text("zip\n", encoding="utf-8")
        (path / "__pycache__").mkdir(parents=True, exist_ok=True)
        (path / "__pycache__/cache.pyc").write_bytes(b"pyc")
        return path

    def run_installer(self, *args: str, source: Path | None = None) -> subprocess.CompletedProcess[str]:
        command = [
            os.sys.executable,
            str(ROOT / "scripts/install-antigravity"),
            "--config-dir",
            str(self.config),
        ]
        if source is not None:
            command.extend(["--source-root", str(source)])
        elif "--name" not in args:
            command.extend(["--source-root", str(self.source)])
        command.extend(args)
        return subprocess.run(command, capture_output=True, text=True, timeout=15)

    def test_check_is_read_only_and_install_copies_cleanly_with_modes(self) -> None:
        result = self.run_installer("--check")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.config.exists())

        installed = self.run_installer()
        self.assertEqual(0, installed.returncode, installed.stderr)
        plugin_dir = self.config / "plugins/engineering-method"
        self.assertTrue((plugin_dir / ".antigravity-plugin/plugin.json").is_file())
        self.assertTrue((plugin_dir / "skills/example/SKILL.md").is_file())
        self.assertTrue(bool((plugin_dir / "scripts/helper").stat().st_mode & 0o100))
        self.assertFalse((plugin_dir / ".git").exists())
        self.assertFalse((plugin_dir / "dist").exists())
        self.assertFalse((plugin_dir / "__pycache__").exists())

        repeat = self.run_installer()
        self.assertEqual(0, repeat.returncode, repeat.stderr)
        self.assertIn("Already installed", repeat.stdout)

    def test_owned_install_updates_cleanly_when_source_changes(self) -> None:
        self.assertEqual(0, self.run_installer().returncode)
        (self.source / "skills/example/SKILL.md").write_text(
            "---\nname: example\ndescription: Updated skill.\n---\n\n# Updated\n",
            encoding="utf-8",
        )
        check = self.run_installer("--check")
        self.assertEqual(0, check.returncode, check.stderr)
        self.assertIn("Would update", check.stdout)

        updated = self.run_installer()
        self.assertEqual(0, updated.returncode, updated.stderr)
        self.assertIn("Updated", updated.stdout)
        self.assertIn(
            "Updated skill.",
            (self.config / "plugins/engineering-method/skills/example/SKILL.md").read_text(encoding="utf-8"),
        )

    def test_install_and_uninstall_preserve_user_config_and_other_plugins(self) -> None:
        self.config.mkdir()
        config_file = self.config / "config.json"
        config_file.write_text('{"plugins": {"other": {"enabled": true}}}\n', encoding="utf-8")
        other_plugin = self.config / "plugins/other"
        other_plugin.mkdir(parents=True)
        (other_plugin / "plugin.json").write_text('{"name": "other"}\n', encoding="utf-8")

        self.assertEqual(0, self.run_installer().returncode)
        self.assertEqual(0, self.run_installer("--uninstall", "--check").returncode)
        self.assertTrue((self.config / "plugins/engineering-method").exists())
        self.assertEqual(0, self.run_installer("--uninstall").returncode)
        self.assertFalse((self.config / "plugins/engineering-method").exists())
        self.assertEqual('{"name": "other"}\n', (other_plugin / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual('{"plugins": {"other": {"enabled": true}}}\n', config_file.read_text(encoding="utf-8"))
        self.assertEqual(0, self.run_installer("--uninstall").returncode)

    def test_foreign_or_modified_plugin_is_never_overwritten_or_removed(self) -> None:
        foreign = self.config / "plugins/engineering-method"
        foreign.mkdir(parents=True)
        (foreign / "plugin.json").write_text('{"name": "engineering-method"}\n', encoding="utf-8")
        for args in ((), ("--check",), ("--uninstall",)):
            result = self.run_installer(*args)
            self.assertNotEqual(0, result.returncode)
            self.assertTrue((foreign / "plugin.json").is_file())

        shutil.rmtree(foreign)
        self.assertEqual(0, self.run_installer().returncode)
        (foreign / "skills/example/SKILL.md").write_text("local edit\n", encoding="utf-8")
        for args in ((), ("--check",), ("--uninstall",)):
            result = self.run_installer(*args)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("local edit\n", (foreign / "skills/example/SKILL.md").read_text(encoding="utf-8"))

    def test_symlinked_destination_parent_and_plugin_dir_are_rejected(self) -> None:
        outside = self.base / "outside"
        outside.mkdir()
        self.config.symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(0, self.run_installer().returncode)
        self.assertEqual([], list(outside.iterdir()))

        self.config.unlink()
        (self.config / "plugins").mkdir(parents=True)
        target = outside / "target"
        target.mkdir()
        (target / "keep.txt").write_text("keep", encoding="utf-8")
        (self.config / "plugins/engineering-method").symlink_to(target, target_is_directory=True)
        self.assertNotEqual(0, self.run_installer().returncode)
        self.assertEqual("keep", (target / "keep.txt").read_text(encoding="utf-8"))

    def test_missing_required_resources_are_rejected_before_writing(self) -> None:
        (self.source / ".antigravity-plugin/plugin.json").unlink()
        self.assertNotEqual(0, self.run_installer().returncode)
        self.assertFalse(self.config.exists())

    def test_both_methods_coexist_and_uninstall_works_after_source_removed(self) -> None:
        writing = self.make_source(self.base / "writing-method", "writing-method", "0.5.0")
        self.assertEqual(0, self.run_installer(source=self.source).returncode)
        self.assertEqual(0, self.run_installer(source=writing).returncode)
        self.assertEqual(
            {"engineering-method", "writing-method"},
            {p.name for p in (self.config / "plugins").iterdir()},
        )
        shutil.rmtree(writing)
        result = self.run_installer("--uninstall", "--name", "writing-method", source=self.source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual({"engineering-method"}, {p.name for p in (self.config / "plugins").iterdir()})


if __name__ == "__main__":
    unittest.main()
