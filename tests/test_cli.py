"""End-to-end tests for the complete, non-destructive command surface."""

from __future__ import annotations

import contextlib
from dataclasses import replace
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engineering_method.backlog import (
    BacklogDocument,
    load_backlog,
    render_backlog,
    render_backlog_archive,
)
from engineering_method.cli import main
from engineering_method.continuity import RunState, create_run, load_run_state
from engineering_method.features import load_features
from engineering_method.gh import GitHubIssuesGateway, RepositoryDetection
from engineering_method.issues import pending_queue
from engineering_method.models import BacklogItem, Priority, TaskStatus
from tests.fakes import MutableGitHubRunner


def item(
    identifier: str,
    *,
    status: TaskStatus = TaskStatus.OPEN,
    priority: Priority = Priority.P1,
    depends_on: tuple[str, ...] = (),
) -> BacklogItem:
    return BacklogItem(
        identifier,
        f"Task {identifier}",
        status,
        priority,
        None,
        depends_on,
        "",
        "2026-09-04T10:20:30Z",
    )


@contextlib.contextmanager
def quiet_cli():
    output = io.StringIO()
    errors = io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        yield output, errors


class LocalCommandSurfaceTests(unittest.TestCase):
    def test_init_is_non_destructive_and_local_commands_cover_dependencies_priority_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli() as (_, errors):
            root = Path(temporary)
            self.assertEqual(main(["backlog", "init", "--project-key", "EM"], root=root), 0)
            original_backlog = (root / "BACKLOG.md").read_bytes()
            original_features = (root / "FEATURES.md").read_bytes()
            self.assertEqual(main(["backlog", "init", "--project-key", "XX"], root=root), 2)
            self.assertEqual((root / "BACKLOG.md").read_bytes(), original_backlog)
            self.assertEqual((root / "FEATURES.md").read_bytes(), original_features)

            self.assertEqual(
                main(
                    [
                        "backlog",
                        "add",
                        "--id",
                        "EM-001",
                        "--title",
                        "Unblock work",
                        "--priority",
                        "P2",
                    ],
                    root=root,
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "add",
                        "--id",
                        "EM-002",
                        "--title",
                        "Blocked work",
                        "--priority",
                        "P1",
                        "--depends-on",
                        "EM-001",
                    ],
                    root=root,
                ),
                0,
            )
            self.assertEqual(main(["backlog", "priority", "EM-001", "P0"], root=root), 0)
            self.assertEqual(main(["backlog", "start", "EM-001"], root=root), 0)
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "block",
                        "EM-002",
                        "--depends-on",
                        "EM-001",
                        "--notes",
                        "Waiting",
                    ],
                    root=root,
                ),
                0,
            )
            self.assertEqual(main(["backlog", "complete", "EM-001"], root=root), 0)
            document = load_backlog(root / "BACKLOG.md")
            by_id = {entry.id: entry for entry in document.items}
            self.assertEqual(by_id["EM-001"].priority, Priority.P0)
            self.assertEqual(by_id["EM-001"].status, TaskStatus.COMPLETE)
            self.assertEqual(by_id["EM-002"].depends_on, ("EM-001",))
            self.assertEqual(by_id["EM-002"].notes, "Waiting")

            completed = tuple(item(f"EM-{number:03d}", status=TaskStatus.COMPLETE) for number in range(3, 15))
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "local", document.items + completed)),
                encoding="utf-8",
            )
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "archive",
                        "--active-line-limit",
                        "40",
                        "--target-line-limit",
                        "40",
                    ],
                    root=root,
                ),
                0,
            )
            self.assertTrue((root / "BACKLOG-ARCHIVE.md").is_file())
            self.assertIn("already exists", errors.getvalue())

    def test_explicit_replace_is_the_only_way_to_reinitialize(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            self.assertEqual(main(["backlog", "init", "--project-key", "EM"], root=root), 0)
            self.assertEqual(
                main(
                    ["backlog", "init", "--project-key", "XX", "--replace"], root=root
                ),
                0,
            )
            self.assertEqual(load_backlog(root / "BACKLOG.md").project_key, "XX")

    def test_initialization_does_not_leave_half_created_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            real_replace = os.replace
            calls = 0

            def fail_second(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("feature initialization failed")
                return real_replace(source, destination)

            with patch("engineering_method.files.os.replace", side_effect=fail_second):
                self.assertEqual(
                    main(["backlog", "init", "--project-key", "EM"], root=root), 2
                )
            self.assertFalse((root / "BACKLOG.md").exists())
            self.assertFalse((root / "FEATURES.md").exists())

    def test_cache_mode_queues_mutations_without_fabricating_local_canonical_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            cached = BacklogDocument("EM", "github-cache", (item("EM-001"),))
            (root / "BACKLOG.md").write_text(render_backlog(cached), encoding="utf-8")
            class OfflineGateway:
                def detect_repository(self):
                    return RepositoryDetection(None, "GitHub repository unavailable")

            gateway = OfflineGateway()
            self.assertEqual(
                main(
                    ["backlog", "complete", "EM-001"], root=root, gateway=gateway
                ),
                0,
            )
            self.assertEqual(
                main(
                    ["backlog", "priority", "EM-001", "P0"],
                    root=root,
                    gateway=gateway,
                ),
                0,
            )
            unchanged = load_backlog(root / "BACKLOG.md").items[0]
            self.assertEqual(unchanged.status, TaskStatus.OPEN)
            self.assertEqual(unchanged.priority, Priority.P1)
            self.assertEqual(len(pending_queue(root)), 2)

    def test_feature_commands_add_change_and_remove_with_rationale(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            self.assertEqual(main(["backlog", "init", "--project-key", "EM"], root=root), 0)
            self.assertEqual(
                main(
                    [
                        "feature",
                        "add",
                        "--id",
                        "F-001",
                        "--name",
                        "State",
                        "--summary",
                        "Durable state.",
                        "--related",
                        "EM-001",
                    ],
                    root=root,
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "feature",
                        "change",
                        "--id",
                        "F-001",
                        "--summary",
                        "Durable recovery state.",
                        "--status",
                        "changed",
                    ],
                    root=root,
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "feature",
                        "remove",
                        "--id",
                        "F-001",
                        "--rationale",
                        "Superseded.",
                    ],
                    root=root,
                ),
                0,
            )
            inventory = load_features(root / "FEATURES.md")
            self.assertEqual(inventory.features[0].status, "removed")
            self.assertEqual(dict(inventory.removal_rationales)["F-001"], "Superseded.")

    def test_invalid_and_destructive_commands_fail_concisely_without_mutating_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli() as (_, errors):
            root = Path(temporary)
            self.assertEqual(main(["backlog", "init", "--project-key", "EM"], root=root), 0)
            before = (root / "BACKLOG.md").read_bytes()
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "add",
                        "--id",
                        "EM-001",
                        "--title",
                        "Bad",
                        "--priority",
                        "invalid",
                    ],
                    root=root,
                ),
                2,
            )
            self.assertEqual((root / "BACKLOG.md").read_bytes(), before)
            future = {
                "schema_version": 2,
                "lifecycle": "implementation",
                "phase": "work",
                "next_action": "continue",
            }
            self.assertEqual(
                main(
                    ["continuity-state", "init", "EM-001", "--file", "-"],
                    root=root,
                    stdin=io.StringIO(json.dumps(future)),
                ),
                2,
            )
            self.assertLessEqual(max(len(line) for line in errors.getvalue().splitlines()), 120)

    def test_add_rejects_an_id_already_retained_in_the_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "local", (item("EM-002"),))),
                encoding="utf-8",
            )
            (root / "BACKLOG-ARCHIVE.md").write_text(
                render_backlog_archive(
                    BacklogDocument(
                        "EM", "local", (item("EM-001", status=TaskStatus.COMPLETE),)
                    )
                ),
                encoding="utf-8",
            )
            before = (root / "BACKLOG.md").read_bytes()
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "add",
                        "--id",
                        "EM-001",
                        "--title",
                        "Reused",
                        "--priority",
                        "P1",
                    ],
                    root=root,
                ),
                2,
            )
            self.assertEqual((root / "BACKLOG.md").read_bytes(), before)


