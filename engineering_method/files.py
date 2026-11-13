"""Filesystem primitives that keep project-state writes safe and portable."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from typing import Any, Mapping


def require_repo_relative(path: str) -> str:
    """Return a normalized repository-relative POSIX path or reject unsafe input."""
    if (
        not isinstance(path, str)
        or not path
        or "\\" in path
        or "\n" in path
        or "\r" in path
        or re.match(r"^[A-Za-z]:", path)
    ):
        raise ValueError("path must be a non-empty repository-relative POSIX path")
    raw_parts = path.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise ValueError("path must remain within the repository without dot segments")
    candidate = PurePosixPath(path)
    if candidate.is_absolute():
        raise ValueError("path must remain within the repository")
    normalized = str(candidate)
    if normalized in {"", "."}:
        raise ValueError("path must name a repository artifact")
    return normalized


def require_safe_component(value: str, *, field: str = "path component") -> str:
    """Validate an identifier that will become exactly one filesystem component."""
    if (
        not isinstance(value, str)
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or ":" in value
        or "\n" in value
        or "\r" in value
    ):
        raise ValueError(f"invalid {field}")
    return value


def require_contained_path(root: Path, path: Path, *, field: str) -> Path:
    """Reject lexical traversal and every existing symlink that escapes a repository root."""
    root_lexical = Path(os.path.abspath(root))
    candidate = path if path.is_absolute() else root_lexical / path
    candidate_lexical = Path(os.path.abspath(candidate))
    try:
        relative = candidate_lexical.relative_to(root_lexical)
    except ValueError as error:
        raise ValueError(f"{field} escapes the repository") from error
    root_resolved = root_lexical.resolve(strict=False)
    current = root_lexical
    try:
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                current.resolve(strict=False).relative_to(root_resolved)
        candidate_lexical.resolve(strict=False).relative_to(root_resolved)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError(f"{field} escapes the repository through a symlink") from error
    return candidate_lexical


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomically replace JSON using a flushed sibling temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _json_bytes(payload)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_text(path: Path, content: str) -> None:
    """Atomically replace a UTF-8 text artifact using the same sibling-file protocol."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _staged_file(path: Path, data: bytes, *, role: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.{role}.", suffix=".tmp", dir=path.parent
    )
    temporary_path = Path(temporary_name)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    return temporary_path


def atomic_write_bundle(replacements: Mapping[Path, bytes]) -> None:
    """Replace a small related file set with rollback if a later replacement fails."""
    if not replacements:
        return
    staged: dict[Path, Path] = {}
    backups: dict[Path, Path | None] = {}
    replaced: list[Path] = []
    try:
        for path, data in replacements.items():
            staged[path] = _staged_file(path, data, role="new")
            backups[path] = _staged_file(path, path.read_bytes(), role="old") if path.exists() else None
        try:
            for path in replacements:
                os.replace(staged[path], path)
                replaced.append(path)
        except OSError:
            for path in reversed(replaced):
                backup = backups[path]
                if backup is None:
                    path.unlink(missing_ok=True)
                else:
                    os.replace(backup, path)
                    backups[path] = None
            raise
    finally:
        for temporary_path in (*staged.values(), *(path for path in backups.values() if path)):
            temporary_path.unlink(missing_ok=True)


def append_jsonl(path: Path, record: Mapping[str, Any]) -> None:
    """Append exactly one fsynced JSON object and newline per call."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line)
        handle.flush()
        os.fsync(handle.fileno())
