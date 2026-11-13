"""Behavioral tests for complete, compact-safe continuity and recovery."""

from __future__ import annotations

from dataclasses import replace
import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import engineering_method.continuity as continuity
from engineering_method.backlog import BacklogDocument, render_backlog
from engineering_method.models import BacklogItem, Priority, TaskStatus


def state(**changes: object) -> continuity.RunState:
    values: dict[str, object] = {
        "work_id": "EM-002",
        "backlog_id": "EM-002",
        "issue_id": 42,
        "feature_id": "F-001",
        "change_id": "state-continuity",
        "lifecycle": "implementation",
        "phase": "task-6",
        "current_slice": "slice-2",
        "spec_path": "docs/spec.md",
        "plan_path": "docs/plan.md",
        "tasks_path": "docs/tasks.md",
        "uml_paths": ("docs/uml/state.md",),
        "report_paths": ("reports/review.md",),
        "artifact_paths": ("artifacts/result.txt",),
        "worktree_path": ".",
        "base_commit": "base",
        "last_observed_head": "head",
        "completed_work": ("slice-1",),
        "active_work": ("slice-2",),
        "pending_work": ("run verification",),
        "active_agent_ids": ("agent-live", "agent-gone"),
        "completed_agent_ids": ("agent-done",),
        "open_findings": ("verify recovery",),
        "failing_checks": ("integration",),
        "verification_command": "python3 -m unittest",
        "verification_timestamp": "2026-09-04T10:20:30Z",
        "verification_output_digest": "a" * 64,
        "next_action": "complete EM-002",
    }
    values.update(changes)
    return continuity.RunState(**values)


def make_artifacts(root: Path, run_state: continuity.RunState) -> None:
    paths = tuple(
        path
        for path in (
            run_state.spec_path,
            run_state.plan_path,
            run_state.tasks_path,
            *run_state.uml_paths,
            *run_state.report_paths,
            *run_state.artifact_paths,
        )
        if path is not None
    )
    for relative in paths:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("evidence\n", encoding="utf-8")


