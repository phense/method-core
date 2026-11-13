"""Canonical local backlog parsing, rendering, ordering, and archiving."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable, Literal

from .files import atomic_write_bundle, atomic_write_text
from .models import (
    BacklogItem,
    PROJECT_KEY_PATTERN,
    Priority,
    TaskStatus,
    parse_task_id,
    validate_backlog_items,
)


SCHEMA_VERSION = 1
MARKER_PATTERN = re.compile(r"^\s*<!-- engineering-method:backlog (?P<payload>\{.*\}) -->\s*$")
DOCUMENT_MARKER_PATTERN = re.compile(
    r"^<!-- engineering-method:backlog-document (?P<payload>\{.*\}) -->$"
)
DISPLAY_PATTERN = re.compile(
    r"^(?P<indent>\s*)-\s+(?P<emoji>[⭕🔄✅❌])\s+`(?P<id>[^`]+)`\s+"
    r"(?:\*\*(?P<priority>P[0-3])\*\*\s+)?(?P<title>.+)$"
)
STATUS_EMOJI = {
    TaskStatus.OPEN: "⭕",
    TaskStatus.IN_PROGRESS: "🔄",
    TaskStatus.COMPLETE: "✅",
    TaskStatus.BLOCKED: "❌",
}
EMOJI_STATUS = {emoji: status for status, emoji in STATUS_EMOJI.items()}
PRIORITY_RANK = {Priority.P0: 0, Priority.P1: 1, Priority.P2: 2, Priority.P3: 3}
GITHUB_CACHE_NOTICE = "Generated GitHub Issues cache — do not edit"


@dataclass(frozen=True)
class BacklogDocument:
    """The local canonical backlog or generated GitHub cache."""

    project_key: str
    mode: Literal["local", "github-cache"]
    items: tuple[BacklogItem, ...]

    def __post_init__(self) -> None:
        if not PROJECT_KEY_PATTERN.fullmatch(self.project_key):
            raise ValueError("backlog project key must be uppercase alphanumeric")
        if self.mode not in {"local", "github-cache"}:
            raise ValueError("backlog mode must be local or github-cache")
        if not isinstance(self.items, tuple):
            raise ValueError("backlog items must be a tuple")
        validated = validate_backlog_items(self.items)
        for entry in validated:
            item_project_key, _ = parse_task_id(entry.id)
            if item_project_key != self.project_key:
                raise ValueError("all backlog IDs must use the document project key")


def _task_sort_key(identifier: str) -> tuple[tuple[int, ...], str]:
    _, components = parse_task_id(identifier)
    return components, identifier


def _root_id(entry: BacklogItem, by_id: dict[str, BacklogItem]) -> str:
    current = entry
    while current.parent_id is not None:
        current = by_id[current.parent_id]
    return current.id


def _children_by_parent(by_id: dict[str, BacklogItem]) -> dict[str | None, list[BacklogItem]]:
    children: dict[str | None, list[BacklogItem]] = {}
    for entry in by_id.values():
        children.setdefault(entry.parent_id, []).append(entry)
    return children


def _subtree_ids(
    identifier: str, children: dict[str | None, list[BacklogItem]]
) -> set[str]:
    result = {identifier}
    for child in children.get(identifier, ()):
        result.update(_subtree_ids(child.id, children))
    return result


def _validate_dependency_graph(by_id: dict[str, BacklogItem]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValueError("backlog dependency cycle detected")
        if identifier in visited:
            return
        visiting.add(identifier)
        for dependency in by_id[identifier].depends_on:
            visit(dependency)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in by_id:
        visit(identifier)


def _is_descendant(identifier: str, ancestor: str, by_id: dict[str, BacklogItem]) -> bool:
    current = by_id[identifier]
    while current.parent_id is not None:
        if current.parent_id == ancestor:
            return True
        current = by_id[current.parent_id]
    return False


def _ordered_siblings(
    parent_id: str | None,
    *,
    children: dict[str | None, list[BacklogItem]],
    by_id: dict[str, BacklogItem],
) -> list[BacklogItem]:
    siblings = children.get(parent_id, [])
    if not siblings:
        return []
    subtree_by_sibling = {entry.id: _subtree_ids(entry.id, children) for entry in siblings}
    branch_by_id = {
        identifier: sibling_id
        for sibling_id, identifiers in subtree_by_sibling.items()
        for identifier in identifiers
    }
    dependencies: dict[str, set[str]] = {entry.id: set() for entry in siblings}
    blocked: set[str] = set()
    unblockers: set[str] = set()
    for sibling in siblings:
        subtree = subtree_by_sibling[sibling.id]
        if any(by_id[identifier].status is TaskStatus.BLOCKED for identifier in subtree):
            blocked.add(sibling.id)
        for identifier in subtree:
            for dependency in by_id[identifier].depends_on:
                dependency_branch = branch_by_id.get(dependency)
                if dependency_branch is not None and dependency_branch != sibling.id:
                    dependencies[sibling.id].add(dependency_branch)
                    if sibling.id in blocked:
                        unblockers.add(dependency_branch)

    def sort_key(identifier: str) -> tuple[int, int, tuple[int, ...], str]:
        subtree = subtree_by_sibling[identifier]
        rank = 0 if identifier in unblockers else 1 if identifier in blocked else 2
        priority = min(PRIORITY_RANK[by_id[item_id].priority] for item_id in subtree)
        components, stable_id = _task_sort_key(identifier)
        return rank, priority, components, stable_id

    pending = {entry.id for entry in siblings}
    placed: set[str] = set()
    result: list[BacklogItem] = []
    while pending:
        ready = sorted(
            (identifier for identifier in pending if dependencies[identifier] <= placed),
            key=sort_key,
        )
        if not ready:
            raise ValueError("backlog dependency cycle detected")
        identifier = ready[0]
        pending.remove(identifier)
        placed.add(identifier)
        result.append(by_id[identifier])
    return result


def _render_order_for_group(root_id: str, by_id: dict[str, BacklogItem]) -> list[BacklogItem]:
    children = _children_by_parent(by_id)
    roots = [entry for entry in children.get(None, ()) if entry.id == root_id]
    if len(roots) != 1:
        raise ValueError("backlog hierarchy must have one top-level group root")
    ordered: list[BacklogItem] = []

    def visit(entry: BacklogItem) -> None:
        ordered.append(entry)
        for child in _ordered_siblings(entry.id, children=children, by_id=by_id):
            visit(child)

    visit(roots[0])
    return ordered


def ordered_items(items: Iterable[BacklogItem]) -> list[BacklogItem]:
    """Order every sibling level dependency-first without separating subtrees."""
    materialized = validate_backlog_items(items)
    by_id = {entry.id: entry for entry in materialized}
    if not by_id:
        return []
    _validate_dependency_graph(by_id)
    for entry in by_id.values():
        for dependency in entry.depends_on:
            if _is_descendant(dependency, entry.id, by_id):
                raise ValueError("backlog dependency conflicts with hierarchy order")
    children = _children_by_parent(by_id)
    ordered: list[BacklogItem] = []

    def visit(entry: BacklogItem) -> None:
        ordered.append(entry)
        for child in _ordered_siblings(entry.id, children=children, by_id=by_id):
            visit(child)

    for root in _ordered_siblings(None, children=children, by_id=by_id):
        visit(root)
    return ordered


def _marker_payload(entry: BacklogItem) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "id": entry.id,
        "title": entry.title,
        "status": entry.status.value,
        "priority": entry.priority.value,
        "parent_id": entry.parent_id,
        "depends_on": list(entry.depends_on),
        "notes": entry.notes,
        "updated_at": entry.updated_at,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _document_marker(document: BacklogDocument) -> str:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "project_key": document.project_key,
        "mode": document.mode,
    }
    return json.dumps(payload, separators=(",", ":"))


def render_backlog(
    document: BacklogDocument, *, preserve_item_order: bool = False
) -> str:
    """Render a readable, marker-backed canonical local document or cache."""
    header = ["# Backlog", f"<!-- engineering-method:backlog-document {_document_marker(document)} -->"]
    if document.mode == "github-cache":
        header = [
            GITHUB_CACHE_NOTICE,
            "# Backlog",
            f"<!-- engineering-method:backlog-document {_document_marker(document)} -->",
        ]
        header.extend(
            [
                "",
                "GitHub Issues are canonical. Refresh this cache; do not make local canonical mutations.",
            ]
        )
    else:
        header.extend(
            [
                "",
                "This is the canonical local task register until GitHub Issues become writable and canonical.",
                "Keep stable IDs unchanged. Order groups unblocker-first, then priority and dependency order.",
            ]
        )
    header.extend(
        [
            "",
            "## Status legend",
            "",
            "- `⭕` Open",
            "- `🔄` In progress",
            "- `✅` Complete",
            "- `❌` Blocked",
            "",
            "## Tasks",
            "",
        ]
    )
    lines = header
    entries = document.items if preserve_item_order else tuple(ordered_items(document.items))
    for entry in entries:
        _, components = parse_task_id(entry.id)
        indent = "  " * (len(components) - 1)
        lines.append(f"{indent}<!-- engineering-method:backlog {_marker_payload(entry)} -->")
        lines.append(
            f"{indent}- {STATUS_EMOJI[entry.status]} `{entry.id}` **{entry.priority.value}** {entry.title}"
        )
        if entry.depends_on:
            dependencies = ", ".join(f"`{identifier}`" for identifier in entry.depends_on)
            lines.append(f"{indent}  - Depends on: {dependencies}")
        if entry.notes:
            lines.append(f"{indent}  - Notes: {entry.notes}")
    return "\n".join(lines).rstrip() + "\n"


def _parse_marker_item(payload: object, display: re.Match[str]) -> BacklogItem:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("backlog marker must use schema_version 1")
    required = {"id", "title", "status", "priority", "parent_id", "depends_on", "notes", "updated_at"}
    if set(payload) != required | {"schema_version"} or not isinstance(
        payload["depends_on"], list
    ):
        raise ValueError("backlog marker is incomplete")
    try:
        entry = BacklogItem(
            id=payload["id"],
            title=payload["title"],
            status=TaskStatus(payload["status"]),
            priority=Priority(payload["priority"]),
            parent_id=payload["parent_id"],
            depends_on=tuple(payload["depends_on"]),
            notes=payload["notes"],
            updated_at=payload["updated_at"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("backlog marker contains invalid task data") from error
    if (
        display.group("id") != entry.id
        or display.group("title") != entry.title
        or display.group("priority") != entry.priority.value
        or EMOJI_STATUS[display.group("emoji")] is not entry.status
    ):
        raise ValueError("backlog marker and visible task disagree")
    return entry


def _load_marked_items(lines: list[str]) -> list[BacklogItem]:
    items: list[BacklogItem] = []
    consumed_detail_indices: set[int] = set()
    marker_indices = {index for index, line in enumerate(lines) if MARKER_PATTERN.fullmatch(line)}
    visible_indices = {index for index, line in enumerate(lines) if DISPLAY_PATTERN.fullmatch(line)}
    marked_document = bool(marker_indices) or any(
        DOCUMENT_MARKER_PATTERN.fullmatch(line) for line in lines
    )
    if marked_document:
        for index in visible_indices:
            if index == 0 or index - 1 not in marker_indices:
                raise ValueError("visible task has no immediately preceding marker")
    for index, line in enumerate(lines):
        marker = MARKER_PATTERN.fullmatch(line)
        if marker is None:
            continue
        if index + 1 >= len(lines):
            raise ValueError("backlog marker must precede a visible task")
        display = DISPLAY_PATTERN.fullmatch(lines[index + 1])
        if display is None:
            raise ValueError("backlog marker must immediately precede a visible task")
        try:
            payload = json.loads(marker.group("payload"))
        except json.JSONDecodeError as error:
            raise ValueError("backlog marker contains invalid JSON") from error
        entry = _parse_marker_item(payload, display)
        _, components = parse_task_id(entry.id)
        expected_indent = "  " * (len(components) - 1)
        marker_indent = line[: len(line) - len(line.lstrip())]
        if marker_indent != expected_indent or display.group("indent") != expected_indent:
            raise ValueError("backlog marker and visible indentation disagree")
        detail_index = index + 2
        if entry.depends_on:
            expected = f"{expected_indent}  - Depends on: " + ", ".join(
                f"`{identifier}`" for identifier in entry.depends_on
            )
            if detail_index >= len(lines) or lines[detail_index] != expected:
                raise ValueError("backlog marker and visible dependencies disagree")
            consumed_detail_indices.add(detail_index)
            detail_index += 1
        if entry.notes:
            expected = f"{expected_indent}  - Notes: {entry.notes}"
            if detail_index >= len(lines) or lines[detail_index] != expected:
                raise ValueError("backlog marker and visible notes disagree")
            consumed_detail_indices.add(detail_index)
            detail_index += 1
        if detail_index < len(lines) and lines[detail_index].startswith(
            f"{expected_indent}  - Depends on:"
        ):
            raise ValueError("backlog marker and visible dependencies disagree")
        if detail_index < len(lines) and lines[detail_index].startswith(
            f"{expected_indent}  - Notes:"
        ):
            raise ValueError("backlog marker and visible notes disagree")
        items.append(entry)
    if marked_document:
        visible_details = {
            index
            for index, line in enumerate(lines)
            if re.fullmatch(r"\s*-\s+(?:Depends on|Notes):.*", line)
        }
        if visible_details != consumed_detail_indices:
            raise ValueError("backlog marker and visible details disagree")
    return items


def _load_legacy_items(lines: list[str]) -> list[BacklogItem]:
    items: list[BacklogItem] = []
    ancestry: list[tuple[int, BacklogItem]] = []
    for line in lines:
        display = DISPLAY_PATTERN.fullmatch(line)
        if display is None:
            continue
        indent = len(display.group("indent"))
        tail = display.group("title")
        title, separator, dependency_text = tail.partition(". Depends on ")
        dependencies = tuple(re.findall(r"`([^`]+)`", dependency_text)) if separator else ()
        while ancestry and ancestry[-1][0] >= indent:
            ancestry.pop()
        parent = ancestry[-1][1] if ancestry else None
        priority_value = display.group("priority")
        if priority_value is None and parent is None:
            raise ValueError("a top-level legacy backlog item requires a priority")
        entry = BacklogItem(
            id=display.group("id"),
            title=title,
            status=EMOJI_STATUS[display.group("emoji")],
            priority=Priority(priority_value) if priority_value is not None else parent.priority,
            parent_id=parent.id if parent is not None else None,
            depends_on=dependencies,
            notes="",
            updated_at="1970-01-01T00:00:00Z",
        )
        items.append(entry)
        ancestry.append((indent, entry))
    return items


def _load_document_metadata(lines: list[str]) -> tuple[str | None, str | None]:
    for line in lines:
        marker = DOCUMENT_MARKER_PATTERN.fullmatch(line)
        if marker is None:
            continue
        try:
            payload = json.loads(marker.group("payload"))
        except json.JSONDecodeError as error:
            raise ValueError("backlog document marker contains invalid JSON") from error
        if (
            not isinstance(payload, dict)
            or set(payload) != {"schema_version", "project_key", "mode"}
            or payload.get("schema_version") != SCHEMA_VERSION
            or not isinstance(payload.get("project_key"), str)
            or payload.get("mode") not in {"local", "github-cache"}
        ):
            raise ValueError("backlog document marker is invalid")
        return payload["project_key"], payload["mode"]
    return None, None


def load_backlog(path: Path) -> BacklogDocument:
    """Load a marker-backed document or migrate compatible legacy task lines in memory."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"cannot read backlog: {path}") from error
    if any(
        "<!-- engineering-method:backlog " in line and MARKER_PATTERN.fullmatch(line) is None
        for line in lines
    ):
        raise ValueError("backlog contains a malformed task marker")
    document_marker_lines = [
        line for line in lines if "engineering-method:backlog-document" in line
    ]
    if any(DOCUMENT_MARKER_PATTERN.fullmatch(line) is None for line in document_marker_lines):
        raise ValueError("backlog contains a malformed document marker")
    if len(document_marker_lines) > 1:
        raise ValueError("backlog contains duplicate document markers")
    project_key, metadata_mode = _load_document_metadata(lines)
    has_markers = any(MARKER_PATTERN.fullmatch(line) for line in lines) or any(
        DOCUMENT_MARKER_PATTERN.fullmatch(line) for line in lines
    )
    items = _load_marked_items(lines)
    if not has_markers:
        items = _load_legacy_items(lines)
    if project_key is None:
        if not items:
            raise ValueError("backlog has no task IDs from which to derive a project key")
        project_key, _ = parse_task_id(items[0].id)
    mode = metadata_mode or ("github-cache" if GITHUB_CACHE_NOTICE in lines else "local")
    return BacklogDocument(project_key=project_key, mode=mode, items=tuple(items))


