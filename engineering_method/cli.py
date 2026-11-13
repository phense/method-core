"""Dependency-free, non-destructive command adapters for project-state workflows."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import TextIO

from .backlog import (
    BacklogDocument,
    load_backlog,
    load_backlog_history,
    render_backlog,
    write_backlog,
)
from .continuity import (
    BacklogCanonicalProbe,
    GitHubCanonicalProbe,
    SubprocessGitProbe,
    append_event,
    checkpoint,
    create_run,
    load_run_state,
    recover_run,
    run_state_from_payload,
)
from .features import FeatureDocument, load_features, remove_feature, render_features, upsert_feature
from .files import atomic_write_bundle, atomic_write_text, require_repo_relative
from .gh import GitHubIssuesGateway, RepositoryRef
from .issues import (
    IssueGateway,
    migrate_local_backlog,
    overlay_pending_queue,
    queue_mutation,
    refresh_issue_cache,
    replay_pending_queue,
    workflow_state_check,
)
from .models import BacklogItem, Feature, Priority, TaskStatus, derive_project_key, utc_timestamp


HELP_TEXT = {
    (): """Usage: project-state <command> [action] [options]

Commands:
  backlog             Manage durable task state.
  feature             Manage the capability inventory.
  continuity-state    Manage compact-continuity runs and events.
  backlog-to-issues   Migrate or reconcile GitHub Issues.
  refresh-issue-cache Refresh the generated GitHub Issues cache.

Options:
  --help              Show help for a command or action.""",
    ("backlog",): """Usage: project-state backlog <action> [options]

Actions:
  init          Initialize BACKLOG.md and FEATURES.md.
  state-check   Detect canonical local or GitHub mode.
  add           Add a stable backlog item.
  start         Mark an item in progress.
  block         Mark an item blocked.
  complete      Mark an item complete.
  priority      Change priority without changing identity.
  dependencies  Replace dependency IDs.
  archive       Archive eligible completed groups.

Options:
  --help        Show help for an action.""",
    ("backlog", "init"): """Usage: project-state backlog init [--project-key KEY] [--replace]

Action:
  Initialize BACKLOG.md and FEATURES.md without replacing existing state by default.

Options:
  --project-key KEY  Set the stable uppercase project key.
  --replace          Explicitly replace existing project state.
  --help             Show this help.""",
    ("backlog", "state-check"): """Usage: project-state backlog state-check

Action:
  Detect local or writable GitHub canonical mode without a methodology prompt.

Options:
  --help  Show this help.""",
    ("backlog", "add"): """Usage: project-state backlog add --id ID --title TEXT --priority P0-P3 [options]

Action:
  Add one item with a stable caller-supplied ID.

Options:
  --parent ID       Set the parent backlog ID.
  --depends-on IDS Set comma-separated dependency IDs.
  --notes TEXT      Store concise notes.
  --help            Show this help.""",
    ("backlog", "start"): """Usage: project-state backlog start <backlog-id> [options]

Action:
  Mark one backlog item in progress.

Options:
  --notes TEXT      Replace concise notes.
  --depends-on IDS Replace comma-separated dependency IDs.
  --help            Show this help.""",
    ("backlog", "block"): """Usage: project-state backlog block <backlog-id> [options]

Action:
  Mark one backlog item blocked.

Options:
  --notes TEXT      Record the blocker.
  --depends-on IDS Replace comma-separated dependency IDs.
  --help            Show this help.""",
    ("backlog", "complete"): """Usage: project-state backlog complete <backlog-id> [options]

Action:
  Mark one backlog item complete.

Options:
  --notes TEXT      Replace concise notes.
  --depends-on IDS Replace comma-separated dependency IDs.
  --help            Show this help.""",
    ("backlog", "priority"): """Usage: project-state backlog priority <backlog-id> <P0-P3>

Action:
  Change priority without changing the stable backlog ID.

Options:
  --help  Show this help.""",
    ("backlog", "dependencies"): """Usage: project-state backlog dependencies <backlog-id> --depends-on IDS

Action:
  Replace comma-separated dependency IDs.

Options:
  --depends-on IDS  Required dependency IDs; use an empty value for none.
  --help             Show this help.""",
    ("backlog", "archive"): """Usage: project-state backlog archive [options]

Action:
  Archive eligible completed groups in local canonical mode.