class GitHubCommandSurfaceTests(unittest.TestCase):
    def test_migrate_refresh_and_reconcile_have_distinct_remote_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "local", (item("EM-001"),))),
                encoding="utf-8",
            )
            runner = MutableGitHubRunner()
            gateway = GitHubIssuesGateway(runner)

            self.assertEqual(
                main(["backlog-to-issues", "migrate"], root=root, gateway=gateway), 0
            )
            self.assertEqual(load_backlog(root / "BACKLOG.md").mode, "github-cache")

            mutation_count = runner.mutation_count
            self.assertEqual(main(["refresh-issue-cache"], root=root, gateway=gateway), 0)
            self.assertEqual(runner.mutation_count, mutation_count)

            class OfflineGateway:
                def detect_repository(self):
                    return RepositoryDetection(None, "GitHub repository unavailable")

            self.assertEqual(
                main(
                    ["backlog", "complete", "EM-001"],
                    root=root,
                    gateway=OfflineGateway(),
                ),
                0,
            )
            self.assertEqual(len(pending_queue(root)), 1)
            self.assertEqual(
                main(["backlog-to-issues", "reconcile"], root=root, gateway=gateway), 0
            )
            self.assertEqual(pending_queue(root), ())
            self.assertEqual(load_backlog(root / "BACKLOG.md").items[0].status, TaskStatus.COMPLETE)
            self.assertGreater(runner.mutation_count, mutation_count)

            self.assertEqual(
                main(
                    ["backlog", "priority", "EM-001", "P0"],
                    root=root,
                    gateway=gateway,
                ),
                0,
            )
            self.assertEqual(pending_queue(root), ())
            self.assertEqual(load_backlog(root / "BACKLOG.md").items[0].priority, Priority.P0)

    def test_migration_preserves_a_factual_nonblocking_detection_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli() as (output, _):
            root = Path(temporary)
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "local", (item("EM-001"),))),
                encoding="utf-8",
            )
            runner = MutableGitHubRunner(permission="READ")
            self.assertEqual(
                main(
                    ["backlog-to-issues", "migrate"],
                    root=root,
                    gateway=GitHubIssuesGateway(runner),
                ),
                0,
            )
            self.assertIn("not writable", output.getvalue())
            self.assertEqual(load_backlog(root / "BACKLOG.md").mode, "local")

    def test_pending_overlay_allows_offline_parent_child_and_dependency_mutations(self) -> None:
        class OfflineGateway:
            def detect_repository(self):
                return RepositoryDetection(None, "GitHub repository unavailable")

        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "local", (item("EM-001"),))),
                encoding="utf-8",
            )
            runner = MutableGitHubRunner()
            gateway = GitHubIssuesGateway(runner)
            self.assertEqual(
                main(["backlog-to-issues", "migrate"], root=root, gateway=gateway), 0
            )
            offline = OfflineGateway()
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "add",
                        "--id",
                        "EM-002",
                        "--title",
                        "Queued parent",
                        "--priority",
                        "P1",
                    ],
                    root=root,
                    gateway=offline,
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "add",
                        "--id",
                        "EM-002.1",
                        "--title",
                        "Queued child",
                        "--priority",
                        "P1",
                        "--parent",
                        "EM-002",
                    ],
                    root=root,
                    gateway=offline,
                ),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "backlog",
                        "dependencies",
                        "EM-002.1",
                        "--depends-on",
                        "EM-001",
                    ],
                    root=root,
                    gateway=offline,
                ),
                0,
            )
            self.assertEqual(len(pending_queue(root)), 3)

            self.assertEqual(
                main(["backlog-to-issues", "reconcile"], root=root, gateway=gateway), 0
            )
            by_marker = {
                str(entry["body"]).split('"backlog_id":"', 1)[1].split('"', 1)[0]: entry
                for entry in runner.issues
                if '"backlog_id":"' in str(entry["body"])
            }
            parent = by_marker["EM-002"]
            child = by_marker["EM-002.1"]
            blocker = by_marker["EM-001"]
            self.assertEqual(runner.sub_issues[int(parent["number"])], {int(child["id"])})
            self.assertEqual(
                runner.blocked_by[int(child["number"])], {int(blocker["id"])}
            )


