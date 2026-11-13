"""Clean native install failures cannot masquerade as load evidence."""
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from scripts.clean_install import assert_installed, isolated_environment, run_native


class CleanInstallTests(unittest.TestCase):
    def test_inventory_requires_host_specific_installed_entries(self):
        invalid = [
            {"marketplaces": [{"name": "engineering-method", "plugins": []}]},
            {"installed": [{"name": "engineering-method", "installed": None, "enabled": None}]},
            {"installed": [{"pluginId": "engineering-method@engineering-method", "installed": False, "enabled": True}]},
            [{"id": "engineering-method@engineering-method", "enabled": True}],
        ]
        for host in ("Codex", "Claude"):
            for payload in invalid:
                with self.subTest(host=host, payload=payload), self.assertRaises(ValueError):
                    assert_installed(json.dumps(payload), host)

    def test_native_timeout_terminates_grandchild_before_return(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "orphan"
            child = f"import time; from pathlib import Path; time.sleep(0.5); Path({str(marker)!r}).touch()"
            parent = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(5)"
            with self.assertRaises(ValueError):
                run_native([sys.executable, "-c", parent], Path(directory), None, 0.1)
            time.sleep(0.6)
            self.assertFalse(marker.exists(), "native timeout left an active grandchild")

    def test_isolation_drops_credentials_and_user_configuration(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "secret", "OPENAI_API_KEY": "secret",
            "CODEX_HOME": "/real/codex", "CLAUDE_CONFIG_DIR": "/real/claude",
        }):
            env = isolated_environment(Path(directory))
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            self.assertNotIn("OPENAI_API_KEY", env)
            self.assertTrue(env["CODEX_HOME"].startswith(directory))
            self.assertTrue(env["CLAUDE_CONFIG_DIR"].startswith(directory))

    def test_native_timeout_missing_command_and_failure_are_errors(self):
        for error in (FileNotFoundError("missing"), subprocess.TimeoutExpired("host", 1)):
            with self.subTest(error=type(error).__name__), patch("scripts.clean_install.run_bounded", side_effect=error):
                with self.assertRaises(ValueError):
                    run_native(["host"], Path("/tmp"), {}, 1)
        with patch("scripts.clean_install.run_bounded", return_value=subprocess.CompletedProcess(["host"], 1, "", "failure")):
            with self.assertRaises(ValueError):
                run_native(["host"], Path("/tmp"), {}, 1)