Options:
  --active-line-limit N  Set the archive trigger line count.
  --target-line-limit N  Set the active-file target line count.
  --help                 Show this help.""",
    ("feature",): """Usage: project-state feature <action> [options]

Actions:
  add     Add a verified capability.
  change  Update a verified capability.
  remove  Retain a removed capability with rationale.

Options:
  --help  Show help for an action.""",
    ("feature", "add"): """Usage: project-state feature add --id ID --name TEXT --summary TEXT [options]

Action:
  Add one verified capability.

Options:
  --status VALUE  Set available, changed, or removed.
  --related IDS   Set comma-separated related backlog IDs.
  --help          Show this help.""",
    ("feature", "change"): """Usage: project-state feature change --id ID [options]

Action:
  Update one existing capability without changing its identity.

Options:
  --name TEXT     Replace the capability name.
  --summary TEXT  Replace the summary.
  --status VALUE  Set available, changed, or removed.
  --related IDS   Replace related backlog IDs.
  --help          Show this help.""",
    ("feature", "remove"): """Usage: project-state feature remove --id ID --rationale TEXT

Action:
  Retain a removed capability as history with its rationale.

Options:
  --id ID           Select the capability.
  --rationale TEXT  Record why it was removed.
  --help             Show this help.""",
    ("backlog-to-issues",): """Usage: backlog-to-issues <action>

Actions:
  migrate    Detect a writable repository and migrate local history.
  reconcile  Replay pending offline mutations in causal order.

Options:
  --help  Show help for an action.""",
    ("backlog-to-issues", "migrate"): """Usage: backlog-to-issues migrate

Action:
  Detect writable GitHub Issues and migrate local backlog history idempotently.

Options:
  --help  Show this help for migrate.""",
    ("backlog-to-issues", "reconcile"): """Usage: backlog-to-issues reconcile

Action:
  Reconcile pending offline mutations against canonical GitHub Issues.

Options:
  --help  Show this help for reconcile.""",
    ("refresh-issue-cache",): """Usage: refresh-issue-cache [--help]

Action:
  Refresh the generated read-only BACKLOG.md cache from canonical GitHub Issues.

Options:
  --help  Show this help.""",
    ("continuity-state",): """Usage: continuity-state <action> <work-id> [options]

Actions:
  init        Initialize a durable run.
  checkpoint  Replace run state and optionally its resume brief.
  event       Append one provider-neutral event.
  status      Validate and print the state path.
  recover     Reconcile saved state with current evidence.

Options:
  --help  Show help for an action.""",
    ("continuity-state", "init"): """Usage: continuity-state init <work-id> --file PATH --resume-file PATH [options]

Action:
  Initialize a durable run from repository-relative JSON and Markdown inputs.

Options:
  --file PATH            Read run state JSON; use - for stdin.
  --resume-file PATH     Read the required recovery brief.
  --decisions-file PATH  Read optional durable decisions.
  --replace              Explicitly replace an existing run.
  --help                 Show this help.""",
    ("continuity-state", "checkpoint"): """Usage: continuity-state checkpoint <work-id> --file PATH [options]

Action:
  Atomically checkpoint run state and optionally replace its resume brief.

Options:
  --file PATH         Read run state JSON; use - for stdin.
  --resume-file PATH  Read a replacement recovery brief.
  --help              Show this help.""",
    ("continuity-state", "event"): """Usage: continuity-state event <work-id> --file PATH

Action:
  Append one validated provider-neutral event.

Options:
  --file PATH  Read event JSON; use - for stdin.
  --help       Show this help.""",
    ("continuity-state", "status"): """Usage: continuity-state status <work-id>

Action:
  Validate the named run and print its state path.

Options:
  work-id  Stable run identifier.
  --help   Show this help.""",
    ("continuity-state", "recover"): """Usage: continuity-state recover <work-id> (--live-agents IDS | --coordinator-only)

Action:
  Reconcile the run with git, artifacts, canonical task state, and observed agents.