class ContinuityCommandSurfaceTests(unittest.TestCase):
    def _git_repository(self, root: Path) -> str:
        subprocess.run(("git", "init", "-q"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.name", "Test User"), cwd=root, check=True)
        (root / "tracked.txt").write_text("state\n", encoding="utf-8")
        subprocess.run(("git", "add", "tracked.txt"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-q", "-m", "state"), cwd=root, check=True)
        return subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, check=True, text=True, capture_output=True
        ).stdout.strip()

    def test_json_file_and_stdin_inputs_preserve_resume_and_recover_with_real_probes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            head = self._git_repository(root)
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "local", (item("EM-001"),))),
                encoding="utf-8",
            )
            (root / "resume-input.md").write_text("Resume stays intact.\n", encoding="utf-8")
            initial = {
                "backlog_id": "EM-001",
                "lifecycle": "implementation",
                "phase": "build",
                "worktree_path": str(root),
                "base_commit": head,
                "last_observed_head": head,
                "next_action": "continue build",
            }
            self.assertEqual(
                main(
                    [
                        "continuity-state",
                        "init",
                        "EM-001",
                        "--file",
                        "-",
                        "--resume-file",
                        "resume-input.md",
                    ],
                    root=root,
                    stdin=io.StringIO(json.dumps(initial)),
                ),
                0,
            )
            checkpoint = {**initial, "phase": "verify", "next_action": "run verification"}
            (root / "checkpoint.json").write_text(json.dumps(checkpoint), encoding="utf-8")
            self.assertEqual(
                main(
                    [
                        "continuity-state",
                        "checkpoint",
                        "EM-001",
                        "--file",
                        "checkpoint.json",
                    ],
                    root=root,
                ),
                0,
            )
            run = root / ".engineering-method" / "runs" / "EM-001"
            self.assertEqual(
                (run / "resume.md").read_text(encoding="utf-8"), "Resume stays intact.\n"
            )
            self.assertEqual(
                main(
                    ["continuity-state", "event", "EM-001", "--file", "-"],
                    root=root,
                    stdin=io.StringIO('{"kind":"verification_passed"}'),
                ),
                0,
            )
            self.assertEqual(main(["continuity-state", "status", "EM-001"], root=root), 0)
            self.assertEqual(
                main(
                    ["continuity-state", "recover", "EM-001", "--live-agents", ""],
                    root=root,
                ),
                0,
            )
            self.assertEqual(load_run_state(root, "EM-001").phase, "verify")

    def test_github_mode_recovery_reads_remote_canonical_status_not_the_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, quiet_cli():
            root = Path(temporary)
            head = self._git_repository(root)
            local = BacklogDocument("EM", "local", (item("EM-001"),))
            (root / "BACKLOG.md").write_text(render_backlog(local), encoding="utf-8")
            runner = MutableGitHubRunner()
            gateway = GitHubIssuesGateway(runner)
            self.assertEqual(
                main(["backlog-to-issues", "migrate"], root=root, gateway=gateway), 0
            )
            cache = load_backlog(root / "BACKLOG.md")
            stale_complete = BacklogDocument(
                "EM",
                "github-cache",
                (replace(cache.items[0], status=TaskStatus.COMPLETE),),
            )
            (root / "BACKLOG.md").write_text(render_backlog(stale_complete), encoding="utf-8")
            create_run(
                root,
                RunState(
                    work_id="EM-001",
                    backlog_id="EM-001",
                    lifecycle="implementation",
                    phase="build",
                    current_slice="slice-1",
                    active_work=("slice-1",),
                    worktree_path=str(root),
                    base_commit=head,
                    last_observed_head=head,
                    next_action="continue slice-1",
                ),
                "Resume remote work.",
            )

            self.assertEqual(
                main(
                    ["continuity-state", "recover", "EM-001", "--live-agents", ""],
                    root=root,
                    gateway=gateway,
                ),
                0,
            )
            recovered = load_run_state(root, "EM-001")
            self.assertEqual(recovered.active_work, ("slice-1",))
            self.assertNotIn("slice-1", recovered.completed_work)

    def test_recover_requires_an_explicit_live_agent_observation(self) -> None:
        """Omitting host observation must fail before reading or mutating project state."""
        with tempfile.TemporaryDirectory() as temporary, quiet_cli() as (_, errors):
            root = Path(temporary)

            result = main(["continuity-state", "recover", "EM-001"], root=root)

        self.assertEqual(2, result)
        self.assertIn("recover requires --live-agents", errors.getvalue())


