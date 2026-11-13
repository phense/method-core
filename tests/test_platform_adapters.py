"""Portable platform boundaries and declared capability coverage."""
import json
import re
import tempfile
import unittest
from pathlib import Path

from scripts.validate_plugin import _validate_platform_boundary

ROOT = Path(__file__).resolve().parents[1]


class PlatformAdapterTests(unittest.TestCase):
    def test_neutral_resources_reject_host_syntax_and_models(self):
        for tree in ("skills", "templates", "shared/policies"):
            for token in ("collaboration.spawn_agent", "gpt-6-astra", "claude-fable-5", "`Agent`"):
                with self.subTest(tree=tree, token=token), tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    path = root / tree / "example.md"
                    path.parent.mkdir(parents=True)
                    path.write_text(token)
                    errors = []
                    _validate_platform_boundary(root, errors)
                    self.assertTrue(errors)

    def test_shared_tree_is_host_neutral(self):
        errors = []
        _validate_platform_boundary(ROOT, errors)
        self.assertEqual([], errors)

    def test_both_adapters_map_every_required_operation(self):
        operations = {"dispatch", "follow_up", "status", "wait", "cancel", "isolation", "model_selection", "sequential_fallback"}
        for host in ("codex", "claude"):
            with self.subTest(host=host):
                text = (ROOT / f"shared/platform/{host}.md").read_text()
                data = json.loads(re.search(r"```json\n(.*?)\n```", text, re.S).group(1))
                self.assertEqual(operations, set(data["operations"]))
                self.assertTrue(all(data["operations"].values()))
                self.assertEqual({"fast", "standard", "strong"}, set(data["roles"]))
                self.assertEqual("medium", data["coordinator"]["effort"])
                for selection in data["roles"]["strong"]:
                    expected = "medium" if any(s in selection["model"] for s in ("astra", "fable")) else "high"
                    self.assertEqual(expected, selection["effort"])
                self.assertIn("case-specific", text)
                self.assertIn("at most once", text)
                self.assertIn("Never claim", text)


if __name__ == "__main__":
    unittest.main()