Options:
  --live-agents IDS  Required comma-separated host-observed IDs; empty means confirmed none.
  --coordinator-only  No observation; requires immutable no-delegation provenance and no agent history.
  --help             Show this help.""",
}


def _error(message: str) -> int:
    print(message, file=sys.stderr)
    return 2


def _parse(
    arguments: list[str],
    *,
    value_options: frozenset[str] = frozenset(),
    flags: frozenset[str] = frozenset(),
) -> tuple[list[str], dict[str, str], set[str]]:
    positionals: list[str] = []
    values: dict[str, str] = {}
    enabled: set[str] = set()
    index = 0
    while index < len(arguments):
        argument = arguments[index]
        if argument in flags:
            if argument in enabled:
                raise ValueError(f"duplicate option: {argument}")
            enabled.add(argument)
            index += 1
        elif argument in value_options:
            if argument in values:
                raise ValueError(f"duplicate option: {argument}")
            if index + 1 >= len(arguments):
                raise ValueError(f"{argument} requires a value")
            values[argument] = arguments[index + 1]
            index += 2
        elif argument.startswith("--"):
            raise ValueError(f"unsupported option: {argument}")
        else:
            positionals.append(argument)
            index += 1
    return positionals, values, enabled


def _required(options: dict[str, str], name: str) -> str:
    if name not in options:
        raise ValueError(f"{name} is required")
    return options[name]


def _csv(value: str | None, *, option: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if value == "":
        return ()
    values = tuple(part.strip() for part in value.split(","))
    if any(not part for part in values):
        raise ValueError(f"{option} contains an empty value")
    return values


def _help_text(arguments: list[str]) -> str | None:
    if "--help" not in arguments:
        return None
    if arguments.count("--help") != 1 or arguments[-1] != "--help":
        raise ValueError("--help must appear once at the end of a command path")
    topic = tuple(arguments[:-1])
    if topic not in HELP_TEXT:
        raise ValueError("unsupported help topic")
    return HELP_TEXT[topic]


def _read_repo_input(root: Path, value: str, *, stream: TextIO) -> str:
    if value == "-":
        return stream.read()
    relative = require_repo_relative(value)
    repository = root.resolve()
    path = (root / relative).resolve()
    try:
        path.relative_to(repository)
    except ValueError as error:
        raise ValueError("input file escapes the repository") from error
    if not path.is_file():
        raise ValueError(f"input file does not exist: {relative}")
    return path.read_text(encoding="utf-8")


def _write_local_backlog(root: Path, document: BacklogDocument) -> None:
    write_backlog(root / "BACKLOG.md", document)


def _load_mutable_backlog(root: Path) -> BacklogDocument:
    return load_backlog(root / "BACKLOG.md")


def _replace_item(
    document: BacklogDocument, identifier: str, transform
) -> BacklogDocument:
    found = False
    items: list[BacklogItem] = []
    for item in document.items:
        if item.id == identifier:
            found = True
            items.append(transform(item))
        else:
            items.append(item)
    if not found:
        raise ValueError("backlog ID does not exist")
    return BacklogDocument(document.project_key, document.mode, tuple(items))


def _queue_or_write(
    root: Path,
    document: BacklogDocument,
    *,
    mutations: tuple[dict[str, object], ...],
    local_document: BacklogDocument,
    gateway: IssueGateway,
) -> str:
    if document.mode == "github-cache":
        for mutation in mutations:
            queue_mutation(root, mutation)
        detection = gateway.detect_repository()
        if detection.repository is not None:
            replay_pending_queue(
                root, root / "BACKLOG.md", gateway, detection.repository
            )
            return "BACKLOG.md\n.engineering-method/github-queue.jsonl"
        return ".engineering-method/github-queue.jsonl"
    _write_local_backlog(root, local_document)
    return "BACKLOG.md"


def _backlog_command(
    arguments: list[str],
    *,
    root: Path,
    gateway: IssueGateway,
) -> str:
    if not arguments:
        raise ValueError("backlog action required")
    action, rest = arguments[0], arguments[1:]
    path = root / "BACKLOG.md"
    features_path = root / "FEATURES.md"
    if action == "init":
        positionals, options, flags = _parse(
            rest,
            value_options=frozenset({"--project-key"}),
            flags=frozenset({"--replace"}),
        )
        if positionals:
            raise ValueError("backlog init accepts no positional arguments")
        if (path.exists() or features_path.exists()) and "--replace" not in flags:
            raise ValueError("project state already exists; use --replace to reinitialize")
        key = options.get("--project-key") or derive_project_key(root.name)
        atomic_write_bundle(
            {
                path: render_backlog(BacklogDocument(key, "local", ())).encode("utf-8"),
                features_path: render_features(FeatureDocument(features=())).encode("utf-8"),
            }
        )
        archive_path = root / "BACKLOG-ARCHIVE.md"
        if "--replace" in flags and archive_path.exists():
            archive_path.unlink()
        return "BACKLOG.md\nFEATURES.md"

    if action == "state-check":
        positionals, _, _ = _parse(rest)
        if positionals:
            raise ValueError("backlog state-check accepts no arguments")
        return workflow_state_check(path, gateway).reason

    document = _load_mutable_backlog(root)
    if document.mode == "github-cache":
        document = overlay_pending_queue(root, document)
    if action == "add":
        positionals, options, _ = _parse(
            rest,
            value_options=frozenset(
                {"--id", "--title", "--priority", "--parent", "--depends-on", "--notes"}
            ),
        )
        if positionals:
            raise ValueError("backlog add accepts options only")
        identifier = _required(options, "--id")
        if document.mode == "local" and any(
            item.id == identifier for item in load_backlog_history(path).items
        ):
            raise ValueError("backlog ID already exists in active or archived history")
        title = _required(options, "--title")
        priority = Priority(_required(options, "--priority"))
        parent = options.get("--parent")
        dependencies = _csv(options.get("--depends-on"), option="--depends-on")
        notes = options.get("--notes", "")
        new_item = BacklogItem(
            identifier,
            title,
            TaskStatus.OPEN,
            priority,
            parent,
            dependencies,
            notes,
            utc_timestamp(),
        )
        local_document = BacklogDocument(
            document.project_key, document.mode, document.items + (new_item,)
        )
        return _queue_or_write(
            root,
            document,
            mutations=(
                {
                    "kind": "add",
                    "backlog_id": identifier,
                    "title": title,
                    "priority": priority.value,
                    "parent_id": parent,
                    "depends_on": list(dependencies),
                    "notes": notes,
                },
            ),
            local_document=local_document,
            gateway=gateway,
        )

    if action in {"start", "block", "complete"}:
        positionals, options, _ = _parse(
            rest, value_options=frozenset({"--notes", "--depends-on"})
        )
        if len(positionals) != 1:
            raise ValueError(f"backlog {action} requires one backlog ID")
        identifier = positionals[0]
        desired_status = {
            "start": TaskStatus.IN_PROGRESS,
            "block": TaskStatus.BLOCKED,
            "complete": TaskStatus.COMPLETE,
        }[action]

        def update(item: BacklogItem) -> BacklogItem:
            dependencies = (
                _csv(options["--depends-on"], option="--depends-on")
                if "--depends-on" in options
                else item.depends_on
            )
            return replace(
                item,
                status=desired_status,
                depends_on=dependencies,
                notes=options.get("--notes", item.notes),
                updated_at=utc_timestamp(),
            )

        local_document = _replace_item(document, identifier, update)
        mutation: dict[str, object] = {
            "kind": "status",
            "backlog_id": identifier,
            "status": desired_status.value,
        }
        if "--notes" in options:
            mutation["notes"] = options["--notes"]
        mutations = [mutation]
        if "--depends-on" in options:
            mutations.append(
                {
                    "kind": "dependencies",
                    "backlog_id": identifier,
                    "depends_on": list(
                        _csv(options["--depends-on"], option="--depends-on")
                    ),
                }
            )
        return _queue_or_write(
            root,
            document,
            mutations=tuple(mutations),
            local_document=local_document,
            gateway=gateway,
        )

    if action == "priority":
        positionals, _, _ = _parse(rest)
        if len(positionals) != 2:
            raise ValueError("backlog priority requires a backlog ID and P0-P3")
        identifier, raw_priority = positionals
        priority = Priority(raw_priority)
        local_document = _replace_item(
            document,
            identifier,
            lambda item: replace(item, priority=priority, updated_at=utc_timestamp()),
        )
        return _queue_or_write(
            root,
            document,
            mutations=(
                {"kind": "priority", "backlog_id": identifier, "priority": priority.value},
            ),
            local_document=local_document,
            gateway=gateway,
        )

    if action == "dependencies":
        positionals, options, _ = _parse(
            rest, value_options=frozenset({"--depends-on"})
        )
        if len(positionals) != 1:
            raise ValueError("backlog dependencies requires one backlog ID")
        identifier = positionals[0]
        dependencies = _csv(_required(options, "--depends-on"), option="--depends-on")
        local_document = _replace_item(
            document,
            identifier,
            lambda item: replace(
                item, depends_on=dependencies, updated_at=utc_timestamp()
            ),
        )
        return _queue_or_write(
            root,
            document,
            mutations=(
                {
                    "kind": "dependencies",
                    "backlog_id": identifier,
                    "depends_on": list(dependencies),
                },
            ),
            local_document=local_document,
            gateway=gateway,
        )

    if action == "archive":
        positionals, options, _ = _parse(
            rest,
            value_options=frozenset({"--active-line-limit", "--target-line-limit"}),
        )
        if positionals:
            raise ValueError("backlog archive accepts options only")
        if document.mode != "local":
            raise ValueError("cannot archive a github-cache backlog")
        active_limit = int(options.get("--active-line-limit", "500"))
        target_limit = int(options.get("--target-line-limit", "350"))
        _, archived = write_backlog(
            path,
            document,
            active_line_limit=active_limit,
            target_line_limit=target_limit,
        )
        return "BACKLOG.md\nBACKLOG-ARCHIVE.md" if archived else "BACKLOG.md"
    raise ValueError("unsupported backlog action")


def _feature_command(arguments: list[str], *, root: Path) -> str:
    if not arguments:
        raise ValueError("feature action required")
    document = load_features(root / "FEATURES.md")
    action, rest = arguments[0], arguments[1:]
    if action in {"add", "change"}:
        positionals, options, _ = _parse(
            rest,
            value_options=frozenset(
                {"--id", "--name", "--summary", "--status", "--related"}
            ),
        )
        if positionals:
            raise ValueError(f"feature {action} accepts options only")
        identifier = _required(options, "--id")
        existing = next((entry for entry in document.features if entry.id == identifier), None)
        if action == "change" and existing is None:
            raise ValueError("feature ID does not exist")
        name = options.get("--name", existing.name if existing else None)
        summary = options.get("--summary", existing.summary if existing else None)
        if name is None or summary is None:
            raise ValueError("--name and --summary are required for a new feature")
        status = options.get("--status", existing.status if existing else "available")
        related = (
            _csv(options["--related"], option="--related")
            if "--related" in options
            else existing.related_backlog_ids if existing else ()
        )
        document = upsert_feature(
            document,
            Feature(identifier, name, summary, status, related, utc_timestamp()),
        )
    elif action == "remove":
        positionals, options, _ = _parse(
            rest, value_options=frozenset({"--id", "--rationale"})
        )
        if positionals:
            raise ValueError("feature remove accepts options only")
        document = remove_feature(
            document,
            _required(options, "--id"),
            rationale=_required(options, "--rationale"),
        )
    else:
        raise ValueError("unsupported feature action")
    atomic_write_text(root / "FEATURES.md", render_features(document))
    return "FEATURES.md"


def _repository(gateway: IssueGateway) -> RepositoryRef:
    detection = gateway.detect_repository()
    if detection.repository is None:
        raise ValueError(detection.reason)
    return detection.repository


def _github_command(
    command: str,
    arguments: list[str],
    *,
    root: Path,
    gateway: IssueGateway,
) -> str:
    path = root / "BACKLOG.md"
    if command == "refresh-issue-cache":
        if arguments:
            raise ValueError("refresh-issue-cache accepts no arguments")
        refresh_issue_cache(path, gateway, _repository(gateway))
        return "BACKLOG.md"
    if not arguments:
        raise ValueError("backlog-to-issues requires migrate or reconcile")
    action, rest = arguments[0], arguments[1:]
    if rest:
        raise ValueError(f"backlog-to-issues {action} accepts no arguments")
    if action == "migrate":
        return migrate_local_backlog(path, gateway).reason
    if action == "reconcile":
        replay_pending_queue(root, path, gateway, _repository(gateway))
        return "BACKLOG.md\n.engineering-method/github-queue.jsonl"
    raise ValueError("backlog-to-issues requires migrate or reconcile")


def _continuity_command(
    arguments: list[str], *, root: Path, stream: TextIO, gateway: IssueGateway
) -> str:
    if not arguments:
        raise ValueError("continuity action required")
    action, rest = arguments[0], arguments[1:]
    if action in {"init", "checkpoint", "event"}:
        positionals, options, flags = _parse(
            rest,
            value_options=frozenset({"--file", "--resume-file", "--decisions-file"}),
            flags=frozenset({"--replace"}),
        )
        if len(positionals) != 1:
            raise ValueError(f"{action} requires one work ID")
        work_id = positionals[0]
        source = _required(options, "--file")
        content = _read_repo_input(root, source, stream=stream)
        if action == "event":
            if flags or "--resume-file" in options or "--decisions-file" in options:
                raise ValueError("event accepts only work ID and --file")
            append_event(root, work_id, json.loads(content))
            return f".engineering-method/runs/{work_id}/events.jsonl"
        payload = json.loads(content)
        run_state = run_state_from_payload(payload, work_id=work_id)
        if action == "init":
            if "--resume-file" not in options:
                raise ValueError("continuity init requires --resume-file")
            resume = _read_repo_input(root, options["--resume-file"], stream=stream)
            decisions = (
                _read_repo_input(root, options["--decisions-file"], stream=stream)
                if "--decisions-file" in options
                else ""
            )
            create_run(
                root,
                run_state,
                resume,
                decisions,
                replace_existing="--replace" in flags,
            )
        else:
            if flags or "--decisions-file" in options:
                raise ValueError("checkpoint does not accept --replace or --decisions-file")
            resume = (
                _read_repo_input(root, options["--resume-file"], stream=stream)
                if "--resume-file" in options
                else None
            )
            checkpoint(root, work_id, run_state, resume)
        return f".engineering-method/runs/{work_id}"

    positionals, options, flags = _parse(
        rest, value_options=frozenset({"--live-agents"}), flags=frozenset({"--coordinator-only"})
    )
    if (flags and action != "recover") or len(positionals) != 1:
        raise ValueError(f"{action} requires one work ID")
    work_id = positionals[0]
    if action == "status":
        if options:
            raise ValueError("status accepts no options")
        load_run_state(root, work_id)
        return f".engineering-method/runs/{work_id}/state.json"
    if action == "recover":
        unknown = set(options) - {"--live-agents"}
        if unknown:
            raise ValueError("recover received unsupported options")
        if "--coordinator-only" in flags and "--live-agents" in options:
            raise ValueError("choose observation or coordinator-only recovery, not both")
        if "--live-agents" not in options and "--coordinator-only" not in flags:
            raise ValueError("recover requires --live-agents from an explicit host observation")
        live_agents = None if "--coordinator-only" in flags else _csv(options["--live-agents"], option="--live-agents")
        backlog = load_backlog(root / "BACKLOG.md")
        canonical_probe = (
            GitHubCanonicalProbe(
                gateway, _repository(gateway), project_key=backlog.project_key
            )
            if backlog.mode == "github-cache"
            else BacklogCanonicalProbe()
        )
        recovered = recover_run(
            root,
            work_id,
            git_probe=SubprocessGitProbe(),
            canonical_probe=canonical_probe,
            live_agent_ids=live_agents,
        )
        return recovered.next_action
    raise ValueError("unsupported continuity action")


def main(
    argv: list[str] | None = None,
    *,
    root: Path | None = None,
    gateway: IssueGateway | None = None,
    stdin: TextIO | None = None,
) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    project_root = Path.cwd() if root is None else Path(root)
    stream = sys.stdin if stdin is None else stdin
    try:
        help_text = _help_text(arguments)
        if help_text is not None:
            print(help_text)
            return 0
        if not arguments:
            raise ValueError("project-state command required")
        issue_gateway = gateway or GitHubIssuesGateway()
        command, remaining = arguments[0], arguments[1:]
        if command == "backlog":
            output = _backlog_command(remaining, root=project_root, gateway=issue_gateway)
        elif command == "feature":
            output = _feature_command(remaining, root=project_root)
        elif command == "continuity-state":
            output = _continuity_command(
                remaining, root=project_root, stream=stream, gateway=issue_gateway
            )
        elif command in {"backlog-to-issues", "refresh-issue-cache"}:
            output = _github_command(
                command, remaining, root=project_root, gateway=issue_gateway
            )
        else:
            raise ValueError("unsupported project-state command")
    except (ValueError, RuntimeError, OSError, TypeError, json.JSONDecodeError) as error:
        return _error(str(error))
    print(output)
    return 0
