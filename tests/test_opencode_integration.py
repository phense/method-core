"""Run the real installer and JS hook: catch overwrite, broken paths and config loss."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class OpenCodeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="em opencode ")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.config = self.base / "config"
        self.source = self.base / "source tree"
        (self.source / "integrations/opencode").mkdir(parents=True)
        (self.source / "integrations/opencode/plugin.mjs").write_text("export default async () => ({})\n")
        (self.source / "skills").mkdir()
        (self.source / "shared/platform").mkdir(parents=True)
        (self.source / "shared/platform/opencode.md").write_text("Adapter\n")

    def run_installer(self, *args):
        return subprocess.run(
            [os.sys.executable, str(ROOT / "scripts/install-opencode"),
             "--source-root", str(self.source), "--config-dir", str(self.config), *args],
            capture_output=True, text=True, timeout=10,
        )

    def test_check_is_read_only_and_install_is_idempotent(self):
        # Catches eager mkdir during check, duplicate registration and broken file URLs.
        result = self.run_installer("--check")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertFalse(self.config.exists())
        self.assertEqual(0, self.run_installer().returncode)
        loader = self.config / "plugins/engineering-method.js"
        before = loader.read_bytes()
        self.assertIn(self.source.as_uri().encode(), before)
        self.assertEqual(0, self.run_installer().returncode)
        self.assertEqual(before, loader.read_bytes())

    def test_install_and_uninstall_preserve_user_config_and_other_plugins(self):
        # Catches config rewriting or directory-wide deletion on removal.
        self.config.mkdir()
        config = self.config / "opencode.jsonc"
        config.write_text('// keep formatting\n{"model":"existing/model"}\n')
        plugins = self.config / "plugins"
        plugins.mkdir()
        other = plugins / "other.js"
        other.write_text("other")
        self.assertEqual(0, self.run_installer().returncode)
        self.assertEqual(0, self.run_installer("--uninstall", "--check").returncode)
        self.assertTrue((plugins / "engineering-method.js").exists())
        self.assertEqual(0, self.run_installer("--uninstall").returncode)
        self.assertFalse((plugins / "engineering-method.js").exists())
        self.assertEqual("other", other.read_text())
        self.assertEqual('// keep formatting\n{"model":"existing/model"}\n', config.read_text())
        self.assertEqual(0, self.run_installer("--uninstall").returncode)

    def test_foreign_or_modified_loader_is_never_overwritten_or_removed(self):
        plugins = self.config / "plugins"
        plugins.mkdir(parents=True)
        loader = plugins / "engineering-method.js"
        loader.write_text("// user plugin\n")
        for args in [(), ("--check",), ("--uninstall",)]:
            result = self.run_installer(*args)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual("// user plugin\n", loader.read_text())

    def test_line_ending_modified_loader_is_preserved(self):
        self.assertEqual(0, self.run_installer().returncode)
        loader = self.config / "plugins/engineering-method.js"
        modified = loader.read_bytes().replace(b"\n", b"\r\n")
        loader.write_bytes(modified)
        for args in ((), ("--check",), ("--uninstall",)):
            result = self.run_installer(*args)
            self.assertNotEqual(0, result.returncode)
            self.assertEqual(modified, loader.read_bytes())

    def test_symlinked_destination_parent_and_loader_are_rejected(self):
        # Catches following a link out of the intended installation directory.
        outside = self.base / "outside"
        outside.mkdir()
        self.config.symlink_to(outside, target_is_directory=True)
        self.assertNotEqual(0, self.run_installer().returncode)
        self.assertEqual([], list(outside.iterdir()))
        self.config.unlink()
        (self.config / "plugins").mkdir(parents=True)
        target = outside / "target.js"
        target.write_text("do not change")
        (self.config / "plugins/engineering-method.js").symlink_to(target)
        self.assertNotEqual(0, self.run_installer().returncode)
        self.assertEqual("do not change", target.read_text())

    def test_missing_source_is_rejected_before_writing(self):
        (self.source / "integrations/opencode/plugin.mjs").unlink()
        self.assertNotEqual(0, self.run_installer().returncode)
        self.assertFalse(self.config.exists())

    def test_uninstall_works_after_source_was_removed(self):
        self.assertEqual(0, self.run_installer().returncode)
        shutil.rmtree(self.source)
        self.assertEqual(0, self.run_installer("--uninstall").returncode)
        self.assertFalse((self.config / "plugins/engineering-method.js").exists())

    def test_hook_adds_paths_once_and_preserves_other_configuration(self):
        # Catches replacing user rules, model, MCP or permissions; executes the real hook.
        source = ROOT / "integrations/opencode/plugin.mjs"
        script = """
const {default: plugin} = await import(process.argv[1]);
const config = {
  skills: {paths: ["/other/skills"], urls: ["https://example.invalid/skills"]},
  instructions: ["/other/rules.md"],
  model: "existing/model", mcp: {existing: {enabled: true}},
  permission: {bash: "ask"}
};
const hook = await plugin({});
await hook.config(config);
await hook.config(config);
console.log(JSON.stringify(config));
"""
        result = subprocess.run(
            ["node", "--input-type=module", "-e", script, source.as_uri()],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        actual = json.loads(result.stdout)
        self.assertEqual(["/other/skills", str(ROOT / "skills")], actual["skills"]["paths"])
        self.assertEqual(["https://example.invalid/skills"], actual["skills"]["urls"])
        self.assertEqual(["/other/rules.md", str(ROOT / "shared/platform/opencode.md")], actual["instructions"])
        self.assertEqual("existing/model", actual["model"])
        self.assertEqual({"existing": {"enabled": True}}, actual["mcp"])
        self.assertEqual({"bash": "ask"}, actual["permission"])

    def test_hook_handles_empty_config_from_a_linked_module(self):
        # Catches resolving resources beside the loader instead of the real module.
        linked = self.base / "plugin.mjs"
        linked.symlink_to(ROOT / "integrations/opencode/plugin.mjs")
        result = subprocess.run(
            ["node", "--input-type=module", "-e",
             "const p=await import(process.argv[1]);const c={};await (await p.default({})).config(c);console.log(JSON.stringify(c));",
             linked.as_uri()], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        actual = json.loads(result.stdout)
        self.assertEqual([str(ROOT / "skills")], actual["skills"]["paths"])
        self.assertEqual([str(ROOT / "shared/platform/opencode.md")], actual["instructions"])