def archive_completed_groups(
    document: BacklogDocument,
    *,
    active_line_limit: int = 500,
    target_line_limit: int = 350,
) -> tuple[BacklogDocument, tuple[BacklogItem, ...]]:
    """Move oldest fully-complete top-level groups out of an oversized local backlog."""
    if document.mode == "github-cache":
        raise ValueError("cannot archive a github-cache backlog")
    if not 0 < target_line_limit <= active_line_limit:
        raise ValueError("archive line limits must be positive and target no greater than active")
    if len(render_backlog(document).splitlines()) <= active_line_limit:
        return document, ()

    by_id = {entry.id: entry for entry in document.items}
    groups = {
        root_id: _render_order_for_group(root_id, by_id)
        for root_id in {_root_id(entry, by_id) for entry in document.items}
    }
    complete_group_ids = {
        root_id
        for root_id, entries in groups.items()
        if all(entry.status is TaskStatus.COMPLETE for entry in entries)
    }
    complete_adjacency = {root_id: set() for root_id in complete_group_ids}
    protected_group_ids: set[str] = set()
    for entry in document.items:
        source_group = _root_id(entry, by_id)
        for dependency in entry.depends_on:
            dependency_group = _root_id(by_id[dependency], by_id)
            if source_group == dependency_group:
                continue
            if source_group in complete_group_ids and dependency_group in complete_group_ids:
                complete_adjacency[source_group].add(dependency_group)
                complete_adjacency[dependency_group].add(source_group)
            else:
                if source_group in complete_group_ids:
                    protected_group_ids.add(source_group)
                if dependency_group in complete_group_ids:
                    protected_group_ids.add(dependency_group)

    components: list[set[str]] = []
    unseen = set(complete_group_ids)
    while unseen:
        start = min(unseen, key=_task_sort_key)
        component: set[str] = set()
        pending = [start]
        while pending:
            group_id = pending.pop()
            if group_id in component:
                continue
            component.add(group_id)
            pending.extend(complete_adjacency[group_id] - component)
        unseen.difference_update(component)
        components.append(component)

    eligible = sorted(
        (
            (
                max(
                    entry.updated_at
                    for root_id in component
                    for entry in groups[root_id]
                ),
                component,
            )
            for component in components
            if component.isdisjoint(protected_group_ids)
        ),
        key=lambda pair: (
            pair[0],
            min((_task_sort_key(root_id) for root_id in pair[1])),
        ),
    )
    remaining_ids = set(by_id)
    archived: list[BacklogItem] = []
    for _, component in eligible:
        if len(render_backlog(BacklogDocument(
            project_key=document.project_key,
            mode=document.mode,
            items=tuple(entry for entry in document.items if entry.id in remaining_ids),
        )).splitlines()) <= target_line_limit:
            break
        ordered_roots = sorted(
            component,
            key=lambda root_id: (
                max(entry.updated_at for entry in groups[root_id]),
                _task_sort_key(root_id),
            ),
        )
        for root_id in ordered_roots:
            archived.extend(groups[root_id])
            remaining_ids.difference_update(entry.id for entry in groups[root_id])
    active = BacklogDocument(
        project_key=document.project_key,
        mode=document.mode,
        items=tuple(entry for entry in document.items if entry.id in remaining_ids),
    )
    if len(render_backlog(active).splitlines()) > target_line_limit:
        raise ValueError("cannot reduce backlog to archive target without archiving active work")
    return active, tuple(archived)


