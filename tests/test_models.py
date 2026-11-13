"""Behavioral tests for stable project-state models and file safety."""

from __future__ import annotations

import json
import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engineering_method
from engineering_method import models
from engineering_method.files import (
    append_jsonl,
    atomic_write_json,
    require_repo_relative,
    require_safe_component,
)
from engineering_method.models import (
    BacklogItem,
    Priority,
    TaskStatus,
    derive_project_key,
    next_child_id,
    parse_task_id,
    utc_timestamp,
    validate_backlog_items,
)


def item(
    identifier: str,
    *,
    parent_id: str | None = None,
    depends_on: tuple[str, ...] = (),
) -> BacklogItem:
    """Build a hand-specified valid item for collection validation tests."""
    return BacklogItem(
        id=identifier,
        title="A stable backlog item",
        status=TaskStatus.OPEN,
        priority=Priority.P1,
        parent_id=parent_id,
        depends_on=depends_on,
        notes="",
        updated_at="2026-09-04T10:20:30Z",
    )


class ProjectKeyTests(unittest.TestCase):
    def test_derives_initials_from_hyphenated_repository_name(self) -> None:
        self.assertEqual(derive_project_key("engineering-method"), "EM")

    def test_preserves_an_explicit_project_key_override(self) -> None:
        self.assertEqual(derive_project_key("engineering-method", override="STATE"), "STATE")

    def test_rejects_repository_names_without_alphanumeric_words(self) -> None:
        with self.assertRaises(ValueError):
            derive_project_key("---")


class TaskIdentifierTests(unittest.TestCase):
    def test_parses_nested_uppercase_task_id(self) -> None:
        self.assertEqual(parse_task_id("EM-002.7.12"), ("EM", (2, 7, 12)))

    def test_preserves_the_existing_top_level_em_000_identity(self) -> None:
        self.assertEqual(parse_task_id("EM-000"), ("EM", (0,)))

    def test_rejects_lowercase_zero_and_malformed_task_components(self) -> None:
        for value in ("em-002", "EM-0", "EM-000.0", "EM-002.0", "EM-002.", "EM002"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_task_id(value)

    def test_next_child_id_uses_only_immediate_children(self) -> None:
        existing = ("EM-002", "EM-002.1", "EM-002.3", "EM-002.1.1")
        self.assertEqual(next_child_id("EM-002", existing), "EM-002.4")

    def test_next_child_id_requires_an_existing_parent(self) -> None:
        with self.assertRaises(ValueError):
            next_child_id("EM-002", ("EM-002.1",))


class BacklogModelTests(unittest.TestCase):
    def test_rejects_a_child_whose_parent_is_absent_from_collection(self) -> None:
        with self.assertRaisesRegex(ValueError, "parent"):
            validate_backlog_items((item("EM-002.1", parent_id="EM-002"),))

    def test_rejects_duplicate_ids(self) -> None:
        duplicate = item("EM-002")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            validate_backlog_items((duplicate, duplicate))

    def test_rejects_parent_that_does_not_match_nested_id(self) -> None:
        with self.assertRaises(ValueError):
            item("EM-002.1", parent_id="EM-003")

    def test_timestamp_is_utc_rfc_3339(self) -> None:
        self.assertRegex(utc_timestamp(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_rejects_newlines_in_canonical_text_fields_and_unsafe_status_values(self) -> None:
        for field, value in (("title", "line one\nline two"), ("notes", "safe\runsafe")):
            values = {
                "id": "EM-002",
                "title": "Safe title",
                "status": TaskStatus.OPEN,
                "priority": Priority.P1,
                "parent_id": None,
                "depends_on": (),
                "notes": "Safe notes",
                "updated_at": "2026-09-04T10:20:30Z",
            }
            values[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "newline"):
                BacklogItem(**values)
        with self.assertRaisesRegex(ValueError, "status"):
            BacklogItem(
                "EM-002",
                "Safe title",
                "open\nclosed",  # type: ignore[arg-type]
                Priority.P1,
                None,
                (),
                "",
                "2026-09-04T10:20:30Z",
            )


class FilesystemSafetyTests(unittest.TestCase):
    def test_accepts_a_clean_nested_repository_relative_path(self) -> None:
        self.assertEqual(require_repo_relative("state/runs/item.json"), "state/runs/item.json")

    def test_rejects_absolute_and_traversing_repository_paths(self) -> None:
        for value in (
            "/tmp/state.json",
            "../state.json",
            "runs/../../state.json",
            "C:\\state.json",
            "C:/state.json",
            "C:state.json",
            ".",
            "./state.json",
            "state/./item.json",
            "state//item.json",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require_repo_relative(value)

    def test_rejects_unsafe_single_path_components_on_posix_and_windows(self) -> None:
        for value in ("", ".", "..", "EM/002", "EM\\002", "C:EM-002", "EM-002\nnext"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                require_safe_component(value, field="work ID")

    def test_atomic_write_replaces_json_at_the_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "state.json"
            destination.write_text('{"old": true}\n', encoding="utf-8")

            atomic_write_json(destination, {"version": 1, "title": "new"})

            self.assertEqual(
                json.loads(destination.read_text(encoding="utf-8")),
                {"title": "new", "version": 1},
            )

    def test_atomic_write_failure_preserves_existing_destination_and_cleans_tempfile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "state.json"
            destination.write_text('{"old": true}\n', encoding="utf-8")

            with patch("engineering_method.files.os.replace", side_effect=OSError("disk failure")):
                with self.assertRaisesRegex(OSError, "disk failure"):
                    atomic_write_json(destination, {"new": True})

            self.assertEqual(destination.read_text(encoding="utf-8"), '{"old": true}\n')
            self.assertEqual(list(Path(temporary).glob(".state.json.*.tmp")), [])

    def test_append_jsonl_writes_one_valid_record_per_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "events" / "events.jsonl"

            append_jsonl(destination, {"event": "started", "sequence": 1})
            append_jsonl(destination, {"event": "completed", "sequence": 2})

            self.assertEqual(
                [json.loads(line) for line in destination.read_text(encoding="utf-8").splitlines()],
                [
                    {"event": "started", "sequence": 1},
                    {"event": "completed", "sequence": 2},
                ],
            )


class PythonVersionTests(unittest.TestCase):
    def test_runtime_guard_rejects_python_3_10_and_accepts_python_3_11(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Python 3.11"):
            models.require_supported_python((3, 10))
        models.require_supported_python((3, 11))

    def test_package_guard_runs_before_importing_python_3_11_only_modules(self) -> None:
        try:
            with patch.object(sys, "version_info", (3, 10)):
                with self.assertRaisesRegex(RuntimeError, "Python 3.11"):
                    importlib.reload(engineering_method)
        finally:
            importlib.reload(engineering_method)


if __name__ == "__main__":
    unittest.main()
