"""Stable, validated data models shared by project-state services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import re
import sys
from typing import Iterable, Literal


PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*$")
TASK_ID_PATTERN = re.compile(
    r"^([A-Z][A-Z0-9]*)-((?:000|0*[1-9][0-9]*)(?:\.0*[1-9][0-9]*)*)$"
)
RFC_3339_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def require_supported_python(version_info: tuple[int, ...] | object = sys.version_info) -> None:
    """Fail clearly before unsupported interpreters parse or run project-state data."""
    major, minor = version_info[:2]  # type: ignore[index]
    if (major, minor) < (3, 11):
        raise RuntimeError("engineering-method requires Python 3.11 or newer")


require_supported_python()


def _require_single_line(value: str, *, field: str, non_empty: bool = False) -> None:
    if not isinstance(value, str) or (non_empty and not value.strip()):
        suffix = "non-empty text" if non_empty else "text"
        raise ValueError(f"{field} must be {suffix}")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field} must not contain a newline")


class TaskStatus(StrEnum):
    """The finite lifecycle state of a canonical backlog item."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class Priority(StrEnum):
    """Urgency is deliberately independent of an item's stable identity."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


def utc_timestamp() -> str:
    """Return a seconds-precision UTC timestamp in canonical RFC-3339 form."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _validate_utc_timestamp(value: str) -> None:
    if not RFC_3339_UTC_PATTERN.fullmatch(value):
        raise ValueError("updated_at must be a UTC RFC-3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("updated_at must be a valid UTC RFC-3339 timestamp") from error
    if parsed.tzinfo != timezone.utc:
        raise ValueError("updated_at must be UTC")


def derive_project_key(repository_name: str, *, override: str | None = None) -> str:
    """Derive a stable uppercase key, unless an explicit validated key is supplied."""
    if override is not None:
        if not PROJECT_KEY_PATTERN.fullmatch(override):
            raise ValueError("project-key override must be uppercase alphanumeric")
        return override
    words = re.findall(r"[A-Za-z0-9]+", repository_name)
    if not words:
        raise ValueError("repository name must contain an alphanumeric word")
    if len(words) == 1:
        key = words[0][:2]
    else:
        key = "".join(word[0] for word in words)
    key = key.upper()
    if not PROJECT_KEY_PATTERN.fullmatch(key):
        raise ValueError("repository name cannot derive a valid project key")
    return key


def parse_task_id(value: str) -> tuple[str, tuple[int, ...]]:
    """Parse a stable uppercase task ID without accepting ambiguous zero components."""
    match = TASK_ID_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid task ID: {value!r}")
    return match.group(1), tuple(int(component) for component in match.group(2).split("."))


def next_child_id(parent_id: str, existing_ids: Iterable[str]) -> str:
    """Return the next monotonic direct child ID for an existing parent."""
    project_key, parent_components = parse_task_id(parent_id)
    known_ids = tuple(existing_ids)
    if parent_id not in known_ids:
        raise ValueError(f"parent ID does not exist: {parent_id}")
    direct_children: list[int] = []
    for identifier in known_ids:
        child_key, child_components = parse_task_id(identifier)
        if child_key == project_key and child_components[:-1] == parent_components and len(
            child_components
        ) == len(parent_components) + 1:
            direct_children.append(child_components[-1])
    return f"{parent_id}.{max(direct_children, default=0) + 1}"


@dataclass(frozen=True)
class BacklogItem:
    """One stable canonical task entry."""

    id: str
    title: str
    status: TaskStatus
    priority: Priority
    parent_id: str | None
    depends_on: tuple[str, ...]
    notes: str
    updated_at: str

    def __post_init__(self) -> None:
        _, components = parse_task_id(self.id)
        _require_single_line(self.title, field="backlog title", non_empty=True)
        if not isinstance(self.status, TaskStatus):
            raise ValueError("backlog status must be a TaskStatus")
        if not isinstance(self.priority, Priority):
            raise ValueError("backlog priority must be a Priority")
        if self.parent_id is None:
            if len(components) != 1:
                raise ValueError("nested backlog items require their immediate parent")
        else:
            parent_key, parent_components = parse_task_id(self.parent_id)
            item_key, _ = parse_task_id(self.id)
            if (
                parent_key != item_key
                or parent_components != components[:-1]
                or len(components) == 1
            ):
                raise ValueError("backlog parent must be the immediate parent of its child ID")
        if not isinstance(self.depends_on, tuple):
            raise ValueError("depends_on must be a tuple")
        for dependency in self.depends_on:
            parse_task_id(dependency)
        if self.id in self.depends_on:
            raise ValueError("backlog item cannot depend on itself")
        _require_single_line(self.notes, field="backlog notes")
        _validate_utc_timestamp(self.updated_at)


@dataclass(frozen=True)
class Feature:
    """A capability inventory entry, intentionally distinct from a task item."""

    id: str
    name: str
    summary: str
    status: Literal["available", "changed", "removed"]
    related_backlog_ids: tuple[str, ...]
    updated_at: str

    def __post_init__(self) -> None:
        if re.fullmatch(r"F-0*[1-9][0-9]*", self.id) is None:
            raise ValueError("feature ID must use the F-NNN form")
        _require_single_line(self.name, field="feature name", non_empty=True)
        _require_single_line(self.summary, field="feature summary", non_empty=True)
        if self.status not in {"available", "changed", "removed"}:
            raise ValueError("feature status is invalid")
        if not isinstance(self.related_backlog_ids, tuple):
            raise ValueError("related_backlog_ids must be a tuple")
        for backlog_id in self.related_backlog_ids:
            parse_task_id(backlog_id)
        _validate_utc_timestamp(self.updated_at)


def validate_backlog_items(items: Iterable[BacklogItem]) -> tuple[BacklogItem, ...]:
    """Validate collection-level uniqueness, hierarchy, and dependency references."""
    materialized = tuple(items)
    identifiers = [item.id for item in materialized]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("duplicate backlog item ID")
    known_ids = set(identifiers)
    for entry in materialized:
        if entry.parent_id is not None and entry.parent_id not in known_ids:
            raise ValueError(f"backlog parent does not exist: {entry.parent_id}")
        for dependency in entry.depends_on:
            if dependency not in known_ids:
                raise ValueError(f"backlog dependency does not exist: {dependency}")
    return materialized
