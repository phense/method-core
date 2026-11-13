"""Versioned compact-continuity state, events, and evidence-based recovery."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields, replace
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Collection, Mapping, Protocol

from .backlog import load_backlog, load_backlog_history
from .files import (
    append_jsonl,
    atomic_write_bundle,
    atomic_write_json,
    atomic_write_text,
    require_contained_path,
    require_repo_relative,
    require_safe_component,
)
from .models import RFC_3339_UTC_PATTERN, TaskStatus, parse_task_id, utc_timestamp


SCHEMA_VERSION = 1
GIT_TIMEOUT_SECONDS = 15
EVENT_KINDS = frozenset(
    {
        "workflow_started",
        "phase_changed",
        "slice_started",
        "decision_recorded",
        "agent_dispatched",
        "agent_completed",
        "verification_failed",
        "verification_passed",
        "workflow_completed",
    }
)
PRODUCER_EVENT_FIELDS = frozenset({"schema_version", "timestamp", "work_id", "sequence"})
SENSITIVE_TERMS = ("token", "password", "secret", "authorization", "cookie")
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)(?:\b[A-Za-z0-9_-]*(?:token|password|secret|authorization|cookie)"
    r"[A-Za-z0-9_-]*\s*[:=]\s*\S+|"
    r"\bbearer\s+\S+|\bgh[pousr]_[A-Za-z0-9_]+)"
)
TUPLE_FIELDS = frozenset(
    {
        "uml_paths",
        "report_paths",
        "artifact_paths",
        "completed_work",
        "active_work",
        "pending_work",
        "active_agent_ids",
        "completed_agent_ids",
        "open_findings",
        "failing_checks",
    }
)


def _single_line(value: object, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{field} must be {'text' if allow_empty else 'non-empty text'}")
    if "\n" in value or "\r" in value:
        raise ValueError(f"{field} must not contain a newline")
    return value


def _contains_sensitive(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(term in lowered for term in SENSITIVE_TERMS) or _contains_sensitive(item):
                return True
        return False
    if isinstance(value, (tuple, list, set)):
        return any(_contains_sensitive(item) for item in value)
    return isinstance(value, str) and SENSITIVE_VALUE_PATTERN.search(value) is not None


def reject_sensitive_content(value: object, *, artifact: str) -> None:
    if _contains_sensitive(value):
        raise ValueError(f"{artifact} contains sensitive content")


@dataclass(frozen=True)
class RunState:
    work_id: str
    lifecycle: str
    phase: str
    next_action: str
    backlog_id: str | None = None
    issue_id: int | None = None
    feature_id: str | None = None
    change_id: str | None = None
    current_slice: str | None = None
    spec_path: str | None = None
    plan_path: str | None = None
    tasks_path: str | None = None
    uml_paths: tuple[str, ...] = ()
    report_paths: tuple[str, ...] = ()
    artifact_paths: tuple[str, ...] = ()
    worktree_path: str = "."
    base_commit: str = ""
    last_observed_head: str = ""
    completed_work: tuple[str, ...] = ()
    active_work: tuple[str, ...] = ()
    pending_work: tuple[str, ...] = ()
    active_agent_ids: tuple[str, ...] = ()
    completed_agent_ids: tuple[str, ...] = ()
    open_findings: tuple[str, ...] = ()
    failing_checks: tuple[str, ...] = ()
    verification_command: str | None = None
    verification_timestamp: str | None = None
    verification_output_digest: str | None = None
    schema_version: int = SCHEMA_VERSION
    coordination_mode: str = "observed"

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("invalid run schema version")
        if self.coordination_mode not in ("observed", "coordinator-only"):
            raise ValueError("invalid coordination mode")
        if self.coordination_mode == "coordinator-only" and (self.active_agent_ids or self.completed_agent_ids):
            raise ValueError("coordinator-only runs cannot contain agent identities")
        require_safe_component(self.work_id, field="work ID")
        _single_line(self.lifecycle, field="lifecycle")
        _single_line(self.phase, field="phase")
        _single_line(self.next_action, field="next action")
        if self.backlog_id is not None:
            parse_task_id(self.backlog_id)
        if self.issue_id is not None and (type(self.issue_id) is not int or self.issue_id <= 0):
            raise ValueError("issue ID must be a positive integer")
        if self.feature_id is not None and re.fullmatch(r"F-0*[1-9][0-9]*", self.feature_id) is None:
            raise ValueError("feature ID must use the F-NNN form")
        if self.change_id is not None:
            require_safe_component(self.change_id, field="change ID")
        if self.current_slice is not None:
            _single_line(self.current_slice, field="current slice")
        for path in self.all_artifact_paths:
            require_repo_relative(path)
        _single_line(self.worktree_path, field="worktree path")
        for field_name in ("base_commit", "last_observed_head"):
            _single_line(getattr(self, field_name), field=field_name, allow_empty=True)
        for field_name in TUPLE_FIELDS:
            values = getattr(self, field_name)
            if not isinstance(values, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            for value in values:
                _single_line(value, field=field_name)
        verification = (
            self.verification_command,
            self.verification_timestamp,
            self.verification_output_digest,
        )
        if any(value is not None for value in verification):
            if any(value is None for value in verification):
                raise ValueError("latest successful verification fields must be recorded together")
            _single_line(self.verification_command, field="verification command")
            if not RFC_3339_UTC_PATTERN.fullmatch(self.verification_timestamp or ""):
                raise ValueError("verification timestamp must be UTC RFC-3339")
            if re.fullmatch(r"[0-9a-f]{64}", self.verification_output_digest or "") is None:
                raise ValueError("verification output digest must be lowercase SHA-256")
        reject_sensitive_content(asdict(self), artifact="run state")

    @property
    def all_artifact_paths(self) -> tuple[str, ...]:
        optional = tuple(
            path for path in (self.spec_path, self.plan_path, self.tasks_path) if path is not None
        )
        return optional + self.uml_paths + self.report_paths + self.artifact_paths


@dataclass(frozen=True)
class GitSnapshot:
    worktree_path: str
    base_commit_exists: bool
    head_commit: str
    recorded_head_exists: bool = True


class GitProbe(Protocol):
    def inspect(self, root: Path, state: RunState) -> GitSnapshot: ...


class CanonicalWorkProbe(Protocol):
    def status(self, root: Path, state: RunState) -> TaskStatus | None: ...


class SubprocessGitProbe:
    """Inspect the actual worktree and commits with bounded local git commands."""

    def _run(self, root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                ("git", *arguments),
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
                timeout=GIT_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError("git recovery probe timed out") from error
        except OSError as error:
            raise ValueError("git recovery probe is unavailable") from error
        return result

    def inspect(self, root: Path, state: RunState) -> GitSnapshot:
        worktree = self._run(root, "rev-parse", "--show-toplevel")
        head = self._run(root, "rev-parse", "HEAD")
        if worktree.returncode != 0 or head.returncode != 0:
            raise ValueError("cannot inspect recovery worktree")
        base_exists = True
        if state.base_commit:
            base = self._run(root, "cat-file", "-e", f"{state.base_commit}^{{commit}}")
            base_exists = base.returncode == 0
        recorded_head_exists = True
        if state.last_observed_head:
            recorded_head = self._run(
                root, "cat-file", "-e", f"{state.last_observed_head}^{{commit}}"
            )
            recorded_head_exists = recorded_head.returncode == 0
        return GitSnapshot(
            worktree.stdout.strip(),
            base_exists,
            head.stdout.strip(),
            recorded_head_exists,
        )


class BacklogCanonicalProbe:
    """Read completion from the repository's active/cache backlog plus local archive."""

    def status(self, root: Path, state: RunState) -> TaskStatus | None:
        identifier = state.backlog_id or state.work_id
        backlog_path = root / "BACKLOG.md"
        if not backlog_path.is_file():
            return None
        if load_backlog(backlog_path).mode == "github-cache":
            raise ValueError("GitHub mode recovery requires a remote canonical probe")
        document = load_backlog_history(backlog_path)
        entry = next((item for item in document.items if item.id == identifier), None)
        return entry.status if entry is not None else None


