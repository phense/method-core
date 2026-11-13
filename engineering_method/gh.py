"""Injected GitHub CLI boundary; ordinary tests never invoke a real subprocess."""

from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from typing import Protocol, Sequence


GH_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class GhResult:
    returncode: int
    stdout: str
    stderr: str


class GhRunner(Protocol):
    def run(self, args: Sequence[str], *, stdin: str | None = None) -> GhResult: ...


@dataclass(frozen=True)
class RepositoryRef:
    owner: str
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


@dataclass(frozen=True)
class RepositoryDetection:
    repository: RepositoryRef | None
    reason: str


@dataclass(frozen=True)
class RemoteLabel:
    name: str
    color: str
    description: str


@dataclass(frozen=True)
class RemoteIssue:
    """REST issue identity includes both database ID and human issue number."""

    id: int
    number: int
    title: str
    body: str
    state: str
    labels: tuple[str, ...]
    updated_at: str


class SubprocessGhRunner:
    """The sole live-process adapter, with fixed argument lists and a hard timeout."""

    def run(self, args: Sequence[str], *, stdin: str | None = None) -> GhResult:
        try:
            completed = subprocess.run(
                ["gh", *args],
                input=stdin,
                text=True,
                capture_output=True,
                check=False,
                timeout=GH_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return GhResult(124, "", f"gh command timed out after {GH_TIMEOUT_SECONDS} seconds")
        except OSError as error:
            return GhResult(127, "", str(error))
        return GhResult(completed.returncode, completed.stdout, completed.stderr)


def _json_result(result: GhResult, *, operation: str) -> object:
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"gh {operation} failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ValueError(f"gh {operation} returned malformed JSON") from error


def _slurped_items(result: GhResult, *, operation: str) -> list[object]:
    payload = _json_result(result, operation=operation)
    if not isinstance(payload, list) or not all(isinstance(page, list) for page in payload):
        raise ValueError(f"gh {operation} response is partial")
    return [entry for page in payload for entry in page]


def _remote_issue(payload: object) -> RemoteIssue:
    if not isinstance(payload, dict):
        raise ValueError("gh issue response is partial")
    required = {"id", "number", "title", "body", "state", "labels", "updated_at"}
    if not required <= payload.keys() or not isinstance(payload["labels"], list):
        raise ValueError("gh issue response is partial")
    if type(payload["id"]) is not int or type(payload["number"]) is not int:
        raise ValueError("gh issue response is partial")
    if payload["body"] is None:
        payload = {**payload, "body": ""}
    for field in ("title", "body", "state", "updated_at"):
        if not isinstance(payload[field], str):
            raise ValueError("gh issue response is partial")
    labels: list[str] = []
    for label in payload["labels"]:
        if not isinstance(label, dict) or not isinstance(label.get("name"), str):
            raise ValueError("gh issue response is partial")
        labels.append(label["name"])
    return RemoteIssue(
        id=payload["id"],
        number=payload["number"],
        title=payload["title"],
        body=payload["body"],
        state=payload["state"].lower(),
        labels=tuple(labels),
        updated_at=payload["updated_at"],
    )


class GitHubIssuesGateway:
    """All GitHub Issue transport shapes behind an injectable, testable runner."""

    def __init__(self, runner: GhRunner | None = None) -> None:
        self._runner = runner or SubprocessGhRunner()

    def detect_repository(self) -> RepositoryDetection:
        result = self._runner.run(("repo", "view", "--json", "nameWithOwner,viewerPermission"))
        if result.returncode != 0:
            detail = result.stderr.lower()
            if "remote" in detail or "not a git repository" in detail:
                reason = "no GitHub remote"
            elif any(word in detail for word in ("auth", "login", "token")):
                reason = "GitHub authentication unavailable"
            else:
                reason = "GitHub repository unavailable"
            return RepositoryDetection(None, reason)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return RepositoryDetection(None, "GitHub repository detection returned malformed data")
        if not isinstance(payload, dict):
            return RepositoryDetection(None, "GitHub repository detection returned malformed data")
        if payload.get("viewerPermission") not in {"WRITE", "MAINTAIN", "ADMIN"}:
            return RepositoryDetection(None, "GitHub repository is not writable")
        name_with_owner = payload.get("nameWithOwner")
        if not isinstance(name_with_owner, str) or name_with_owner.count("/") != 1:
            return RepositoryDetection(None, "GitHub repository detection returned malformed data")
        owner, name = name_with_owner.split("/", 1)
        if not owner or not name:
            return RepositoryDetection(None, "GitHub repository detection returned malformed data")
        return RepositoryDetection(
            RepositoryRef(owner, name), "writable authenticated GitHub repository detected"
        )

    def detect_writable_repository(self) -> RepositoryRef | None:
        """Compatibility projection for callers that do not need reason detail."""
        return self.detect_repository().repository

    def list_method_issues(self, repository: RepositoryRef) -> list[RemoteIssue]:
        endpoint = f"repos/{repository.full_name}/issues?state=all&per_page=100"
        values = _slurped_items(
            self._runner.run(("api", "--paginate", "--slurp", endpoint)),
            operation="issue list",
        )
        return [
            _remote_issue(entry)
            for entry in values
            if not isinstance(entry, dict) or "pull_request" not in entry
        ]

    def list_labels(self, repository: RepositoryRef) -> dict[str, RemoteLabel]:
        endpoint = f"repos/{repository.full_name}/labels?per_page=100"
        values = _slurped_items(
            self._runner.run(("api", "--paginate", "--slurp", endpoint)),
            operation="label list",
        )
        labels: dict[str, RemoteLabel] = {}
        for payload in values:
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("name"), str)
                or not isinstance(payload.get("color"), str)
                or payload.get("description") is not None
                and not isinstance(payload.get("description"), str)
            ):
                raise ValueError("gh label list response is partial")
            label = RemoteLabel(
                payload["name"], payload["color"], payload.get("description") or ""
            )
            if label.name in labels:
                raise ValueError("gh label list contains a duplicate name")
            labels[label.name] = label
        return labels

    def ensure_label(
        self,
        repository: RepositoryRef,
        *,
        name: str,
        color: str,
        description: str,
    ) -> None:
        result = self._runner.run(
            (
                "label",
                "create",
                name,
                "--repo",
                repository.full_name,
                "--color",
                color,
                "--description",
                description,
                "--force",
            )
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gh label upsert failed")

    def create_issue(
        self,
        repository: RepositoryRef,
        *,
        title: str,
        body: str,
        labels: Sequence[str],
        language: str = "en",
    ) -> RemoteIssue:
        if language != "en":
            raise ValueError("GitHub-authored content must declare English")
        request = json.dumps(
            {"title": title, "body": body, "labels": list(labels)}, separators=(",", ":")
        )
        payload = _json_result(
            self._runner.run(
                (
                    "api",
                    "--method",
                    "POST",
                    f"repos/{repository.full_name}/issues",
                    "--input",
                    "-",
                ),
                stdin=request,
            ),
            operation="issue create",
        )
        return _remote_issue(payload)

    def update_issue(
        self,
        repository: RepositoryRef,
        *,
        number: int,
        title: str,
        body: str,
        labels: Sequence[str],
        state: str,
        language: str = "en",
    ) -> RemoteIssue:
        if language != "en":
            raise ValueError("GitHub-authored content must declare English")
        if state not in {"open", "closed"}:
            raise ValueError("GitHub issue state must be open or closed")
        request = json.dumps(
            {
                "title": title,
                "body": body,
                "labels": list(labels),
                "state": state,
            },
            separators=(",", ":"),
        )
        payload = _json_result(
            self._runner.run(
                (
                    "api",
                    "--method",
                    "PATCH",
                    f"repos/{repository.full_name}/issues/{number}",
                    "--input",
                    "-",
                ),
                stdin=request,
            ),
            operation="issue update",
        )
        return _remote_issue(payload)

    def list_sub_issue_ids(
        self, repository: RepositoryRef, *, parent_number: int
    ) -> set[int]:
        endpoint = f"repos/{repository.full_name}/issues/{parent_number}/sub_issues?per_page=100"
        return self._relation_ids(endpoint, operation="sub-issue list")

    def list_blocker_ids(
        self, repository: RepositoryRef, *, blocked_number: int
    ) -> set[int]:
        endpoint = (
            f"repos/{repository.full_name}/issues/{blocked_number}/dependencies/blocked_by?per_page=100"
        )
        return self._relation_ids(endpoint, operation="dependency list")

    def _relation_ids(self, endpoint: str, *, operation: str) -> set[int]:
        values = _slurped_items(
            self._runner.run(("api", "--paginate", "--slurp", endpoint)), operation=operation
        )
        result: set[int] = set()
        for payload in values:
            if not isinstance(payload, dict) or type(payload.get("id")) is not int:
                raise ValueError(f"gh {operation} response is partial")
            result.add(payload["id"])
        return result

    def _relation_mutation(
        self,
        repository: RepositoryRef,
        *,
        method: str,
        number: int,
        suffix: str,
        field: str,
        database_id: int,
        operation: str,
    ) -> None:
        if type(database_id) is not int:
            raise ValueError("GitHub relationship IDs must be integer database IDs")
        result = self._runner.run(
            (
                "api",
                "--method",
                method,
                f"repos/{repository.full_name}/issues/{number}/{suffix}",
                "-F",
                f"{field}={database_id}",
            )
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or f"gh {operation} failed")

    def ensure_sub_issue(
        self, repository: RepositoryRef, *, parent_number: int, child_id: int
    ) -> None:
        self._relation_mutation(
            repository,
            method="POST",
            number=parent_number,
            suffix="sub_issues",
            field="sub_issue_id",
            database_id=child_id,
            operation="sub-issue relationship",
        )

    def remove_sub_issue(
        self, repository: RepositoryRef, *, parent_number: int, child_id: int
    ) -> None:
        self._relation_mutation(
            repository,
            method="DELETE",
            number=parent_number,
            suffix="sub_issue",
            field="sub_issue_id",
            database_id=child_id,
            operation="sub-issue removal",
        )

    def ensure_blocked_by(
        self, repository: RepositoryRef, *, blocked_number: int, blocker_id: int
    ) -> None:
        self._relation_mutation(
            repository,
            method="POST",
            number=blocked_number,
            suffix="dependencies/blocked_by",
            field="issue_id",
            database_id=blocker_id,
            operation="dependency relationship",
        )

    def remove_blocked_by(
        self, repository: RepositoryRef, *, blocked_number: int, blocker_id: int
    ) -> None:
        if type(blocker_id) is not int:
            raise ValueError("GitHub relationship IDs must be integer database IDs")
        result = self._runner.run(
            (
                "api",
                "--method",
                "DELETE",
                f"repos/{repository.full_name}/issues/{blocked_number}/"
                f"dependencies/blocked_by/{blocker_id}",
            )
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "gh dependency removal failed")
