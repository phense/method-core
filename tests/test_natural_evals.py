"""Unscripted routing evaluations count loads, not mentions, and never steer the host."""

from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from scripts import run_host_evals as harness
from scripts import run_natural_evals as natural


def lines(*events):
    return "\n".join(json.dumps(event) for event in events)


def claude_call(identity, name, arguments, content="ok", error=False):
    return [
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": identity, "name": name, "input": arguments}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": identity, "content": content, "is_error": error}]}},
    ]


DONE = {"type": "result", "subtype": "success", "is_error": False, "result": "done"}


class LoadedSkillTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.plugin = Path(self.directory.name) / "plugin"
        skill = self.plugin / "skills/alpha-skill"
        skill.mkdir(parents=True)
        self.content = "---\nname: alpha-skill\ndescription: Use when testing.\n---\n\n# Alpha\n\nBody.\n"
        (skill / "SKILL.md").write_text(self.content)

    def tearDown(self):
        self.directory.cleanup()

    def test_claude_counts_successful_skill_calls_and_skill_file_reads(self):
        text = lines(
            *claude_call("a", "Skill", {"skill": "writing-method:story-drafting"}),
            *claude_call("b", "Read", {"file_path": "/x/skills/alpha-skill/SKILL.md"}),
            *claude_call("c", "Skill", {"skill": "writing-method:story-drafting"}),
            DONE)
        self.assertEqual(["story-drafting", "alpha-skill"], natural.loaded_skills("claude", text, [self.plugin]))

    def test_claude_ignores_failed_calls_and_paths_inside_file_content(self):
        text = lines(
            *claude_call("a", "Skill", {"skill": "beta-skill"}, error=True),
            *claude_call("b", "Read", {"file_path": "/x/policy.md"},
                         content="see skills/alpha-skill/SKILL.md for details"),
            {"type": "assistant", "message": {"content": [
                {"type": "text", "text": "I would use skills/alpha-skill/SKILL.md"}]}},
            DONE)
        self.assertEqual([], natural.loaded_skills("claude", text, [self.plugin]))

    def test_codex_counts_a_complete_read_only(self):
        def command(text, output, code=0):
            return {"type": "item.completed", "item": {"type": "command_execution", "command": text,
                                                       "aggregated_output": output, "exit_code": code}}
        path = ".agents/skills/alpha-skill/SKILL.md"
        complete = lines(command(f"/bin/zsh -lc 'cat {path}'", self.content), {"type": "turn.completed"})
        self.assertEqual(["alpha-skill"], natural.loaded_skills("codex", complete, [self.plugin]))
        listing = lines(command("/bin/zsh -lc 'rg --files .agents/skills'", path + "\n"),
                        command(f"/bin/zsh -lc 'cat {path}'", self.content, code=1),
                        command(f"/bin/zsh -lc 'head -2 {path}'", "---\nname: alpha-skill\n"),
                        {"type": "turn.completed"})
        self.assertEqual([], natural.loaded_skills("codex", listing, [self.plugin]))

    def test_unfinished_or_failed_transcripts_are_failures(self):
        with self.assertRaisesRegex(harness.EvalFailure, "incomplete_transcript"):
            natural.loaded_skills("claude", lines(*claude_call("a", "Skill", {"skill": "x"})), [self.plugin])
        with self.assertRaisesRegex(harness.EvalFailure, "host_error"):
            natural.loaded_skills("codex", lines({"type": "turn.failed"}), [self.plugin])
        with self.assertRaisesRegex(harness.EvalFailure, "malformed_jsonl"):
            natural.loaded_skills("claude", "{not json", [self.plugin])

    def test_claude_counts_a_complete_shell_read(self):
        path = str(self.plugin / "skills/alpha-skill/SKILL.md")
        text = lines(*claude_call("a", "Bash", {"command": f"cat {path}"}, content=self.content), DONE)
        self.assertEqual(["alpha-skill"], natural.loaded_skills("claude", text, [self.plugin]))

    def test_judgement(self):
        expected = {"any": ["a", "b"], "prohibited": ["z"]}
        self.assertTrue(natural.judge(["b", "other"], expected))
        self.assertFalse(natural.judge(["other"], expected))
        self.assertFalse(natural.judge(["a", "z"], expected))
        # A case that expects no skill hits only when nothing was loaded.
        self.assertTrue(natural.judge([], {"any": []}))
        self.assertFalse(natural.judge(["a"], {"any": []}))


