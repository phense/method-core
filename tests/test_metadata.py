"""Runtime and packaging metadata tests for the supported Python floor."""

from __future__ import annotations

import tomllib
import unittest
from pathlib import Path


class ProjectMetadataTests(unittest.TestCase):
    def test_project_declares_python_3_11_or_newer(self) -> None:
        root = Path(__file__).resolve().parents[1]
        payload = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(payload["project"]["requires-python"], ">=3.11")


if __name__ == "__main__":
    unittest.main()