class WrapperPortabilityTests(unittest.TestCase):
    SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"

    def run_script(
        self, directory: str, script: str, *arguments: str
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            (str(self.SCRIPTS / script), *arguments),
            cwd=directory,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )

    def test_project_state_wrapper_runs_from_an_unrelated_current_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = self.run_script(
                temporary, "project-state", "backlog", "init", "--project-key", "EM"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(temporary) / "BACKLOG.md").is_file())

    def test_project_state_help_is_portable_concise_and_non_mutating(self) -> None:
        """Missing help dispatch must not force callers into unknown-command errors."""
        cases = (
            (
                ("--help",),
                ("Usage: project-state", "Commands:", "backlog", "feature", "continuity-state"),
            ),
            (
                ("backlog", "--help"),
                ("Usage: project-state backlog", "Actions:", "complete", "archive"),
            ),
            (
                ("backlog", "complete", "--help"),
                (
                    "Usage: project-state backlog complete",
                    "Options:",
                    "--notes",
                    "--depends-on",
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for arguments, expected in cases:
                with self.subTest(arguments=arguments):
                    result = self.run_script(temporary, "project-state", *arguments)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual("", result.stderr)
                    for fragment in expected:
                        self.assertIn(fragment, result.stdout)
                    self.assertEqual([], list(Path(temporary).iterdir()))

    def test_sibling_wrapper_help_covers_every_applicable_action_without_mutation(self) -> None:
        """Installed convenience wrappers need the same help behavior as project-state."""
        cases = (
            ("backlog-to-issues", ("--help",), ("Actions:", "migrate", "reconcile")),
            ("backlog-to-issues", ("migrate", "--help"), ("Options:", "migrate")),
            ("backlog-to-issues", ("reconcile", "--help"), ("Options:", "reconcile")),
            ("refresh-issue-cache", ("--help",), ("Options:", "Refresh")),
            ("continuity-state", ("--help",), ("Actions:", "init", "recover")),
            ("continuity-state", ("init", "--help"), ("Options:", "--resume-file")),
            ("continuity-state", ("checkpoint", "--help"), ("Options:", "--file")),
            ("continuity-state", ("event", "--help"), ("Options:", "--file")),
            ("continuity-state", ("status", "--help"), ("Options:", "work-id")),
            ("continuity-state", ("recover", "--help"), ("Options:", "--live-agents")),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for script, arguments, expected in cases:
                with self.subTest(script=script, arguments=arguments):
                    result = self.run_script(temporary, script, *arguments)
                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertEqual("", result.stderr)
                    self.assertIn(f"Usage: {script}", result.stdout)
                    for fragment in expected:
                        self.assertIn(fragment, result.stdout)
                    self.assertEqual([], list(Path(temporary).iterdir()))

    def test_unknown_wrapper_commands_remain_nonzero_and_non_mutating(self) -> None:
        """Adding help must not turn unknown command paths into successful no-ops."""
        cases = (
            ("project-state", ("unknown",)),
            ("project-state", ("backlog", "unknown")),
            ("backlog-to-issues", ("unknown",)),
            ("continuity-state", ("unknown",)),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for script, arguments in cases:
                with self.subTest(script=script, arguments=arguments):
                    result = self.run_script(temporary, script, *arguments)
                    self.assertNotEqual(0, result.returncode)
                    self.assertEqual("", result.stdout)
                    self.assertTrue(result.stderr.strip())
                    self.assertEqual([], list(Path(temporary).iterdir()))


if __name__ == "__main__":
    unittest.main()