class ContinuityStateTests(unittest.TestCase):
    def test_state_json_contains_every_design_field_and_exact_run_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = continuity.create_run(root, state(), "Resume here.", "Keep IDs stable.")
            self.assertEqual(
                {path.name for path in run.iterdir()},
                {"state.json", "resume.md", "decisions.md", "agent-reports", "events.jsonl"},
            )
            payload = json.loads((run / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(
                set(payload),
                {
                    "schema_version",
                    "coordination_mode",
                    "work_id",
                    "backlog_id",
                    "issue_id",
                    "feature_id",
                    "change_id",
                    "lifecycle",
                    "phase",
                    "current_slice",
                    "spec_path",
                    "plan_path",
                    "tasks_path",
                    "uml_paths",
                    "report_paths",
                    "artifact_paths",
                    "worktree_path",
                    "base_commit",
                    "last_observed_head",
                    "completed_work",
                    "active_work",
                    "pending_work",
                    "active_agent_ids",
                    "completed_agent_ids",
                    "open_findings",
                    "failing_checks",
                    "verification_command",
                    "verification_timestamp",
                    "verification_output_digest",
                    "next_action",
                },
            )

    def test_initialization_is_non_destructive_without_explicit_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = continuity.create_run(root, state(), "Original resume.")
            continuity.append_event(root, "EM-002", {"kind": "workflow_started"})
            with self.assertRaisesRegex(ValueError, "already exists"):
                continuity.create_run(root, replace(state(), phase="changed"), "Replacement.")
            self.assertEqual((run / "resume.md").read_text(encoding="utf-8"), "Original resume.")

            continuity.create_run(
                root, replace(state(), phase="changed"), "Replacement.", replace_existing=True
            )
            self.assertEqual((run / "resume.md").read_text(encoding="utf-8"), "Replacement.")
            self.assertEqual((run / "events.jsonl").read_text(encoding="utf-8"), "")

    def test_checkpoint_rolls_back_state_and_resume_together_on_second_replace_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = continuity.create_run(root, state(), "Original resume.")
            original_state = (run / "state.json").read_bytes()
            original_resume = (run / "resume.md").read_bytes()
            real_replace = os.replace
            calls = 0

            def fail_second(source, destination):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("second replacement failed")
                return real_replace(source, destination)

            with patch("engineering_method.files.os.replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "second replacement"):
                    continuity.checkpoint(
                        root,
                        "EM-002",
                        replace(state(), phase="new-phase"),
                        "New resume.",
                    )
            self.assertEqual((run / "state.json").read_bytes(), original_state)
            self.assertEqual((run / "resume.md").read_bytes(), original_resume)

    def test_checkpoint_preserves_resume_when_no_replacement_text_is_supplied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = continuity.create_run(root, state(), "Preserve me.")
            continuity.checkpoint(root, "EM-002", replace(state(), phase="new"))
            self.assertEqual((run / "resume.md").read_text(encoding="utf-8"), "Preserve me.")

    def test_upgrades_schema_zero_and_rejects_future_schema(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / ".engineering-method" / "runs" / "EM-002"
            run.mkdir(parents=True)
            (run / "resume.md").write_text("Resume.\n", encoding="utf-8")
            (run / "decisions.md").write_text("", encoding="utf-8")
            (run / "events.jsonl").write_text("", encoding="utf-8")
            (run / "agent-reports").mkdir()
            (run / "state.json").write_text(
                json.dumps(
                    {
                        "schema_version": 0,
                        "work_id": "EM-002",
                        "lifecycle": "implementation",
                        "phase": "old",
                        "next_action": "continue",
                        "completed_slices": ["slice-1"],
                        "active_agent_ids": [],
                        "artifact_paths": [],
                    }
                ),
                encoding="utf-8",
            )
            loaded = continuity.load_run_state(root, "EM-002", persist_upgrade=True)
            self.assertEqual(loaded.schema_version, 1)
            self.assertEqual(loaded.completed_work, ("slice-1",))
            self.assertEqual(json.loads((run / "state.json").read_text())["schema_version"], 1)

            payload = json.loads((run / "state.json").read_text())
            payload["schema_version"] = 2
            (run / "state.json").write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "future"):
                continuity.load_run_state(root, "EM-002")

    def test_replacement_is_fully_staged_and_fresh_failure_leaves_no_partial_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = continuity.create_run(root, state(), "Original resume.")
            report = continuity.write_agent_report(
                root, "EM-002", "agent-a", "Original report."
            )
            original_state = (run / "state.json").read_bytes()
            with patch(
                "engineering_method.continuity.atomic_write_bundle",
                side_effect=OSError("staging failed"),
            ):
                with self.assertRaisesRegex(OSError, "staging failed"):
                    continuity.create_run(
                        root,
                        replace(state(), phase="replacement"),
                        "Replacement resume.",
                        replace_existing=True,
                    )
            self.assertEqual((run / "state.json").read_bytes(), original_state)
            self.assertEqual(report.read_text(encoding="utf-8"), "Original report.")

            fresh = replace(state(), work_id="EM-003", backlog_id="EM-003")
            with patch(
                "engineering_method.continuity.atomic_write_bundle",
                side_effect=OSError("fresh staging failed"),
            ):
                with self.assertRaisesRegex(OSError, "fresh staging failed"):
                    continuity.create_run(root, fresh, "Fresh resume.")
            fresh_run = root / ".engineering-method" / "runs" / "EM-003"
            self.assertFalse(fresh_run.exists())
            continuity.create_run(root, fresh, "Fresh resume.")
            self.assertTrue(fresh_run.is_dir())


class ContinuitySafetyTests(unittest.TestCase):
    def test_rejects_unsafe_work_ids_and_sensitive_content_in_every_artifact(self) -> None:
        for work_id in (".", "..", "EM/002", "EM\\002", "C:EM-002"):
            with self.subTest(work_id=work_id), self.assertRaises(ValueError):
                continuity.RunState(
                    work_id=work_id,
                    lifecycle="implementation",
                    phase="work",
                    next_action="continue",
                )
        with self.assertRaisesRegex(ValueError, "sensitive"):
            continuity.RunState(
                work_id="EM-002",
                lifecycle="implementation",
                phase="work",
                next_action="Authorization: Bearer abc123",
            )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "sensitive"):
                continuity.create_run(root, state(), "password=hunter2")
            with self.assertRaisesRegex(ValueError, "sensitive"):
                continuity.create_run(root, state(), "Resume.", "api_token: abc")
            run = continuity.create_run(root, state(), "Resume.")
            before = (run / "events.jsonl").read_text(encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sensitive"):
                continuity.append_event(
                    root,
                    "EM-002",
                    {"kind": "phase_changed", "context": {"auth_token": "abc"}},
                )
            with self.assertRaisesRegex(ValueError, "sensitive"):
                continuity.write_agent_report(root, "EM-002", "agent-a", "Cookie: session=abc")
            self.assertEqual((run / "events.jsonl").read_text(encoding="utf-8"), before)

    def test_events_require_a_valid_run_and_reject_producer_owned_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "run does not exist"):
                continuity.append_event(root, "EM-002", {"kind": "workflow_started"})
            continuity.create_run(root, state(), "Resume.")
            decisions = root / ".engineering-method" / "runs" / "EM-002" / "decisions.md"
            decisions.unlink()
            with self.assertRaisesRegex(ValueError, "run.*incomplete"):
                continuity.append_event(root, "EM-002", {"kind": "workflow_started"})
            decisions.write_text("", encoding="utf-8")
            for field in ("schema_version", "timestamp", "work_id", "sequence"):
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "producer"):
                    continuity.append_event(
                        root, "EM-002", {"kind": "workflow_started", field: "override"}
                    )
            emitted = continuity.append_event(
                root,
                "EM-002",
                {"kind": "verification_passed", "artifact": "reports/review.md"},
            )
            self.assertEqual(emitted["work_id"], "EM-002")
            self.assertEqual(emitted["sequence"], 1)

    def test_accepts_exactly_the_nine_provider_neutral_event_kinds(self) -> None:
        expected = (
            "workflow_started",
            "phase_changed",
            "slice_started",
            "decision_recorded",
            "agent_dispatched",
            "agent_completed",
            "verification_failed",
            "verification_passed",
            "workflow_completed",
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            continuity.create_run(root, state(), "Resume.")
            for kind in expected:
                continuity.append_event(root, "EM-002", {"kind": kind})
            with self.assertRaisesRegex(ValueError, "kind"):
                continuity.append_event(root, "EM-002", {"kind": "invented"})

    def test_state_and_report_writes_reject_symlink_escapes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir()
            outside.mkdir()
            (root / ".engineering-method").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "escapes"):
                continuity.create_run(root, state(), "Resume.")
            self.assertEqual(list(outside.iterdir()), [])

            (root / ".engineering-method").unlink()
            run = continuity.create_run(root, state(), "Resume.")
            reports = run / "agent-reports"
            reports.rmdir()
            reports.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "escapes"):
                continuity.write_agent_report(root, "EM-002", "agent-a", "Report.")
            self.assertEqual(list(outside.iterdir()), [])


