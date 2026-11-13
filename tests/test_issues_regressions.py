"""Regression coverage for complete, restart-safe GitHub synchronization."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engineering_method.gh as gh
import engineering_method.issues as issues
from engineering_method.backlog import (
    BacklogDocument,
    load_backlog,
    render_backlog,
    render_backlog_archive,
)
from engineering_method.models import BacklogItem, Priority, TaskStatus
from tests.fakes import MutableGitHubRunner


REPOSITORY = gh.RepositoryRef("peter", "engineering-method")


def backlog_item(
    identifier: str,
    status: TaskStatus = TaskStatus.OPEN,
    *,
    title: str | None = None,
    priority: Priority = Priority.P1,
    parent_id: str | None = None,
    depends_on: tuple[str, ...] = (),
    notes: str = "",
) -> BacklogItem:
    return BacklogItem(
        identifier,
        title or f"English {identifier}",
        status,
        priority,
        parent_id,
        depends_on,
        notes,
        "2026-09-04T10:20:30Z",
    )


def issue_body(
    identifier: str,
    *,
    status: str = "open",
    priority: str = "P1",
    notes: str = "",
) -> str:
    return (
        f'<!-- engineering-method:issue {{"schema_version":1,"backlog_id":"{identifier}"}} -->\n\n'
        f"Backlog status: `{status}`\n"
        f"Priority: `{priority}`\n"
        f"Notes JSON: {json.dumps(notes, ensure_ascii=False)}\n"
    )


def remote_issue(
    number: int,
    database_id: int,
    *,
    identifier: str | None = None,
    title: str | None = None,
    body: str | None = None,
    state: str = "open",
    labels: tuple[str, ...] = (),
    updated_at: str = "2026-09-04T11:00:00Z",
) -> dict[str, object]:
    actual_title = title or (f"{identifier}: English {identifier}" if identifier else f"Noise {number}")
    actual_body = body if body is not None else (issue_body(identifier) if identifier else "Unrelated")
    return {
        "id": database_id,
        "number": number,
        "title": actual_title,
        "body": actual_body,
        "state": state,
        "labels": [{"name": label} for label in labels],
        "updated_at": updated_at,
    }


class GitHubTransportRegressionTests(unittest.TestCase):
    def test_discovers_markers_beyond_100_issues_without_relying_on_a_label(self) -> None:
        remote = [remote_issue(number, 10_000 + number) for number in range(1, 102)]
        remote.append(
            remote_issue(
                102,
                44_444,
                identifier="EM-002",
                labels=(),
            )
        )
        runner = MutableGitHubRunner(issues=remote, page_size=100)

        found = gh.GitHubIssuesGateway(runner).list_method_issues(REPOSITORY)

        self.assertEqual(len(found), 102)
        self.assertEqual(found[-1].id, 44_444)
        command = runner.calls[0][0]
        self.assertIn("--paginate", command)
        self.assertNotIn("--label", command)

    def test_relationship_payloads_use_database_ids_and_integer_form_fields(self) -> None:
        runner = MutableGitHubRunner(
            issues=(
                remote_issue(10, 9_010, identifier="EM-001"),
                remote_issue(11, 9_011, identifier="EM-001.1"),
            )
        )
        gateway = gh.GitHubIssuesGateway(runner)

        gateway.ensure_sub_issue(REPOSITORY, parent_number=10, child_id=9_011)
        gateway.ensure_blocked_by(REPOSITORY, blocked_number=11, blocker_id=9_010)

        self.assertEqual(runner.sub_issues[10], {9_011})
        self.assertEqual(runner.blocked_by[11], {9_010})
        for command, _ in runner.calls:
            self.assertIn("-F", command)
            self.assertNotIn("-f", command)

    def test_live_runner_applies_a_timeout_and_converts_timeout_to_failure(self) -> None:
        with patch(
            "engineering_method.gh.subprocess.run",
            side_effect=subprocess.TimeoutExpired(("gh", "repo", "view"), 30),
        ) as run:
            result = gh.SubprocessGhRunner().run(("repo", "view"))
        self.assertEqual(result.returncode, 124)
        self.assertIn("timed out", result.stderr)
        self.assertEqual(run.call_args.kwargs["timeout"], 30)


class MigrationConvergenceTests(unittest.TestCase):
    def _document(self) -> BacklogDocument:
        return BacklogDocument(
            "EM",
            "local",
            (
                backlog_item("EM-001", title="Parent", notes="Keep context"),
                backlog_item(
                    "EM-001.1",
                    TaskStatus.BLOCKED,
                    title="Child",
                    priority=Priority.P0,
                    parent_id="EM-001",
                    depends_on=("EM-002",),
                ),
                backlog_item("EM-002", TaskStatus.COMPLETE, title="Blocker"),
            ),
        )

    def test_partial_failure_retry_upserts_every_field_and_reconciles_relations(self) -> None:
        noise = [remote_issue(number, 20_000 + number) for number in range(1, 102)]
        parent = remote_issue(
            150,
            90_001,
            identifier="EM-001",
            title="Old title",
            body=issue_body("EM-001", status="complete", priority="P3"),
            state="closed",
            labels=("status:obsolete", "custom"),
        )
        blocker = remote_issue(
            151,
            90_002,
            identifier="EM-002",
            title="EM-002: Old blocker",
            state="open",
            labels=("engineering-method", "priority:p3", "status:open"),
        )
        runner = MutableGitHubRunner(issues=tuple(noise + [parent, blocker]), page_size=100)
        runner.sub_issues[150] = {90_002}
        runner.fail_once("add-blocker")
        gateway = gh.GitHubIssuesGateway(runner)

        with self.assertRaisesRegex(RuntimeError, "add-blocker"):
            issues.migrate_backlog(self._document(), gateway, REPOSITORY, language="en")

        self.assertEqual(
            len([entry for entry in runner.issues if "engineering-method:issue" in str(entry["body"])]),
            3,
        )
        migrated = issues.migrate_backlog(
            self._document(), gateway, REPOSITORY, language="en"
        )
        self.assertEqual(migrated.mode, "github-cache")

        by_id = {
            issues.marker_backlog_id(str(entry["body"])): entry
            for entry in runner.issues
            if "engineering-method:issue" in str(entry["body"])
        }
        self.assertEqual(by_id["EM-001"]["title"], "EM-001: Parent")
        self.assertEqual(by_id["EM-001"]["state"], "open")
        self.assertEqual(
            {label["name"] for label in by_id["EM-001"]["labels"]},
            {"custom", "engineering-method", "priority:p1", "status:open"},
        )
        self.assertIn('Notes JSON: "Keep context"', str(by_id["EM-001"]["body"]))
        self.assertEqual(by_id["EM-002"]["state"], "closed")
        child = by_id["EM-001.1"]
        self.assertEqual(runner.sub_issues[150], {int(child["id"])})
        self.assertEqual(runner.blocked_by[int(child["number"])], {90_002})
        self.assertEqual(
            set(runner.labels),
            {
                "engineering-method",
                "priority:p0",
                "priority:p1",
                "priority:p2",
                "priority:p3",
                "status:open",
                "status:in-progress",
                "status:blocked",
            },
        )

        mutation_count = runner.mutation_count
        issues.migrate_backlog(self._document(), gateway, REPOSITORY, language="en")
        self.assertEqual(runner.mutation_count, mutation_count)

    def test_reparents_only_after_removing_the_stale_parent_relation(self) -> None:
        document = BacklogDocument(
            "EM",
            "local",
            (
                backlog_item("EM-001", title="Desired parent"),
                backlog_item("EM-001.1", title="Child", parent_id="EM-001"),
                backlog_item("EM-002", title="Stale parent"),
            ),
        )
        remote = (
            remote_issue(
                1,
                101,
                identifier="EM-001",
                title="EM-001: Desired parent",
                labels=("engineering-method", "priority:p1", "status:open"),
            ),
            remote_issue(
                2,
                102,
                identifier="EM-001.1",
                title="EM-001.1: Child",
                labels=("engineering-method", "priority:p1", "status:open"),
            ),
            remote_issue(
                3,
                103,
                identifier="EM-002",
                title="EM-002: Stale parent",
                labels=("engineering-method", "priority:p1", "status:open"),
            ),
        )
        runner = MutableGitHubRunner(issues=remote)
        runner.sub_issues[3] = {102}

        migrate_backlog = issues.migrate_backlog
        migrate_backlog(document, gh.GitHubIssuesGateway(runner), REPOSITORY, language="en")

        self.assertEqual(runner.sub_issues[1], {102})
        self.assertEqual(runner.sub_issues[3], set())

    def test_state_check_is_read_only_even_with_writable_remote_and_archive(self) -> None:
        # Regression: automatic migration creates issues and deletes archived history.
        from engineering_method.cli import main
        runner = MutableGitHubRunner()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "BACKLOG.md").write_text(render_backlog(
                BacklogDocument("EM", "local", (backlog_item("EM-002"),))))
            (root / "BACKLOG-ARCHIVE.md").write_text(render_backlog_archive(
                BacklogDocument("EM", "local", (backlog_item("EM-001", TaskStatus.COMPLETE),))))
            before = {p.name: p.read_bytes() for p in root.iterdir()}
            result = main(["backlog", "state-check"], root=root,
                          gateway=gh.GitHubIssuesGateway(runner))
            self.assertEqual(result, 0)
            self.assertEqual(runner.mutation_count, 0)
            self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)
            self.assertEqual(load_backlog(root / "BACKLOG.md").mode, "local")

    def test_explicit_migration_migrates_archived_history_only_after_complete_success(self) -> None:
        runner = MutableGitHubRunner()
        gateway = gh.GitHubIssuesGateway(runner)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active_path = root / "BACKLOG.md"
            archive_path = root / "BACKLOG-ARCHIVE.md"
            active_path.write_text(
                render_backlog(BacklogDocument("EM", "local", (backlog_item("EM-002"),))),
                encoding="utf-8",
            )
            archive_path.write_text(
                render_backlog_archive(
                    BacklogDocument(
                        "EM", "local", (backlog_item("EM-001", TaskStatus.COMPLETE),)
                    )
                ),
                encoding="utf-8",
            )

            outcome = issues.migrate_local_backlog(active_path, gateway)

            self.assertEqual(outcome.document.mode, "github-cache")
            self.assertEqual(len(outcome.document.items), 2)
            self.assertFalse(archive_path.exists())


class CacheAndQueueRegressionTests(unittest.TestCase):
    def test_refresh_reads_remote_state_instead_of_remigrating_the_cache(self) -> None:
        document = BacklogDocument("EM", "local", (backlog_item("EM-001"),))
        runner = MutableGitHubRunner()
        gateway = gh.GitHubIssuesGateway(runner)
        cached = issues.migrate_backlog(document, gateway, REPOSITORY, language="en")
        method_issue = next(
            entry for entry in runner.issues if "engineering-method:issue" in str(entry["body"])
        )
        method_issue.update(
            {
                "title": "EM-001: Renamed remotely",
                "body": issue_body(
                    "EM-001", status="in_progress", priority="P0", notes="Remote truth"
                ),
                "state": "open",
                "labels": [
                    {"name": "engineering-method"},
                    {"name": "priority:p0"},
                    {"name": "status:in-progress"},
                ],
                "updated_at": "2026-09-04T14:00:00Z",
            }
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "BACKLOG.md"
            path.write_text(render_backlog(cached), encoding="utf-8")

            refreshed = issues.refresh_issue_cache(path, gateway, REPOSITORY)

            self.assertEqual(refreshed.items[0].title, "Renamed remotely")
            self.assertEqual(refreshed.items[0].status, TaskStatus.IN_PROGRESS)
            self.assertEqual(refreshed.items[0].priority, Priority.P0)
            self.assertEqual(refreshed.items[0].notes, "Remote truth")
            self.assertEqual(load_backlog(path), refreshed)

    def test_queue_is_idempotent_across_restart_and_replays_pending_records_causally(self) -> None:
        document = BacklogDocument("EM", "local", (backlog_item("EM-001"),))
        runner = MutableGitHubRunner()
        gateway = gh.GitHubIssuesGateway(runner)
        cached = issues.migrate_backlog(document, gateway, REPOSITORY, language="en")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "BACKLOG.md"
            path.write_text(render_backlog(cached), encoding="utf-8")
            status_mutation = {
                "kind": "status",
                "backlog_id": "EM-001",
                "status": "complete",
                "notes": "Finished offline",
            }
            first_id = issues.queue_mutation(root, status_mutation)
            self.assertEqual(issues.queue_mutation(root, status_mutation), first_id)
            issues.queue_mutation(
                root,
                {"kind": "priority", "backlog_id": "EM-001", "priority": "P0"},
            )
            self.assertEqual(len(issues.pending_queue(root)), 2)

            runner.fail_once("update-issue")
            with self.assertRaisesRegex(RuntimeError, "update-issue"):
                issues.replay_pending_queue(root, path, gateway, REPOSITORY)
            self.assertEqual(len(issues.pending_queue(root)), 2)

            replayed = issues.replay_pending_queue(root, path, gateway, REPOSITORY)

            self.assertEqual(issues.pending_queue(root), ())
            self.assertEqual(replayed.items[0].status, TaskStatus.COMPLETE)
            self.assertEqual(replayed.items[0].priority, Priority.P0)
            records = [
                json.loads(line)
                for line in (root / ".engineering-method" / "github-queue.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            acknowledgements = [entry["id"] for entry in records if entry["state"] == "acknowledged"]
            self.assertEqual(acknowledgements, [entry["id"] for entry in issues.queue_records(root) if entry["state"] == "pending"])

    def test_malformed_pending_queue_payload_is_rejected_before_remote_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue = root / ".engineering-method" / "github-queue.jsonl"
            queue.parent.mkdir(parents=True)
            queue.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "id": "broken",
                        "state": "pending",
                        "queued_at": "2026-09-04T10:20:30Z",
                        "kind": "status",
                        "backlog_id": "EM-001",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "queue line.*invalid"):
                issues.pending_queue(root)

    def test_acknowledged_content_hash_can_be_queued_again_after_intervening_state(self) -> None:
        document = BacklogDocument("EM", "local", (backlog_item("EM-001"),))
        runner = MutableGitHubRunner()
        gateway = gh.GitHubIssuesGateway(runner)
        cached = issues.migrate_backlog(document, gateway, REPOSITORY, language="en")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "BACKLOG.md"
            path.write_text(render_backlog(cached), encoding="utf-8")
            complete = {
                "kind": "status",
                "backlog_id": "EM-001",
                "status": "complete",
            }
            in_progress = {
                "kind": "status",
                "backlog_id": "EM-001",
                "status": "in_progress",
            }
            first_complete_id = issues.queue_mutation(root, complete)
            issues.replay_pending_queue(root, path, gateway, REPOSITORY)
            issues.queue_mutation(root, in_progress)
            issues.replay_pending_queue(root, path, gateway, REPOSITORY)

            second_complete_id = issues.queue_mutation(root, complete)
            self.assertEqual(second_complete_id, first_complete_id)
            self.assertEqual(len(issues.pending_queue(root)), 1)
            final = issues.replay_pending_queue(root, path, gateway, REPOSITORY)

            self.assertEqual(final.items[0].status, TaskStatus.COMPLETE)

    def test_notes_round_trip_empty_and_literal_legacy_sentinel_unambiguously(self) -> None:
        document = BacklogDocument(
            "EM",
            "local",
            (
                backlog_item("EM-001", notes=""),
                backlog_item("EM-002", notes="_None_"),
            ),
        )
        runner = MutableGitHubRunner()
        gateway = gh.GitHubIssuesGateway(runner)
        cached = issues.migrate_backlog(document, gateway, REPOSITORY, language="en")
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "BACKLOG.md"
            path.write_text(render_backlog(cached), encoding="utf-8")
            refreshed = issues.refresh_issue_cache(path, gateway, REPOSITORY)
        self.assertEqual([entry.notes for entry in refreshed.items], ["", "_None_"])
        bodies = [
            str(entry["body"])
            for entry in runner.issues
            if "engineering-method:issue" in str(entry["body"])
        ]
        self.assertTrue(any('Notes JSON: ""' in body for body in bodies))

    def test_pull_request_marker_never_claims_or_updates_the_corresponding_issue(self) -> None:
        marker = '<!-- engineering-method:issue {"schema_version":1,"backlog_id":"EM-001"} -->'
        pull_request = remote_issue(
            1,
            101,
            identifier="EM-001",
            title="Pull request title",
            body=marker,
            labels=(),
        )
        pull_request["pull_request"] = {"url": "https://api.github.test/pulls/1"}
        runner = MutableGitHubRunner(issues=(pull_request,))
        document = BacklogDocument("EM", "local", (backlog_item("EM-001"),))

        issues.migrate_backlog(
            document, gh.GitHubIssuesGateway(runner), REPOSITORY, language="en"
        )

        self.assertEqual(runner.issues[0]["title"], "Pull request title")
        self.assertEqual(len(runner.issues), 2)

    def test_queue_write_rejects_an_engineering_state_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / ".engineering-method").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "escapes"):
                issues.queue_mutation(
                    root,
                    {"kind": "priority", "backlog_id": "EM-001", "priority": "P0"},
                )
            self.assertEqual(list(outside.iterdir()), [])


class DetectionReasonTests(unittest.TestCase):
    def test_preserves_distinct_no_remote_authentication_and_permission_reasons(self) -> None:
        cases = (
            ("no git remotes configured", "no GitHub remote"),
            ("authentication required; run gh auth login", "GitHub authentication unavailable"),
        )
        for stderr, expected in cases:
            runner = MutableGitHubRunner()
            runner.fail_once("detect")
            original = runner._failure

            def failure(operation: str, *, _stderr: str = stderr):
                result = original(operation)
                return gh.GhResult(1, "", _stderr) if result else None

            runner._failure = failure  # type: ignore[method-assign]
            with self.subTest(stderr=stderr):
                detection = gh.GitHubIssuesGateway(runner).detect_repository()
                self.assertIsNone(detection.repository)
                self.assertEqual(detection.reason, expected)

        read_only = MutableGitHubRunner(permission="READ")
        detection = gh.GitHubIssuesGateway(read_only).detect_repository()
        self.assertIsNone(detection.repository)
        self.assertEqual(detection.reason, "GitHub repository is not writable")


if __name__ == "__main__":
    unittest.main()