def _archive_order(items: Iterable[BacklogItem]) -> tuple[BacklogItem, ...]:
    materialized = validate_backlog_items(items)
    by_id = {entry.id: entry for entry in materialized}
    groups = {
        root_id: _render_order_for_group(root_id, by_id)
        for root_id in {_root_id(entry, by_id) for entry in materialized}
    }
    group_order = sorted(
        groups,
        key=lambda identifier: (
            max(entry.updated_at for entry in groups[identifier]),
            _task_sort_key(identifier),
        ),
    )
    return tuple(entry for root_id in group_order for entry in groups[root_id])


def render_backlog_archive(document: BacklogDocument) -> str:
    """Render complete historical groups in completion order, oldest first."""
    ordered = _archive_order(document.items)
    rendered = render_backlog(
        BacklogDocument(document.project_key, "local", ordered), preserve_item_order=True
    )
    return rendered.replace("# Backlog\n", "# Backlog Archive\n", 1).replace(
        "This is the canonical local task register until GitHub Issues become writable and canonical.\n"
        "Keep stable IDs unchanged. Order groups unblocker-first, then priority and dependency order.\n",
        "Completed local groups retained for history and later GitHub migration.\n",
        1,
    )


def load_backlog_history(path: Path) -> BacklogDocument:
    """Load active and archived local items for lossless later migration."""
    active = load_backlog(path)
    archive_path = path.with_name("BACKLOG-ARCHIVE.md")
    if not archive_path.exists():
        return active
    archived = load_backlog(archive_path)
    if archived.project_key != active.project_key:
        raise ValueError("backlog archive project key does not match active backlog")
    return BacklogDocument(active.project_key, active.mode, active.items + archived.items)


def write_backlog(
    path: Path,
    document: BacklogDocument,
    *,
    active_line_limit: int = 500,
    target_line_limit: int = 350,
) -> tuple[BacklogDocument, tuple[BacklogItem, ...]]:
    """Persist a normal backlog write and apply the local archive threshold policy."""
    active, newly_archived = archive_completed_groups(
        document,
        active_line_limit=active_line_limit,
        target_line_limit=target_line_limit,
    )
    if newly_archived:
        archive_path = path.with_name("BACKLOG-ARCHIVE.md")
        existing: tuple[BacklogItem, ...] = ()
        if archive_path.exists():
            archived_document = load_backlog(archive_path)
            if archived_document.project_key != document.project_key:
                raise ValueError("backlog archive project key does not match active backlog")
            existing = archived_document.items
        combined = BacklogDocument(
            document.project_key,
            "local",
            existing + newly_archived,
        )
        atomic_write_bundle(
            {
                archive_path: render_backlog_archive(combined).encode("utf-8"),
                path: render_backlog(active).encode("utf-8"),
            }
        )
    else:
        atomic_write_text(path, render_backlog(active))
    return active, newly_archived
