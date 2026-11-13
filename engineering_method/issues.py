"""Convergent backlog migration, remote cache refresh, and durable queue replay."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
from typing import Callable, Mapping, Protocol, Sequence

from .backlog import (
    BacklogDocument,
    load_backlog,
    load_backlog_history,
    render_backlog,
)
from .files import append_jsonl, atomic_write_text, require_contained_path
from .gh import RemoteIssue, RemoteLabel, RepositoryDetection, RepositoryRef
from .models import (
    BacklogItem,
    Priority,
    RFC_3339_UTC_PATTERN,
    TaskStatus,
    parse_task_id,
    utc_timestamp,
)


ISSUE_MARKER_PATTERN = re.compile(
    r"<!-- engineering-method:issue (?P<payload>\{[^\n]*\}) -->"
)
ISSUE_PREFIX = "<!-- engineering-method:issue "
CONTROLLED_LABELS: tuple[tuple[str, str, str], ...] = (
    ("engineering-method", "0B7285", "Managed by Peter's Engineering Method."),
    ("priority:p0", "B60205", "Blocking or urgent work."),
    ("priority:p1", "D93F0B", "Next planned work."),
    ("priority:p2", "FBCA04", "Planned work."),
    ("priority:p3", "C5DEF5", "Later improvement."),
    ("status:open", "1D76DB", "Open Engineering Method work."),
    ("status:in-progress", "5319E7", "Engineering Method work in progress."),
    ("status:blocked", "B60205", "Engineering Method work currently blocked."),
)
CONTROLLED_LABEL_NAMES = frozenset(label[0] for label in CONTROLLED_LABELS)
QUEUE_SCHEMA_VERSION = 1
QUEUE_KINDS = frozenset({"add", "status", "priority", "dependencies"})


class IssueGateway(Protocol):
    def detect_repository(self) -> RepositoryDetection: ...
    def list_method_issues(self, repository: RepositoryRef) -> list[RemoteIssue]: ...
    def list_labels(self, repository: RepositoryRef) -> dict[str, RemoteLabel]: ...
    def ensure_label(
        self, repository: RepositoryRef, *, name: str, color: str, description: str
    ) -> None: ...
    def create_issue(
        self,
        repository: RepositoryRef,
        *,
        title: str,
        body: str,
        labels: Sequence[str],
        language: str = "en",
    ) -> RemoteIssue: ...
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
    ) -> RemoteIssue: ...
    def list_sub_issue_ids(
        self, repository: RepositoryRef, *, parent_number: int
    ) -> set[int]: ...
    def list_blocker_ids(
        self, repository: RepositoryRef, *, blocked_number: int
    ) -> set[int]: ...
    def ensure_sub_issue(
        self, repository: RepositoryRef, *, parent_number: int, child_id: int
    ) -> None: ...
    def remove_sub_issue(
        self, repository: RepositoryRef, *, parent_number: int, child_id: int
    ) -> None: ...
    def ensure_blocked_by(
        self, repository: RepositoryRef, *, blocked_number: int, blocker_id: int
    ) -> None: ...
    def remove_blocked_by(
        self, repository: RepositoryRef, *, blocked_number: int, blocker_id: int
    ) -> None: ...


@dataclass(frozen=True)
class StateCheckResult:
    document: BacklogDocument
    reason: str


def _marker(backlog_id: str) -> str:
    return (
        f'{ISSUE_PREFIX}{{"schema_version":1,"backlog_id":"{backlog_id}"}} -->'
    )


def marker_backlog_id(body: str) -> str | None:
    """Return the one validated marker identity in a body, if present."""
    matches = list(ISSUE_MARKER_PATTERN.finditer(body))
    if ISSUE_PREFIX in body and not matches:
        raise ValueError("remote issue has a malformed method marker")
    if len(matches) > 1:
        raise ValueError("remote issue has ambiguous method markers")
    if not matches:
        return None
    try:
        payload = json.loads(matches[0].group("payload"))
    except json.JSONDecodeError as error:
        raise ValueError("remote issue has a malformed method marker") from error
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema_version", "backlog_id"}
        or payload.get("schema_version") != 1
        or not isinstance(payload.get("backlog_id"), str)
    ):
        raise ValueError("remote issue has an invalid method marker")
    parse_task_id(payload["backlog_id"])
    return payload["backlog_id"]


def _remote_map(
    items: tuple[BacklogItem, ...], remote: Sequence[RemoteIssue]
) -> dict[str, RemoteIssue]:
    known = {item.id for item in items}
    mapped: dict[str, RemoteIssue] = {}
    for issue in remote:
        item_id = marker_backlog_id(issue.body)
        if item_id is None:
            continue
        if item_id not in known:
            raise ValueError(f"remote issue has an unknown method marker: {item_id}")
        if item_id in mapped:
            raise ValueError("duplicate remote marker")
        mapped[item_id] = issue
    return mapped


def _labels(item: BacklogItem) -> tuple[str, ...]:
    labels = ["engineering-method", f"priority:{item.priority.value.lower()}"]
    if item.status is not TaskStatus.COMPLETE:
        labels.append(f"status:{item.status.value.replace('_', '-')}")
    return tuple(labels)


def _body(item: BacklogItem) -> str:
    notes = json.dumps(item.notes, ensure_ascii=False)
    return (
        f"{_marker(item.id)}\n\n"
        f"Backlog status: `{item.status.value}`\n"
        f"Priority: `{item.priority.value}`\n"
        f"Notes JSON: {notes}\n"
    )


def _title(item: BacklogItem) -> str:
    return f"{item.id}: {item.title}"


def _desired_remote_labels(item: BacklogItem, remote: RemoteIssue | None) -> tuple[str, ...]:
    preserved = () if remote is None else tuple(
        label
        for label in remote.labels
        if label not in CONTROLLED_LABEL_NAMES
        and not label.startswith("priority:")
        and not label.startswith("status:")
    )
    return preserved + _labels(item)


def _provision_labels(gateway: IssueGateway, repository: RepositoryRef) -> None:
    current = gateway.list_labels(repository)
    for name, color, description in CONTROLLED_LABELS:
        existing = current.get(name)
        if (
            existing is None
            or existing.color.lower() != color.lower()
            or existing.description != description
        ):
            gateway.ensure_label(
                repository, name=name, color=color, description=description
            )


def migrate_backlog(
    document: BacklogDocument,
    gateway: IssueGateway,
    repository: RepositoryRef,
    *,
    language: str,
) -> BacklogDocument:
    """Converge issues and native relationships; safe to retry after any partial failure."""
    if language != "en":
        raise ValueError("GitHub-authored content must declare English")
    _provision_labels(gateway, repository)
    mapping = _remote_map(document.items, gateway.list_method_issues(repository))

    for item in document.items:
        remote = mapping.get(item.id)
        desired_labels = _desired_remote_labels(item, remote)
        desired_state = "closed" if item.status is TaskStatus.COMPLETE else "open"
        if remote is None:
            mapping[item.id] = gateway.create_issue(
                repository,
                title=_title(item),
                body=_body(item),
                labels=desired_labels,
                language=language,
            )
            remote = mapping[item.id]
        if (
            remote.title != _title(item)
            or remote.body != _body(item)
            or set(remote.labels) != set(desired_labels)
            or remote.state.lower() != desired_state
        ):
            mapping[item.id] = gateway.update_issue(
                repository,
                number=remote.number,
                title=_title(item),
                body=_body(item),
                labels=desired_labels,
                state=desired_state,
                language=language,
            )

    method_database_ids = {remote.id for remote in mapping.values()}
    sub_issue_changes: list[tuple[RemoteIssue, set[int], set[int]]] = []
    for parent_item in document.items:
        parent_remote = mapping[parent_item.id]
        desired_children = {
            mapping[item.id].id
            for item in document.items
            if item.parent_id == parent_item.id
        }
        current_children = gateway.list_sub_issue_ids(
            repository, parent_number=parent_remote.number
        ) & method_database_ids
        sub_issue_changes.append((parent_remote, current_children, desired_children))
    for parent_remote, current_children, desired_children in sub_issue_changes:
        for child_id in sorted(current_children - desired_children):
            gateway.remove_sub_issue(
                repository, parent_number=parent_remote.number, child_id=child_id
            )
    for parent_remote, current_children, desired_children in sub_issue_changes:
        for child_id in sorted(desired_children - current_children):
            gateway.ensure_sub_issue(
                repository, parent_number=parent_remote.number, child_id=child_id
            )

    dependency_changes: list[tuple[RemoteIssue, set[int], set[int]]] = []
    for item in document.items:
        remote = mapping[item.id]
        desired_blockers = {mapping[dependency].id for dependency in item.depends_on}
        current_blockers = gateway.list_blocker_ids(
            repository, blocked_number=remote.number
        ) & method_database_ids
        dependency_changes.append((remote, current_blockers, desired_blockers))
    for remote, current_blockers, desired_blockers in dependency_changes:
        for blocker_id in sorted(current_blockers - desired_blockers):
            gateway.remove_blocked_by(
                repository, blocked_number=remote.number, blocker_id=blocker_id
            )
    for remote, current_blockers, desired_blockers in dependency_changes:
        for blocker_id in sorted(desired_blockers - current_blockers):
            gateway.ensure_blocked_by(
                repository, blocked_number=remote.number, blocker_id=blocker_id
            )
    return BacklogDocument(document.project_key, "github-cache", document.items)


def _method_issues(remote: Sequence[RemoteIssue]) -> dict[str, RemoteIssue]:
    mapped: dict[str, RemoteIssue] = {}
    for issue in remote:
        identifier = marker_backlog_id(issue.body)
        if identifier is None:
            continue
        if identifier in mapped:
            raise ValueError("duplicate remote marker")
        mapped[identifier] = issue
    return mapped


def _parse_remote_item(
    identifier: str,
    issue: RemoteIssue,
    *,
    parent_id: str | None,
    depends_on: tuple[str, ...],
) -> BacklogItem:
    title_prefix = f"{identifier}: "
    if not issue.title.startswith(title_prefix) or not issue.title.removeprefix(title_prefix).strip():
        raise ValueError("remote issue title and marker disagree")
    status_match = re.search(r"^Backlog status: `([^`]+)`$", issue.body, re.MULTILINE)
    priority_match = re.search(r"^Priority: `(P[0-3])`$", issue.body, re.MULTILINE)
    notes_match = re.search(r"^Notes JSON: (.*)$", issue.body, re.MULTILINE)
    if status_match is None or priority_match is None or notes_match is None:
        raise ValueError("remote issue body is incomplete")
    try:
        body_status = TaskStatus(status_match.group(1))
        priority = Priority(priority_match.group(1))
    except ValueError as error:
        raise ValueError("remote issue body contains invalid state") from error
    priority_labels = [label for label in issue.labels if label.startswith("priority:")]
    status_labels = [label for label in issue.labels if label.startswith("status:")]
    if priority_labels != [f"priority:{priority.value.lower()}"]:
        raise ValueError("remote issue labels and body priority disagree")
    if issue.state.lower() == "closed":
        visible_status = TaskStatus.COMPLETE
        if status_labels:
            raise ValueError("closed remote issue must not retain a workflow status label")
    elif issue.state.lower() == "open" and len(status_labels) == 1:
        try:
            visible_status = TaskStatus(status_labels[0].removeprefix("status:").replace("-", "_"))
        except ValueError as error:
            raise ValueError("remote issue has an invalid workflow status label") from error
    else:
        raise ValueError("remote issue state or status labels are invalid")
    if visible_status is not body_status:
        raise ValueError("remote issue body and visible status disagree")
    try:
        notes = json.loads(notes_match.group(1))
    except json.JSONDecodeError as error:
        raise ValueError("remote issue notes encoding is invalid") from error
    if not isinstance(notes, str):
        raise ValueError("remote issue notes encoding must contain text")
    return BacklogItem(
        id=identifier,
        title=issue.title.removeprefix(title_prefix),
        status=visible_status,
        priority=priority,
        parent_id=parent_id,
        depends_on=depends_on,
        notes=notes,
        updated_at=issue.updated_at,
    )


def remote_backlog(
    gateway: IssueGateway,
    repository: RepositoryRef,
    *,
    project_key: str | None = None,
) -> BacklogDocument:
    """Build a validated cache document from live remote issues and native relations."""
    mapped = _method_issues(gateway.list_method_issues(repository))
    if not mapped:
        if project_key is None:
            raise ValueError("GitHub repository has no Engineering Method issues")
        return BacklogDocument(project_key, "github-cache", ())
    keys = {parse_task_id(identifier)[0] for identifier in mapped}
    if len(keys) != 1 or (project_key is not None and keys != {project_key}):
        raise ValueError("remote issue project key does not match the cache")
    by_database_id = {issue.id: identifier for identifier, issue in mapped.items()}
    parents: dict[str, str] = {}
    for parent_id, remote in mapped.items():
        for child_database_id in gateway.list_sub_issue_ids(
            repository, parent_number=remote.number
        ):
            child_id = by_database_id.get(child_database_id)
            if child_id is None:
                continue
            if child_id in parents and parents[child_id] != parent_id:
                raise ValueError("remote issue has multiple method parents")
            parents[child_id] = parent_id
    dependencies: dict[str, tuple[str, ...]] = {}
    for identifier, remote in mapped.items():
        blocker_ids = gateway.list_blocker_ids(
            repository, blocked_number=remote.number
        )
        dependencies[identifier] = tuple(
            sorted(
                (by_database_id[database_id] for database_id in blocker_ids if database_id in by_database_id),
                key=lambda value: parse_task_id(value)[1],
            )
        )
    items = tuple(
        _parse_remote_item(
            identifier,
            mapped[identifier],
            parent_id=parents.get(identifier),
            depends_on=dependencies[identifier],
        )
        for identifier in sorted(mapped, key=lambda value: parse_task_id(value)[1])
    )
    return BacklogDocument(next(iter(keys)), "github-cache", items)


def refresh_issue_cache(
    path: Path,
    gateway: IssueGateway,
    repository: RepositoryRef,
) -> BacklogDocument:
    """Replace a generated cache from remote canonical state without writing remote data."""
    current = load_backlog(path)
    if current.mode != "github-cache":
        raise ValueError("issue cache refresh requires github-cache mode")
    refreshed = remote_backlog(gateway, repository, project_key=current.project_key)
    atomic_write_text(path, render_backlog(refreshed))
    return refreshed


def _detection(gateway: IssueGateway) -> RepositoryDetection:
    if hasattr(gateway, "detect_repository"):
        return gateway.detect_repository()
    repository = gateway.detect_writable_repository()  # type: ignore[attr-defined]
    return RepositoryDetection(
        repository,
        "writable authenticated GitHub repository detected"
        if repository is not None
        else "no writable authenticated GitHub repository",
    )


def workflow_state_check(path: Path, gateway: IssueGateway) -> StateCheckResult:
    """Report canonical mode and remote availability without changing either."""
    document = load_backlog(path)
    detection = _detection(gateway)
    if detection.repository is None:
        return StateCheckResult(document, detection.reason)
    if document.mode == "github-cache":
        return StateCheckResult(document, "GitHub Issues cache already canonical")
    return StateCheckResult(
        document,
        "local backlog remains canonical; writable GitHub repository available; "
        "explicit backlog-to-issues migrate required",
    )


def migrate_local_backlog(path: Path, gateway: IssueGateway) -> StateCheckResult:
    """Explicitly migrate local history after caller authorization."""
    document = load_backlog(path)
    detection = _detection(gateway)
    if detection.repository is None:
        return StateCheckResult(document, detection.reason)
    if document.mode == "github-cache":
        return StateCheckResult(document, "GitHub Issues cache already canonical")
    history = load_backlog_history(path)
    migrated = migrate_backlog(history, gateway, detection.repository, language="en")
    atomic_write_text(path, render_backlog(migrated))
    archive = path.with_name("BACKLOG-ARCHIVE.md")
    if archive.exists():
        archive.unlink()
    return StateCheckResult(migrated, "migrated local backlog to canonical GitHub Issues")


def _queue_path(root: Path) -> Path:
    return require_contained_path(
        root,
        root / ".engineering-method" / "github-queue.jsonl",
        field="GitHub queue path",
    )


def queue_records(root: Path) -> tuple[dict[str, object], ...]:
    path = _queue_path(root)
    if not path.exists():
        return ()
    records: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"GitHub queue line {line_number} is malformed") from error
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != QUEUE_SCHEMA_VERSION
            or payload.get("state") not in {"pending", "acknowledged"}
            or not isinstance(payload.get("id"), str)
        ):
            raise ValueError(f"GitHub queue line {line_number} is invalid")
        records.append(payload)
    return tuple(records)


def pending_queue(root: Path) -> tuple[dict[str, object], ...]:
    pending: dict[str, dict[str, object]] = {}
    for record in queue_records(root):
        identifier = record["id"]
        if record["state"] == "pending" and identifier not in pending:
            pending[identifier] = record
        elif record["state"] == "acknowledged":
            pending.pop(identifier, None)
    result = tuple(pending.values())
    for record in result:
        mutation = {
            key: value
            for key, value in record.items()
            if key not in {"schema_version", "id", "state", "queued_at"}
        }
        try:
            _validated_mutation(mutation)
        except (TypeError, ValueError) as error:
            raise ValueError(f"GitHub queue line is invalid: {error}") from error
    return result


def _validated_mutation(mutation: Mapping[str, object]) -> dict[str, object]:
    if any(key in mutation for key in ("id", "state", "schema_version", "queued_at")):
        raise ValueError("queued mutation contains producer-owned fields")
    kind = mutation.get("kind")
    backlog_id = mutation.get("backlog_id")
    if kind not in QUEUE_KINDS or not isinstance(backlog_id, str):
        raise ValueError("queued mutation kind or backlog ID is invalid")
    parse_task_id(backlog_id)
    payload = dict(mutation)
    allowed = {
        "add": {
            "kind",
            "backlog_id",
            "title",
            "priority",
            "parent_id",
            "depends_on",
            "notes",
            "updated_at",
        },
        "status": {"kind", "backlog_id", "status", "notes", "updated_at"},
        "priority": {"kind", "backlog_id", "priority", "updated_at"},
        "dependencies": {"kind", "backlog_id", "depends_on", "updated_at"},
    }[kind]
    if not set(payload) <= allowed:
        raise ValueError("queued mutation contains unknown fields")
    if "updated_at" in payload and (
        not isinstance(payload["updated_at"], str)
        or RFC_3339_UTC_PATTERN.fullmatch(payload["updated_at"]) is None
    ):
        raise ValueError("queued mutation updated_at is invalid")
    if "notes" in payload and (
        not isinstance(payload["notes"], str)
        or "\n" in payload["notes"]
        or "\r" in payload["notes"]
    ):
        raise ValueError("queued mutation notes must be single-line text")
    if kind == "add":
        required = {"kind", "backlog_id", "title", "priority"}
        if not required <= payload.keys():
            raise ValueError("queued add mutation is incomplete")
        if (
            not isinstance(payload["title"], str)
            or not payload["title"].strip()
            or "\n" in payload["title"]
            or "\r" in payload["title"]
        ):
            raise ValueError("queued add title must be non-empty single-line text")
        Priority(payload["priority"])
        parent = payload.get("parent_id")
        if parent is not None:
            if not isinstance(parent, str):
                raise ValueError("queued add parent ID is invalid")
            parse_task_id(parent)
        dependencies = payload.get("depends_on", [])
        if not isinstance(dependencies, list):
            raise ValueError("queued add dependencies must be a list")
        for dependency in dependencies:
            if not isinstance(dependency, str):
                raise ValueError("queued add dependency ID is invalid")
            parse_task_id(dependency)
    elif kind == "status":
        TaskStatus(payload.get("status"))
    elif kind == "priority":
        Priority(payload.get("priority"))
    elif kind == "dependencies":
        if not isinstance(payload.get("depends_on"), list):
            raise ValueError("queued dependency mutation requires a list")
        for dependency in payload["depends_on"]:
            parse_task_id(dependency)
    return payload


def queue_mutation(root: Path, mutation: Mapping[str, object]) -> str:
    """Append one content-addressed pending mutation unless that ID was already recorded."""
    payload = _validated_mutation(mutation)
    canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    identifier = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if any(record["id"] == identifier for record in pending_queue(root)):
        return identifier
    record = {
        "schema_version": QUEUE_SCHEMA_VERSION,
        "id": identifier,
        "state": "pending",
        "queued_at": utc_timestamp(),
        **payload,
    }
    append_jsonl(_queue_path(root), record)
    return identifier


def _apply_mutation(document: BacklogDocument, mutation: Mapping[str, object]) -> BacklogDocument:
    identifier = str(mutation["backlog_id"])
    kind = mutation["kind"]
    items = list(document.items)
    index = next((position for position, item in enumerate(items) if item.id == identifier), None)
    if kind == "add":
        if index is not None:
            raise ValueError("queued add mutation targets an existing backlog ID")
        parent = mutation.get("parent_id")
        dependencies = mutation.get("depends_on", [])
        item = BacklogItem(
            identifier,
            str(mutation["title"]),
            TaskStatus.OPEN,
            Priority(mutation["priority"]),
            str(parent) if parent is not None else None,
            tuple(str(value) for value in dependencies),
            str(mutation.get("notes", "")),
            str(mutation.get("updated_at", utc_timestamp())),
        )
        items.append(item)
    else:
        if index is None:
            raise ValueError("queued mutation targets a missing backlog ID")
        current = items[index]
        if kind == "status":
            items[index] = replace(
                current,
                status=TaskStatus(mutation["status"]),
                notes=str(mutation.get("notes", current.notes)),
                updated_at=str(mutation.get("updated_at", utc_timestamp())),
            )
        elif kind == "priority":
            items[index] = replace(
                current,
                priority=Priority(mutation["priority"]),
                updated_at=str(mutation.get("updated_at", utc_timestamp())),
            )
        else:
            items[index] = replace(
                current,
                depends_on=tuple(str(value) for value in mutation["depends_on"]),
                updated_at=str(mutation.get("updated_at", utc_timestamp())),
            )
    return BacklogDocument(document.project_key, "github-cache", tuple(items))


def overlay_pending_queue(root: Path, document: BacklogDocument) -> BacklogDocument:
    """Apply durable pending records in memory for validation of later offline changes."""
    current = document
    for mutation in pending_queue(root):
        current = _apply_mutation(current, mutation)
    return current


def replay_pending_queue(
    root: Path,
    cache_path: Path,
    gateway: IssueGateway,
    repository: RepositoryRef,
) -> BacklogDocument:
    """Replay pending records in causal order and acknowledge only converged mutations."""
    cache = load_backlog(cache_path)
    if cache.mode != "github-cache":
        raise ValueError("queue replay requires github-cache mode")
    current = remote_backlog(gateway, repository, project_key=cache.project_key)
    for mutation in pending_queue(root):
        desired = _apply_mutation(current, mutation)
        current = migrate_backlog(desired, gateway, repository, language="en")
        append_jsonl(
            _queue_path(root),
            {
                "schema_version": QUEUE_SCHEMA_VERSION,
                "id": mutation["id"],
                "state": "acknowledged",
            },
        )
    refreshed = remote_backlog(gateway, repository, project_key=cache.project_key)
    atomic_write_text(cache_path, render_backlog(refreshed))
    return refreshed


def reconcile_queue(
    root: Path,
    mutation: Mapping[str, object],
    *,
    send: Callable[[dict[str, object]], None],
) -> None:
    """Compatibility helper for callers supplying their own idempotent sender."""
    if not isinstance(mutation.get("id"), str) or not mutation["id"]:
        raise ValueError("queued GitHub mutation requires a non-empty id")
    event = dict(mutation)
    event["schema_version"] = QUEUE_SCHEMA_VERSION
    event["state"] = "pending"
    append_jsonl(_queue_path(root), event)
    send(event)
    append_jsonl(
        _queue_path(root),
        {"schema_version": QUEUE_SCHEMA_VERSION, "id": event["id"], "state": "acknowledged"},
    )