class GitHubCanonicalProbe:
    """Read canonical completion directly from GitHub rather than its generated cache."""

    def __init__(self, gateway: Any, repository: Any, *, project_key: str) -> None:
        self._gateway = gateway
        self._repository = repository
        self._project_key = project_key

    def status(self, root: Path, state: RunState) -> TaskStatus | None:
        from .issues import remote_backlog

        identifier = state.backlog_id or state.work_id
        document = remote_backlog(
            self._gateway, self._repository, project_key=self._project_key
        )
        entry = next((item for item in document.items if item.id == identifier), None)
        return entry.status if entry is not None else None


@dataclass(frozen=True)
class RecoveryResult:
    state: RunState
    redispatchable_agent_ids: tuple[str, ...]
    next_action: str
    canonical_status: TaskStatus | None

    @property
    def completed_work(self) -> tuple[str, ...]:
        return self.state.completed_work


def _run(root: Path, work_id: str) -> Path:
    require_safe_component(work_id, field="work ID")
    return require_contained_path(
        root,
        root / ".engineering-method" / "runs" / work_id,
        field="continuity run path",
    )


def _state_payload(state: RunState) -> dict[str, object]:
    return asdict(state)


def _state_bytes(state: RunState) -> bytes:
    return (
        json.dumps(_state_payload(state), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def create_run(
    root: Path,
    state: RunState,
    resume_markdown: str,
    decisions_markdown: str = "",
    *,
    replace_existing: bool = False,
) -> Path:
    reject_sensitive_content(resume_markdown, artifact="resume")
    reject_sensitive_content(decisions_markdown, artifact="decisions")
    run = _run(root, state.work_id)
    if state.coordination_mode == "coordinator-only" and (run.exists() or run.is_symlink()):
        raise ValueError("coordinator-only provenance requires a verified absent run")
    if run.exists() and not replace_existing:
        raise ValueError(f"run already exists: {state.work_id}")
    runs_root = require_contained_path(
        root, root / ".engineering-method" / "runs", field="continuity runs path"
    )
    runs_root.mkdir(parents=True, exist_ok=True)
    require_contained_path(root, runs_root, field="continuity runs path")
    staging = Path(tempfile.mkdtemp(prefix=f".{state.work_id}.new.", dir=runs_root))
    backup: Path | None = None
    try:
        (staging / "agent-reports").mkdir()
        atomic_write_bundle(
            {
                staging / "state.json": _state_bytes(state),
                staging / "resume.md": resume_markdown.encode("utf-8"),
                staging / "decisions.md": decisions_markdown.encode("utf-8"),
                staging / "events.jsonl": b"",
            }
        )
        if run.exists():
            backup = Path(
                tempfile.mkdtemp(prefix=f".{state.work_id}.old.", dir=runs_root)
            )
            backup.rmdir()
            os.replace(run, backup)
        try:
            os.replace(staging, run)
        except OSError:
            if backup is not None and backup.exists() and not run.exists():
                os.replace(backup, run)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup is not None and backup.exists():
            if not run.exists():
                os.replace(backup, run)
            else:
                shutil.rmtree(backup)
    return run


def _upgrade_payload(payload: object) -> tuple[dict[str, object], bool]:
    if not isinstance(payload, dict):
        raise ValueError("run state must be a JSON object")
    version = payload.get("schema_version", 0)
    if type(version) is not int:
        raise ValueError("run schema version must be an integer")
    if version > SCHEMA_VERSION:
        raise ValueError("future run schema is unsupported")
    upgraded = dict(payload)
    changed = version < SCHEMA_VERSION
    if version == 0:
        completed = upgraded.pop("completed_slices", upgraded.get("completed_work", []))
        upgraded["completed_work"] = completed
        upgraded["schema_version"] = SCHEMA_VERSION
    for field_name in TUPLE_FIELDS:
        if field_name in upgraded and isinstance(upgraded[field_name], list):
            upgraded[field_name] = tuple(upgraded[field_name])
    return upgraded, changed


def load_run_state(
    root: Path, work_id: str, *, persist_upgrade: bool = False
) -> RunState:
    run = _run(root, work_id)
    path = require_contained_path(
        root, run / "state.json", field="continuity state path"
    )
    if not run.is_dir() or not path.is_file():
        raise ValueError("run does not exist or has no valid state")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("run state is unreadable or malformed") from error
    upgraded, changed = _upgrade_payload(payload)
    allowed = {field.name for field in fields(RunState)}
    unknown = set(upgraded) - allowed
    if unknown:
        raise ValueError(f"run state contains unknown fields: {', '.join(sorted(unknown))}")
    try:
        state = RunState(**upgraded)
    except (TypeError, ValueError) as error:
        raise ValueError(f"run state is invalid: {error}") from error
    if state.work_id != work_id:
        raise ValueError("run directory and state work IDs disagree")
    if changed and persist_upgrade:
        atomic_write_json(path, _state_payload(state))
    return state


def run_state_from_payload(payload: object, *, work_id: str) -> RunState:
    """Validate CLI JSON input without allowing it to redirect the target run."""
    if not isinstance(payload, dict):
        raise ValueError("run state input must be a JSON object")
    supplied_work_id = payload.get("work_id")
    if supplied_work_id is not None and supplied_work_id != work_id:
        raise ValueError("state work ID does not match the command target")
    candidate = dict(payload)
    candidate["work_id"] = work_id
    candidate.setdefault("schema_version", SCHEMA_VERSION)
    upgraded, _ = _upgrade_payload(candidate)
    allowed = {field.name for field in fields(RunState)}
    unknown = set(upgraded) - allowed
    if unknown:
        raise ValueError(f"run state input contains unknown fields: {', '.join(sorted(unknown))}")
    try:
        return RunState(**upgraded)
    except (TypeError, ValueError) as error:
        raise ValueError(f"run state input is invalid: {error}") from error


def checkpoint(
    root: Path,
    work_id: str,
    state: RunState,
    resume_markdown: str | None = None,
) -> None:
    if work_id != state.work_id:
        raise ValueError("checkpoint work ID does not match state")
    run = _run(root, work_id)
    previous = load_run_state(root, work_id)
    if state.coordination_mode != previous.coordination_mode:
        raise ValueError("coordination mode is immutable after initialization")
    _require_complete_run_tree(root, run)
    resume_path = require_contained_path(
        root, run / "resume.md", field="continuity resume path"
    )
    if resume_markdown is None:
        if not resume_path.is_file():
            raise ValueError("run resume does not exist")
        resume_markdown = resume_path.read_text(encoding="utf-8")
    reject_sensitive_content(resume_markdown, artifact="resume")
    atomic_write_bundle(
        {
            run / "state.json": _state_bytes(state),
            resume_path: resume_markdown.encode("utf-8"),
        }
    )


def _require_complete_run_tree(root: Path, run: Path) -> None:
    required_files = ("state.json", "resume.md", "decisions.md", "events.jsonl")
    paths = [
        require_contained_path(root, run / name, field=f"continuity {name} path")
        for name in required_files
    ]
    reports = require_contained_path(
        root, run / "agent-reports", field="continuity agent reports path"
    )
    missing = [name for name, path in zip(required_files, paths) if not path.is_file()]
    if not reports.is_dir():
        missing.append("agent-reports/")
    if missing:
        raise ValueError(f"run is incomplete: missing {', '.join(missing)}")


def _event_sequence(path: Path, *, work_id: str) -> int:
    if not path.exists():
        return 1
    count = 0
    for expected_sequence, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError("event stream contains malformed JSON") from error
        if not isinstance(payload, dict):
            raise ValueError("event stream contains an invalid record")
        if (
            payload.get("schema_version") != SCHEMA_VERSION
            or payload.get("work_id") != work_id
            or payload.get("kind") not in EVENT_KINDS
            or payload.get("sequence") != expected_sequence
            or not isinstance(payload.get("timestamp"), str)
            or RFC_3339_UTC_PATTERN.fullmatch(payload["timestamp"]) is None
        ):
            raise ValueError("event stream contains an invalid record")
        reject_sensitive_content(payload, artifact="event stream")
        _validate_event_paths(payload)
        count += 1
    return count + 1


def _validate_event_paths(event: Mapping[str, object]) -> None:
    for key, value in event.items():
        if key == "artifact" or key.endswith("_path"):
            if not isinstance(value, str):
                raise ValueError("event artifact paths must be text")
            require_repo_relative(value)
        elif key.endswith("_paths"):
            if not isinstance(value, (tuple, list)):
                raise ValueError("event artifact path collections must be lists")
            for path in value:
                if not isinstance(path, str):
                    raise ValueError("event artifact paths must be text")
                require_repo_relative(path)


def append_event(
    root: Path, work_id: str, event: Mapping[str, object]
) -> dict[str, object]:
    state = load_run_state(root, work_id)
    _require_complete_run_tree(root, _run(root, work_id))
    if not isinstance(event, Mapping):
        raise ValueError("event must be an object")
    if PRODUCER_EVENT_FIELDS & set(event):
        raise ValueError("event contains producer-owned fields")
    if event.get("kind") not in EVENT_KINDS:
        raise ValueError("event kind is invalid")
    if state.coordination_mode == "coordinator-only" and event.get("kind") in {"agent_dispatched", "agent_completed"}:
        raise ValueError("coordinator-only runs cannot record delegation")
    reject_sensitive_content(event, artifact="event")
    _validate_event_paths(event)
    if "status" in event and event["status"] not in {
        "open",
        "in_progress",
        "complete",
        "blocked",
        "pending",
        "active",
        "passed",
        "failed",
    }:
        raise ValueError("event status is invalid")
    path = require_contained_path(
        root,
        _run(root, work_id) / "events.jsonl",
        field="continuity event stream path",
    )
    payload = {
        **event,
        "schema_version": SCHEMA_VERSION,
        "work_id": work_id,
        "timestamp": utc_timestamp(),
        "sequence": _event_sequence(path, work_id=work_id),
    }
    append_jsonl(path, payload)
    return payload


def write_agent_report(root: Path, work_id: str, agent_id: str, markdown: str) -> Path:
    if load_run_state(root, work_id).coordination_mode == "coordinator-only":
        raise ValueError("coordinator-only runs cannot record agent reports")
    _require_complete_run_tree(root, _run(root, work_id))
    require_safe_component(agent_id, field="agent ID")
    reject_sensitive_content(markdown, artifact="agent report")
    path = require_contained_path(
        root,
        _run(root, work_id) / "agent-reports" / f"{agent_id}.md",
        field="continuity agent report path",
    )
    atomic_write_text(path, markdown)
    return path


def _validate_recovery_artifacts(root: Path, state: RunState) -> None:
    repository = root.resolve()
    for relative in state.all_artifact_paths:
        artifact = (root / relative).resolve()
        try:
            artifact.relative_to(repository)
        except ValueError as error:
            raise ValueError(f"recovery artifact escapes worktree: {relative}") from error
        if not artifact.exists():
            raise ValueError(f"recovery artifact does not exist: {relative}")


def _read_recovery_text(run: Path, name: str, *, required: bool) -> str:
    path = run / name
    if not path.is_file():
        if required:
            raise ValueError(f"run {name.removesuffix('.md')} does not exist")
        return ""
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ValueError(f"run {name} cannot be read") from error
    reject_sensitive_content(content, artifact=name)
    if required and not content.strip():
        raise ValueError(f"run {name.removesuffix('.md')} is empty")
    return content


def recover_run(
    root: Path,
    work_id: str,
    *,
    git_probe: GitProbe,
    canonical_probe: CanonicalWorkProbe,
    live_agent_ids: Collection[str] | None,
) -> RecoveryResult:
    run = _run(root, work_id)
    state = load_run_state(root, work_id, persist_upgrade=live_agent_ids is not None)
    if live_agent_ids is None and state.coordination_mode != "coordinator-only":
        raise ValueError("ordinary runs require an explicit host observation")
    _require_complete_run_tree(root, run)
    resume = _read_recovery_text(run, "resume.md", required=True)
    _read_recovery_text(run, "decisions.md", required=False)
    _event_sequence(
        require_contained_path(
            root, run / "events.jsonl", field="continuity event stream path"
        ),
        work_id=work_id,
    )
    reports = require_contained_path(
        root, run / "agent-reports", field="continuity agent reports path"
    )
    for report in reports.iterdir():
        if not report.is_file():
            raise ValueError("run agent reports contain an unsafe entry")
        reject_sensitive_content(report.read_text(encoding="utf-8"), artifact="agent report")
    if live_agent_ids is None:
        events = [json.loads(line) for line in (run / "events.jsonl").read_text().splitlines() if line.strip()]
        if any(event.get("kind") in {"agent_dispatched", "agent_completed"}
               or any("agent" in key for key in event) for event in events) or any(reports.iterdir()):
            raise ValueError("coordinator-only recovery found prior or ambiguous agent activity")
    _validate_recovery_artifacts(root, state)

    backlog_path = root / "BACKLOG.md"
    if (
        backlog_path.is_file()
        and load_backlog(backlog_path).mode == "github-cache"
        and not isinstance(canonical_probe, GitHubCanonicalProbe)
    ):
        raise ValueError("GitHub mode recovery requires a remote canonical probe")

    snapshot = git_probe.inspect(root, state)
    expected_worktree = (
        Path(state.worktree_path)
        if Path(state.worktree_path).is_absolute()
        else root / state.worktree_path
    ).resolve()
    if Path(snapshot.worktree_path).resolve() != expected_worktree:
        raise ValueError("recorded and actual recovery worktree disagree")
    if state.base_commit and not snapshot.base_commit_exists:
        raise ValueError("recorded recovery base commit does not exist")
    if state.last_observed_head and not snapshot.recorded_head_exists:
        raise ValueError("recorded recovery head commit does not exist")
    if not snapshot.head_commit:
        raise ValueError("recovery git head is empty")

    canonical_status = canonical_probe.status(root, state)
    live = set(live_agent_ids) if live_agent_ids is not None else set()
    if canonical_status is TaskStatus.COMPLETE:
        completed = list(state.completed_work)
        for work in (*state.active_work, *((state.current_slice,) if state.current_slice else ())):
            if work not in completed:
                completed.append(work)
        pending = tuple(
            work
            for work in state.pending_work
            if work not in completed and "complete" not in work.lower()
        )
        next_action = pending[0] if pending else "Run final verification and prepare handoff"
        recovered_state = replace(
            state,
            last_observed_head=snapshot.head_commit,
            completed_work=tuple(completed),
            active_work=(),
            pending_work=pending,
            active_agent_ids=(),
            next_action=next_action,
        )
        redispatchable: tuple[str, ...] = ()
    else:
        redispatchable = tuple(agent for agent in state.active_agent_ids if agent not in live)
        still_active = tuple(agent for agent in state.active_agent_ids if agent in live)
        repeats_completed = any(
            completed.lower() in state.next_action.lower() for completed in state.completed_work
        )
        if redispatchable:
            next_action = "Redispatch unavailable agents: " + ", ".join(redispatchable)
        elif repeats_completed:
            next_action = next(
                (work for work in state.pending_work if work not in state.completed_work),
                "Run final verification and prepare handoff",
            )
        else:
            next_action = state.next_action
        recovered_state = replace(
            state,
            last_observed_head=snapshot.head_commit,
            active_agent_ids=still_active,
            next_action=next_action,
        )
    if recovered_state != state:
        checkpoint(root, work_id, recovered_state, resume)
    return RecoveryResult(
        recovered_state, redispatchable, recovered_state.next_action, canonical_status
    )