class CommandTests(unittest.TestCase):
    def test_prompt_is_sent_unchanged_with_every_plugin_and_read_only_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory)
            plugins = [Path("/p/one"), Path("/p/two")]
            command, env = natural.host_command("claude", Path("/repo"), plugins, config, "sonnet", "medium",
                                                "Schreib bitte Kapitel 12.", native_auth=True)
            self.assertEqual("Schreib bitte Kapitel 12.", command[-1])
            self.assertEqual(["/p/one", "/p/two"],
                             [command[i + 1] for i, word in enumerate(command) if word == "--plugin-dir"])
            self.assertEqual(natural.READ_ONLY_TOOLS, command[command.index("--allowedTools") + 1])
            self.assertNotIn("--json-schema", command)
            self.assertNotIn("ANTHROPIC_API_KEY", env)
            command, env = natural.host_command("codex", Path("/repo"), plugins, config, "m", None,
                                                "Plain request.", auth_home=Path("/auth"))
            self.assertEqual("Plain request.", command[-1])
            self.assertEqual("read-only", command[command.index("--sandbox") + 1])
            self.assertNotIn("--output-schema", command)
            # The plugins load as installed, so the user's configuration stays in effect.
            self.assertNotIn("--ignore-user-config", command)
            self.assertEqual("/auth", env["CODEX_HOME"])
        for instruction in (harness.ROUTING_INSTRUCTION, harness.SKILL_DISCOVERY_INSTRUCTION):
            self.assertNotIn(instruction.strip()[:40], " ".join(command))

    def test_repository_holds_the_fixture_and_no_skill_links(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            natural.prepare_repo(base / "repo", {"files": {"docs/a.md": "x"}})
            self.assertEqual("x", (base / "repo/docs/a.md").read_text())
            self.assertFalse((base / "repo/.agents").exists())
            with self.assertRaisesRegex(harness.EvalFailure, "fixture_path_escape"):
                natural.prepare_repo(base / "repo3", {"files": {"../out.md": "x"}})

    def test_codex_uses_the_installed_copy_only_when_its_skills_equal_the_source(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, home = base / "source", base / "home"
            (source / "skills/alpha").mkdir(parents=True)
            (source / "skills/alpha/SKILL.md").write_text("current")
            (source / ".codex-plugin").mkdir()
            (source / ".codex-plugin/plugin.json").write_text(json.dumps({"name": "demo"}))
            with self.assertRaisesRegex(harness.EvalFailure, "plugin_not_installed:demo"):
                natural.installed_codex_plugins([source], home)
            installed = home / "plugins/cache/market/demo/1.0.0"
            (installed / "skills/alpha").mkdir(parents=True)
            (installed / "skills/alpha/SKILL.md").write_text("older")
            with self.assertRaisesRegex(harness.EvalFailure, "installed_plugin_differs:demo"):
                natural.installed_codex_plugins([source], home)
            (installed / "skills/alpha/SKILL.md").write_text("current")
            self.assertEqual([installed], natural.installed_codex_plugins([source], home))


class RunTests(unittest.TestCase):
    def test_a_case_reports_hits_over_runs_and_never_stops_early(self):
        observed = iter([(["a"], "m"), harness.EvalFailure("timeout"), (["other"], "m")])

        def once(*args, **kwargs):
            value = next(observed)
            if isinstance(value, Exception):
                raise value
            return value

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.object(natural, "run_once", side_effect=once), \
                mock.patch.object(harness, "fingerprint", return_value="same"):
            result = natural.run_case("claude", {"id": "c"}, {"any": ["a"]}, Path(directory), 3, 1, 1.0,
                                      [Path(directory)])
        self.assertEqual((3, 1, "passed"), (result["runs"], result["hits"], result["status"]))
        self.assertEqual([True, False, False], [o["hit"] for o in result["observations"]])
        self.assertEqual("timeout", result["observations"][1]["failure"])

    def test_arguments_are_checked_before_any_host_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "plugin"
            (plugin / "skills").mkdir(parents=True)
            base = ["--host", "claude", "--plugin-root", str(plugin)]
            for extra in (["--output-dir", str(plugin / "out")],
                          ["--output-dir", str(Path(directory) / "out")],
                          ["--output-dir", str(Path(directory) / "out"), "--runs", "0"],
                          ["--output-dir", str(Path(directory) / "out"), "--runs", "2", "--min-hits", "3"],
                          ["--output-dir", str(Path(directory) / "out"), "--with-plugin", directory]):
                with self.subTest(extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    natural.main(base + extra)
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                natural.main(["--host", "codex", "--native-auth", "--output-dir", str(Path(directory) / "o"),
                              "--plugin-root", str(plugin)])


class HostProcessTests(unittest.TestCase):
    def test_host_process_never_inherits_standard_input(self):
        # An inherited open stdin makes a host wait for more input: the run then times out with no event.
        output = harness.execute(["python3", "-c", "import sys; print(repr(sys.stdin.read()))"],
                                 Path.cwd(), dict(__import__("os").environ), 20)
        self.assertEqual("''", output.strip())


if __name__ == "__main__":
    unittest.main()
