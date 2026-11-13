"""A consumer must not silently validate without the shared integrity contract."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from scripts.validate_plugin import validate_repository
ROOT=Path(__file__).resolve().parents[1]

class CoreValidationTests(unittest.TestCase):
    def test_declared_method_requires_core_lock(self):
        # Removing the lock must fail even if ordinary plugin metadata is intact.
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'method.json').write_text(json.dumps({'name':'writing-method','method_skills':[]}))
            errors=validate_repository(root)
            self.assertTrue(any('method-core.lock.json' in error for error in errors),errors)
    def test_core_source_validates_without_plugin_identity(self):
        # Core is a source dependency, not a third plugin to install.
        self.assertEqual([],validate_repository(ROOT))
