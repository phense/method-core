"""Contract tests for the injected, network-free GitHub Issues boundary."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from engineering_method.backlog import BacklogDocument, load_backlog
from engineering_method.gh import GhResult, GitHubIssuesGateway, RepositoryRef
from engineering_method.issues import migrate_backlog, reconcile_queue, workflow_state_check
from engineering_method.models import BacklogItem, Priority, TaskStatus
from tests.fakes import ExpectedGhCall, FakeGhRunner, MutableGitHubRunner


REPOSITORY = RepositoryRef("peter", "engineering-method")


def result(payload: object, *, returncode: int = 0, stderr: str = "") -> GhResult:
    return GhResult(returncode=returncode, stdout=json.dumps(payload), stderr=stderr)


def remote_payload(number: int = 12, database_id: int = 8_012) -> dict[str, object]:
    return {
        "id": database_id,
        "number": number,
        "title": "EM-002: State",
        "body": "marker",
        "state": "open",
        "labels": [{"name": "engineering-method"}],
        "updated_at": "2026-09-04T12:00:00Z",
    }


def backlog_item(identifier: str = "EM-001") -> BacklogItem:
    return BacklogItem(
        identifier,
        "English state",
        TaskStatus.OPEN,
        Priority.P1,
        None,
        (),
        "",
        "2026-09-04T10:20:30Z",
    )


class GitHubDetectionTests(unittest.TestCase):
    def test_detects_each_writable_permission(self) -> None:
        for permission in ("WRITE", "MAINTAIN", "ADMIN"):
            runner = FakeGhRunner(
                (
                    ExpectedGhCall(
                        ("repo", "view", "--json", "nameWithOwner,viewerPermission"),
                        result(
                            {
                                "nameWithOwner": "peter/engineering-method",
                                "viewerPermission": permission,
                            }
                        ),
                    ),
                )
            )
            with self.subTest(permission=permission):
                self.assertEqual(
                    GitHubIssuesGateway(runner).detect_writable_repository(), REPOSITORY
                )
                runner.assert_drained()

    def test_malformed_or_read_only_detection_is_not_writable(self) -> None:
        responses = (
            GhResult(0, "[", ""),
            result(
                {
                    "nameWithOwner": "peter/engineering-method",
                    "viewerPermission": "READ",
                }
            ),
        )
        for response in responses:
            runner = FakeGhRunner(
                (
                    ExpectedGhCall(
                        ("repo", "view", "--json", "nameWithOwner,viewerPermission"), response
                    ),
                )
            )
            with self.subTest(response=response):
                self.assertIsNone(GitHubIssuesGateway(runner).detect_writable_repository())


class GitHubIssueOperationsTests(unittest.TestCase):
    def test_lists_complete_rest_issues_and_rejects_partial_responses(self) -> None:
        command = (
            "api",
            "--paginate",
            "--slurp",
            "repos/peter/engineering-method/issues?state=all&per_page=100",
        )
        runner = FakeGhRunner((ExpectedGhCall(command, result([[remote_payload()]])),))
        issues = GitHubIssuesGateway(runner).list_method_issues(REPOSITORY)
        self.assertEqual((issues[0].id, issues[0].number), (8_012, 12))

        partial = FakeGhRunner(
            (ExpectedGhCall(command, result([[{"number": 12, "title": "partial"}]])),)
        )
        with self.assertRaisesRegex(ValueError, "partial"):
            GitHubIssuesGateway(partial).list_method_issues(REPOSITORY)

    def test_nonzero_issue_list_raises_without_claiming_success(self) -> None:
        runner = FakeGhRunner(
            (
                ExpectedGhCall(
                    (
                        "api",
                        "--paginate",
                        "--slurp",
                        "repos/peter/engineering-method/issues?state=all&per_page=100",
                    ),
                    GhResult(1, "", "connection refused"),
                ),
            )
        )
        with self.assertRaisesRegex(RuntimeError, "connection refused"):
            GitHubIssuesGateway(runner).list_method_issues(REPOSITORY)

    def test_accepts_valid_null_rest_body_and_label_description(self) -> None:
        issue = remote_payload()
        issue["body"] = None
        runner = FakeGhRunner(
            (
                ExpectedGhCall(
                    (
                        "api",
                        "--paginate",
                        "--slurp",
                        "repos/peter/engineering-method/issues?state=all&per_page=100",
                    ),
                    result([[issue]]),
                ),
                ExpectedGhCall(
                    (
                        "api",
                        "--paginate",
                        "--slurp",
                        "repos/peter/engineering-method/labels?per_page=100",
                    ),
                    result([[{"name": "engineering-method", "color": "0b7285", "description": None}]]),
                ),
            )
        )
        gateway = GitHubIssuesGateway(runner)
        self.assertEqual(gateway.list_method_issues(REPOSITORY)[0].body, "")
        self.assertEqual(gateway.list_labels(REPOSITORY)["engineering-method"].description, "")

    def test_creates_an_issue_with_json_stdin_and_complete_rest_identity(self) -> None:
        body = '<!-- engineering-method:issue {"schema_version":1,"backlog_id":"EM-002"} -->'
        request = json.dumps(
            {"title": "EM-002: State", "body": body, "labels": ["engineering-method"]},
            separators=(",", ":"),
        )
        payload = remote_payload(number=13, database_id=9_013)
        payload.update({"title": "EM-002: State", "body": body})
        runner = FakeGhRunner(
            (
                ExpectedGhCall(
                    (
                        "api",
                        "--method",
                        "POST",
                        "repos/peter/engineering-method/issues",
                        "--input",
                        "-",
                    ),
                    result(payload),
                    stdin=request,
                ),
            )
        )
        created = GitHubIssuesGateway(runner).create_issue(
            REPOSITORY,
            title="EM-002: State",
            body=body,
            labels=("engineering-method",),
        )
        self.assertEqual((created.id, created.number), (9_013, 13))
        runner.assert_drained()

    def test_removal_routes_match_github_rest_contracts(self) -> None:
        runner = FakeGhRunner(
            (
                ExpectedGhCall(
                    (
                        "api",
                        "--method",
                        "DELETE",
                        "repos/peter/engineering-method/issues/10/sub_issue",
                        "-F",
                        "sub_issue_id=9011",
                    ),
                    GhResult(0, "", ""),
                ),
                ExpectedGhCall(
                    (
                        "api",
                        "--method",
                        "DELETE",
                        "repos/peter/engineering-method/issues/11/dependencies/blocked_by/9010",
                    ),
                    GhResult(0, "", ""),
                ),
            )
        )
        gateway = GitHubIssuesGateway(runner)
        gateway.remove_sub_issue(REPOSITORY, parent_number=10, child_id=9011)
        gateway.remove_blocked_by(REPOSITORY, blocked_number=11, blocker_id=9010)
        runner.assert_drained()

    def test_excludes_pull_request_rows_even_when_their_body_contains_a_marker(self) -> None:
        command = (
            "api",
            "--paginate",
            "--slurp",
            "repos/peter/engineering-method/issues?state=all&per_page=100",
        )
        pull_request = {
            **remote_payload(11, 8_011),
            "body": '<!-- engineering-method:issue {"schema_version":1,"backlog_id":"EM-001"} -->',
            "pull_request": {"url": "https://api.github.test/pulls/11"},
        }
        issue = remote_payload(12, 8_012)
        runner = FakeGhRunner((ExpectedGhCall(command, result([[pull_request, issue]])),))
        found = GitHubIssuesGateway(runner).list_method_issues(REPOSITORY)
        self.assertEqual([entry.number for entry in found], [12])


class MigrationSafetyTests(unittest.TestCase):
    def test_rejects_non_english_duplicate_and_unknown_markers(self) -> None:
        document = BacklogDocument("EM", "local", (backlog_item(),))
        with self.assertRaisesRegex(ValueError, "English"):
            migrate_backlog(document, object(), REPOSITORY, language="de")  # type: ignore[arg-type]

        marker = '<!-- engineering-method:issue {"schema_version":1,"backlog_id":"EM-001"} -->'
        duplicate_runner = MutableGitHubRunner(
            issues=(
                {**remote_payload(1, 101), "body": marker},
                {**remote_payload(2, 102), "body": marker},
            )
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            migrate_backlog(
                document,
                GitHubIssuesGateway(duplicate_runner),
                REPOSITORY,
                language="en",
            )

        unknown = marker.replace("EM-001", "EM-999")
        unknown_runner = MutableGitHubRunner(
            issues=({**remote_payload(1, 101), "body": unknown},)
        )
        with self.assertRaisesRegex(ValueError, "unknown"):
            migrate_backlog(
                document,
                GitHubIssuesGateway(unknown_runner),
                REPOSITORY,
                language="en",
            )

    def test_state_check_keeps_local_mode_without_writable_remote(self) -> None:
        class NoRemoteGateway:
            def detect_writable_repository(self):
                return None

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "BACKLOG.md"
            path.write_text("# Backlog\n\n- ⭕ `EM-001` **P1** Local\n", encoding="utf-8")
            outcome = workflow_state_check(path, NoRemoteGateway())  # type: ignore[arg-type]
            self.assertEqual(outcome.reason, "no writable authenticated GitHub repository")
            self.assertEqual(load_backlog(path).mode, "local")

    def test_compatibility_sender_acknowledges_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sent: list[str] = []
            reconcile_queue(
                root,
                {"id": "one", "kind": "change"},
                send=lambda event: sent.append(str(event["id"])),
            )
            self.assertEqual(sent, ["one"])
            records = [
                json.loads(line)
                for line in (root / ".engineering-method" / "github-queue.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            self.assertEqual([record["state"] for record in records], ["pending", "acknowledged"])


if __name__ == "__main__":
    unittest.main()