class RecoveryTests(unittest.TestCase):
    def test_coordinator_only_bootstrap_checkpoint_and_recovery_without_observer(self):
        from engineering_method.cli import main
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, head = self._git_repository(root)
            (root / "BACKLOG.md").write_text(render_backlog(BacklogDocument("EM", "local", ())))
            (root / "resume-input.md").write_text("No delegation capability; coordinator owns sequential work.")
            initial = continuity.RunState("EM-002", "speckit", "specify", "Write spec",
                                          base_commit=base, last_observed_head=head,
                                          coordination_mode="coordinator-only")
            self.assertFalse((root / ".engineering-method/runs/EM-002").exists())
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(0, main(["continuity-state", "init", "EM-002", "--file", "-",
                    "--resume-file", "resume-input.md"], root=root,
                    stdin=io.StringIO(json.dumps(continuity._state_payload(initial)))))
                following = replace(initial, phase="plan", next_action="Write plan")
                self.assertEqual(0, main(["continuity-state", "checkpoint", "EM-002", "--file", "-"],
                    root=root, stdin=io.StringIO(json.dumps(continuity._state_payload(following)))))
                self.assertEqual(0, main(["continuity-state", "recover", "EM-002", "--coordinator-only"], root=root))
            saved = continuity.load_run_state(root, "EM-002")
            self.assertEqual("plan", saved.phase)
            self.assertEqual((), saved.active_agent_ids)
            self.assertEqual("Write plan", saved.next_action)

    def test_no_observer_rejects_ordinary_active_and_ambiguous_saved_runs(self):
        for scenario in ("ordinary", "active", "completed", "dispatch", "report", "partial"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                base, head = self._git_repository(root)
                initial = continuity.RunState("EM-002", "speckit", "plan", "Write plan",
                    base_commit=base, last_observed_head=head,
                    coordination_mode="observed" if scenario == "ordinary" else "coordinator-only")
                run = continuity.create_run(root, initial, "Resume sequentially")
                if scenario in ("active", "completed"):
                    data = json.loads((run / "state.json").read_text())
                    data[scenario + "_agent_ids"] = ["saved-agent"]
                    (run / "state.json").write_text(json.dumps(data))
                elif scenario == "dispatch":
                    event = {"schema_version": 1, "timestamp": "2026-09-05T00:00:00Z", "work_id": "EM-002",
                             "sequence": 1, "kind": "agent_dispatched", "agent_id": "saved-agent"}
                    (run / "events.jsonl").write_text(json.dumps(event) + "\n")
                elif scenario == "report":
                    (run / "agent-reports/unknown.md").write_text("Uncertain prior agent activity")
                elif scenario == "partial":
                    (run / "events.jsonl").unlink()
                before = {str(p): p.read_bytes() for p in run.rglob("*") if p.is_file()}
                with self.assertRaises(ValueError):
                    continuity.recover_run(root, "EM-002", git_probe=continuity.SubprocessGitProbe(),
                        canonical_probe=continuity.BacklogCanonicalProbe(), live_agent_ids=None)
                self.assertEqual(before, {str(p): p.read_bytes() for p in run.rglob("*") if p.is_file()})

    def test_coordinator_mode_cannot_be_retrofitted_or_dispatch_agents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normal = continuity.RunState("EM-002", "speckit", "plan", "Write plan")
            continuity.create_run(root, normal, "Saved ordinary run")
            isolated = replace(normal, coordination_mode="coordinator-only")
            with self.assertRaises(ValueError):
                continuity.checkpoint(root, "EM-002", isolated)
            with self.assertRaises(ValueError):
                continuity.create_run(root, isolated, "Reset", replace_existing=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            continuity.create_run(root, isolated, "New sequential run")
            with self.assertRaises(ValueError):
                continuity.append_event(root, "EM-002", {"kind": "agent_dispatched"})
            with self.assertRaises(ValueError):
                continuity.write_agent_report(root, "EM-002", "agent", "Done")

    def _git_repository(self, root: Path) -> tuple[str, str]:
        subprocess.run(("git", "init", "-q"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=root, check=True)
        subprocess.run(("git", "config", "user.name", "Test User"), cwd=root, check=True)
        (root / "tracked.txt").write_text("one\n", encoding="utf-8")
        subprocess.run(("git", "add", "tracked.txt"), cwd=root, check=True)
        subprocess.run(("git", "commit", "-q", "-m", "base"), cwd=root, check=True)
        base = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, check=True, text=True, capture_output=True
        ).stdout.strip()
        (root / "tracked.txt").write_text("two\n", encoding="utf-8")
        subprocess.run(("git", "commit", "-qam", "head"), cwd=root, check=True)
        head = subprocess.run(
            ("git", "rev-parse", "HEAD"), cwd=root, check=True, text=True, capture_output=True
        ).stdout.strip()
        return base, head

    def test_real_git_artifact_and_canonical_reconciliation_advances_stale_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base, head = self._git_repository(root)
            run_state = state(
                worktree_path=str(root),
                base_commit=base,
                last_observed_head=base,
            )
            make_artifacts(root, run_state)
            backlog_item = BacklogItem(
                "EM-002",
                "Continuity",
                TaskStatus.COMPLETE,
                Priority.P1,
                None,
                (),
                "",
                "2026-09-04T10:20:30Z",
            )
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "local", (backlog_item,))),
                encoding="utf-8",
            )
            continuity.create_run(root, run_state, "Keep this exact resume text.")

            recovered = continuity.recover_run(
                root,
                "EM-002",
                git_probe=continuity.SubprocessGitProbe(),
                canonical_probe=continuity.BacklogCanonicalProbe(),
                live_agent_ids=("agent-live",),
            )

            self.assertEqual(recovered.state.last_observed_head, head)
            self.assertEqual(recovered.state.active_work, ())
            self.assertIn("slice-2", recovered.completed_work)
            self.assertEqual(recovered.redispatchable_agent_ids, ())
            self.assertEqual(recovered.next_action, "run verification")
            self.assertNotIn("complete EM-002", recovered.next_action)
            self.assertEqual(
                (root / ".engineering-method" / "runs" / "EM-002" / "resume.md").read_text(
                    encoding="utf-8"
                ),
                "Keep this exact resume text.",
            )

    def test_recovery_marks_only_unavailable_active_agents_redispatchable(self) -> None:
        class GitProbe:
            def inspect(self, root: Path, saved: continuity.RunState):
                return continuity.GitSnapshot(str(root), True, saved.last_observed_head)

        class CanonicalProbe:
            def status(self, root: Path, saved: continuity.RunState):
                return TaskStatus.IN_PROGRESS

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_state = state(
                worktree_path=str(root),
                spec_path=None,
                plan_path=None,
                tasks_path=None,
                uml_paths=(),
                report_paths=(),
                artifact_paths=(),
            )
            continuity.create_run(root, run_state, "Resume.")
            recovered = continuity.recover_run(
                root,
                "EM-002",
                git_probe=GitProbe(),
                canonical_probe=CanonicalProbe(),
                live_agent_ids=("agent-live",),
            )
            self.assertEqual(recovered.redispatchable_agent_ids, ("agent-gone",))
            self.assertIn("agent-gone", recovered.next_action)

    def test_recovery_never_repeats_work_already_recorded_complete(self) -> None:
        class GitProbe:
            def inspect(self, root: Path, saved: continuity.RunState):
                return continuity.GitSnapshot(str(root), True, saved.last_observed_head)

        class CanonicalProbe:
            def status(self, root: Path, saved: continuity.RunState):
                return TaskStatus.IN_PROGRESS

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = state(
                worktree_path=str(root),
                current_slice=None,
                completed_work=("slice-1",),
                active_work=(),
                pending_work=("slice-2",),
                active_agent_ids=(),
                next_action="implement slice-1",
                spec_path=None,
                plan_path=None,
                tasks_path=None,
                uml_paths=(),
                report_paths=(),
                artifact_paths=(),
            )
            continuity.create_run(root, saved, "Resume.")
            recovered = continuity.recover_run(
                root,
                "EM-002",
                git_probe=GitProbe(),
                canonical_probe=CanonicalProbe(),
                live_agent_ids=(),
            )
            self.assertEqual(recovered.next_action, "slice-2")

    def test_git_probe_has_a_bounded_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch(
                "engineering_method.continuity.subprocess.run",
                side_effect=subprocess.TimeoutExpired(("git", "rev-parse"), 15),
            ) as run:
                with self.assertRaisesRegex(ValueError, "timed out"):
                    continuity.SubprocessGitProbe().inspect(root, state())
            self.assertEqual(run.call_args.kwargs["timeout"], 15)

    def test_recovery_rejects_missing_resume_artifact_worktree_and_base_commit(self) -> None:
        class GitProbe:
            def __init__(self, worktree: str, base_exists: bool = True):
                self.worktree = worktree
                self.base_exists = base_exists

            def inspect(self, root: Path, saved: continuity.RunState):
                return continuity.GitSnapshot(self.worktree, self.base_exists, "head")

        class CanonicalProbe:
            def status(self, root: Path, saved: continuity.RunState):
                return TaskStatus.OPEN

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_state = state(
                worktree_path=str(root),
                spec_path=None,
                plan_path=None,
                tasks_path=None,
                uml_paths=(),
                report_paths=(),
                artifact_paths=("missing.txt",),
            )
            run = continuity.create_run(root, run_state, "Resume.")
            with self.assertRaisesRegex(ValueError, "artifact"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(str(root)),
                    canonical_probe=CanonicalProbe(),
                    live_agent_ids=(),
                )
            (root / "missing.txt").write_text("now present\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "worktree"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(str(root / "other")),
                    canonical_probe=CanonicalProbe(),
                    live_agent_ids=(),
                )
            with self.assertRaisesRegex(ValueError, "base commit"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(str(root), base_exists=False),
                    canonical_probe=CanonicalProbe(),
                    live_agent_ids=(),
                )
            (run / "resume.md").unlink()
            with self.assertRaisesRegex(ValueError, "resume"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(str(root)),
                    canonical_probe=CanonicalProbe(),
                    live_agent_ids=(),
                )

    def test_recovery_rejects_a_recorded_head_that_no_longer_exists(self) -> None:
        class GitProbe:
            def inspect(self, root: Path, saved: continuity.RunState):
                return continuity.GitSnapshot(
                    str(root), True, "current-head", recorded_head_exists=False
                )

        class CanonicalProbe:
            def status(self, root: Path, saved: continuity.RunState):
                return TaskStatus.OPEN

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = state(
                worktree_path=str(root),
                spec_path=None,
                plan_path=None,
                tasks_path=None,
                uml_paths=(),
                report_paths=(),
                artifact_paths=(),
            )
            continuity.create_run(root, saved, "Resume.")
            with self.assertRaisesRegex(ValueError, "recorded.*head"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(),
                    canonical_probe=CanonicalProbe(),
                    live_agent_ids=(),
                )

    def test_recovery_rejects_an_empty_resume_brief(self) -> None:
        class GitProbe:
            def inspect(self, root: Path, saved: continuity.RunState):
                return continuity.GitSnapshot(str(root), True, "head")

        class CanonicalProbe:
            def status(self, root: Path, saved: continuity.RunState):
                return TaskStatus.OPEN

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = state(
                worktree_path=str(root),
                spec_path=None,
                plan_path=None,
                tasks_path=None,
                uml_paths=(),
                report_paths=(),
                artifact_paths=(),
            )
            continuity.create_run(root, saved, "")
            with self.assertRaisesRegex(ValueError, "resume.*empty"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(),
                    canonical_probe=CanonicalProbe(),
                    live_agent_ids=(),
                )

    def test_recovery_validates_decisions_and_events_even_when_state_needs_no_rewrite(self) -> None:
        class GitProbe:
            def inspect(self, root: Path, saved: continuity.RunState):
                return continuity.GitSnapshot(str(root), True, saved.last_observed_head)

        class CanonicalProbe:
            def status(self, root: Path, saved: continuity.RunState):
                return TaskStatus.OPEN

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            saved = state(
                worktree_path=str(root),
                active_agent_ids=(),
                spec_path=None,
                plan_path=None,
                tasks_path=None,
                uml_paths=(),
                report_paths=(),
                artifact_paths=(),
            )
            run = continuity.create_run(root, saved, "Resume.")
            for filename in ("decisions.md", "events.jsonl"):
                path = run / filename
                original = path.read_bytes()
                path.unlink()
                with self.subTest(filename=filename), self.assertRaisesRegex(
                    ValueError, "run.*incomplete"
                ):
                    continuity.recover_run(
                        root,
                        "EM-002",
                        git_probe=GitProbe(),
                        canonical_probe=CanonicalProbe(),
                        live_agent_ids=(),
                    )
                path.write_bytes(original)
            (run / "events.jsonl").write_text("{broken\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "event stream"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(),
                    canonical_probe=CanonicalProbe(),
                    live_agent_ids=(),
                )

    def test_local_canonical_probe_refuses_a_generated_github_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cached = BacklogItem(
                "EM-002",
                "Remote canonical work",
                TaskStatus.COMPLETE,
                Priority.P1,
                None,
                (),
                "",
                "2026-09-04T10:20:30Z",
            )
            (root / "BACKLOG.md").write_text(
                render_backlog(BacklogDocument("EM", "github-cache", (cached,))),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "remote canonical probe"):
                continuity.BacklogCanonicalProbe().status(root, state())

            saved = state(
                worktree_path=str(root),
                active_agent_ids=(),
                spec_path=None,
                plan_path=None,
                tasks_path=None,
                uml_paths=(),
                report_paths=(),
                artifact_paths=(),
            )
            continuity.create_run(root, saved, "Resume.")

            class GitProbe:
                def inspect(self, root: Path, saved: continuity.RunState):
                    return continuity.GitSnapshot(str(root), True, saved.last_observed_head)

            class DummyCanonicalProbe:
                def status(self, root: Path, saved: continuity.RunState):
                    return TaskStatus.OPEN

            with self.assertRaisesRegex(ValueError, "remote canonical probe"):
                continuity.recover_run(
                    root,
                    "EM-002",
                    git_probe=GitProbe(),
                    canonical_probe=DummyCanonicalProbe(),
                    live_agent_ids=(),
                )


if __name__ == "__main__":
    unittest.main()
