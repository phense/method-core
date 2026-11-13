#!/usr/bin/env python3
"""Isolated, fail-closed CLI behavioral evaluations; expectations never enter prompts."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
AUTH_ERROR = re.compile(r"not logged in|authentication (?:required|failed)|please (?:log ?in|sign in)|oauth.*(?:expired|failed)|invalid api key", re.I)
SKILL_PATH = re.compile(r"(?:^|[/\\\s])skills[/\\]([a-z][a-z0-9-]+)[/\\]SKILL\.md")
DECISION_SCHEMA = {"type": "object", "properties": {"primary": {"type": "string"},
                   "supporting": {"type": "array", "items": {"type": "string"}}},
                   "required": ["primary", "supporting"], "additionalProperties": False}

def private_transcript(path, text):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(text)
    os.chmod(path, 0o600)

def normalize_skill(name, plugin=ROOT):
    manifest = plugin / ".codex-plugin/plugin.json"
    identity = json.loads(manifest.read_text())["name"] if manifest.is_file() else "engineering-method"
    prefix = identity + ":"
    if isinstance(name, str) and name.startswith(prefix):
        return name[len(prefix):]
    if isinstance(name, str) and ":" in name:
        raise EvalFailure("unexpected_skill_namespace")
    return name


def model_policy(host, plugin=ROOT):
    text = (plugin / f"shared/platform/{host}.md").read_text()
    policy = json.loads(re.search(r"```json\n(.*?)\n```", text, re.DOTALL).group(1))
    model = os.environ.get("EM_EVAL_" + host.upper() + "_MODEL")
    effort = os.environ.get("EM_EVAL_" + host.upper() + "_EFFORT")
    if model or effort:
        if not model or not re.fullmatch(r"[a-zA-Z0-9_.-]+", model) or effort not in {"low", "medium", "high"}:
            raise EvalFailure("invalid_explicit_evaluation_model_override")
        choice = {"model": model, "effort": effort}
        policy["coordinator"] = choice.copy()
        policy["roles"] = {role: [choice.copy()] for role in policy["roles"]}
    return policy

def model_effort(host, model, plugin=ROOT):
    for choices in model_policy(host, plugin)["roles"].values():
        for choice in choices:
            if choice["model"] == model:
                return choice["effort"]
    return None

class EvalFailure(RuntimeError):
    def __init__(self, message, transcript=""):
        super().__init__(message)
        self.transcript = transcript

def failure_category(text):
    """Allowlisted diagnostics keep native error context without copying secrets."""
    if AUTH_ERROR.search(text):
        return "authentication"
    patterns = (
        (r"unknown (?:option|argument)|unrecognized (?:option|argument)", "unsupported_cli_option"),
        (r"invalid.*mcp|mcp.*invalid|mcp.*parse", "invalid_mcp_configuration"),
        (r"permission.prompt|permission-prompts", "permission_prompt_configuration"),
        (r"stream-json.*verbose|verbose.*stream-json", "stream_json_requires_verbose"),
        (r"cannot be launched inside|nested.*session", "nested_host_session"),
        (r"operation not permitted|permission denied|eacces|sandbox", "host_permission_denied"),
        (r"keychain", "native_keychain_failure"),
        (r"enotfound|econnrefused|connection|network|fetch failed|dns", "network_failure"),
        (r"model.*(?:unavailable|not found|not supported|does not exist)", "model_unavailable"),
        (r"max.?budget|budget.*exceed", "budget_exceeded"),
    )
    for pattern, category in patterns:
        if re.search(pattern, text, re.I):
            return category
    return "uncategorized_native_error"

def diagnostic_events(text):
    """Keep event structure and skill names; never persist arbitrary host text."""
    records = []
    allowed = {path.name for path in (ROOT / "skills").iterdir() if path.is_dir()} | {"native-focused-edit"}
    for line in text.splitlines():
        try:
            event = json.loads(line)
            if not isinstance(event, dict):
                raise ValueError()
        except ValueError:
            records.append({"type": "malformed", "bytes": len(line.encode())})
            continue
        item = event.get("item", {})
        malformed_item = not isinstance(item, dict)
        if malformed_item:
            item = {}
        records.append({"type": event.get("type"), "subtype": event.get("subtype"),
                        "item_type": item.get("type"), "exit_code": item.get("exit_code"),
                        "is_error": event.get("is_error"), "malformed_item": malformed_item,
                        "skill_paths": sorted(set(SKILL_PATH.findall(json.dumps(event))))})
        final = item.get("text") if item.get("type") == "agent_message" else event.get("result")
        if isinstance(event.get("structured_output"), dict):
            final = json.dumps(event["structured_output"])
        if isinstance(final, str):
            try:
                decision = json.loads(re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", final))
                if isinstance(decision, dict):
                    primary = normalize_skill(decision.get("primary"))
                    supporting = decision.get("supporting", [])
                    if isinstance(supporting, list):
                        supporting = [normalize_skill(name) for name in supporting]
                    records[-1]["decision"] = {
                        "primary": primary if isinstance(primary, str) and primary in allowed else "unrecognized",
                        "supporting": [name if isinstance(name, str) and name in allowed else "unrecognized"
                                       for name in supporting] if isinstance(supporting, list) else ["malformed"],
                    }
            except (ValueError, TypeError, EvalFailure):
                pass
    return records

def native_failure_diagnostics(stdout, stderr):
    """Exclude successful tool reads and model prose from error classification."""
    diagnostics = [stderr]
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            # Native CLIs can emit a plain login failure even with exit code zero.
            diagnostics.append(line)
            continue
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        if kind in ("error", "turn.failed") or (
            kind == "result" and (event.get("is_error") is True
                                  or str(event.get("subtype", "")).startswith("error"))
        ):
            diagnostics.append(line)
    return "\n".join(diagnostics)


def execute(command, cwd, env, timeout):
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
    except FileNotFoundError as exc:
        raise EvalFailure("missing_command") from exc
    def cancel(signum, frame):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        # Termination must exit the wrapper, never advance a both-host loop.
        raise SystemExit(128 + signum)
    previous_term = signal.signal(signal.SIGTERM, cancel)
    try:
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
            raise EvalFailure("timeout", stdout) from exc
    finally:
        signal.signal(signal.SIGTERM, previous_term)
    diagnostics = native_failure_diagnostics(stdout, stderr)
    if AUTH_ERROR.search(diagnostics):
        raise EvalFailure("authentication", stdout)
    if process.returncode:
        raise EvalFailure(f"host_exit:{process.returncode}:" + failure_category(diagnostics), stdout)
    return stdout

def observed_read_skills(command, output, plugin):
    """Dynamic paths count only with an executed read and complete package content."""
    try:
        words = shlex.split(command)
        if len(words) == 3 and Path(words[0]).name in ("sh", "bash", "zsh") and words[1] in ("-c", "-lc"):
            command = words[2]
            words = shlex.split(command)
    except ValueError:
        return set()
    if not words or not output:
        return set()
    executable = Path(words[0]).name
    if executable == "realpath":
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
        statements, current = [], []
        for token in tokens:
            if token == ";":
                statements.append(current)
                current = []
            else:
                current.append(token)
        statements.append(current)
        if (len(statements) < 2 or len(statements[0]) != 2
                or statements[1] != ["cat", statements[0][1]]):
            return set()
        resolved, _, body = output.partition("\n")
        for path in (plugin / "skills").glob("*/SKILL.md"):
            suffix = f"skills/{path.parent.name}/SKILL.md"
            content = path.read_text()
            if (statements[0][1].endswith(suffix) and resolved.endswith("/" + suffix)
                    and content.strip() and body.startswith(content)):
                return {path.parent.name}
        return set()
    reads = executable in ("cat", "sed", "head") or (
        re.fullmatch(r"python(?:\d+(?:\.\d+)*)?", executable)
        and re.search(r"\.read_text\s*\(", command))
    if not reads:
        return set()
    found = set()
    for path in (plugin / "skills").glob("*/SKILL.md"):
        # Claude's Bash result removes terminal newlines, not instruction bytes.
        content = path.read_text().rstrip("\n")
        if content.strip() and content in output:
            found.add(path.parent.name)
    return found


def parse_transcript(host, text, plugin=ROOT):
    try:
        return _parse_transcript(host, text, plugin)
    except EvalFailure:
        raise
    except Exception as exc:
        # An unanticipated native shape is a failed evaluation, never evidence.
        raise EvalFailure("malformed_native_envelope:" + type(exc).__name__, text) from exc

def codex_native_events(text, *, thread_id, project):
    """Normalize host-owned rollout events; never decode encrypted assignments.

    Scope is confirmed by the completed child's own review_assignment field.
    The returned prompt is that attestation, not a reconstructed spawn argument.
    """
    try:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
        metadata = [r['payload'] for r in rows if r.get('type') == 'session_meta']
        if (len(metadata) != 1 or metadata[0].get('id') != thread_id
                or metadata[0].get('source') != 'exec'
                or Path(metadata[0]['cwd']).resolve() != project.resolve()):
            raise EvalFailure('native_session_mismatch')
        events, reviewers, children, completed = [], [], {}, set()
        tool_position = 0
        terminal = False
        for row in rows:
            payload = row.get('payload', {})
            if row.get('type') == 'event_msg':
                if payload.get('type') == 'task_complete':
                    terminal = True
                if payload.get('type') != 'item_completed':
                    continue
                if payload.get('thread_id') != thread_id:
                    raise EvalFailure('native_item_thread_mismatch')
                item = payload['item']
                kind = item['type']
                if kind == 'SubAgentActivity':
                    identity, author = item['agent_thread_id'], item['agent_path']
                    if (not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', identity)
                            or identity == thread_id or not re.fullmatch(r'/root/[a-z0-9_]+', author)):
                        raise EvalFailure('native_child_identity')
                    if item['kind'] == 'started':
                        if author in children:
                            raise EvalFailure('native_duplicate_child')
                        children[author] = identity
                    elif item['kind'] == 'completed':
                        if children.get(author) != identity or author in completed:
                            raise EvalFailure('native_unmatched_child_completion')
                        completed.add(author)
                    continue
                converted = None
                if kind == 'CommandExecution':
                    command = item['command']
                    if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
                        raise EvalFailure('native_command_shape')
                    converted = {'type': 'command_execution', 'command': shlex.join(command),
                                 'exit_code': item.get('exit_code'), 'aggregated_output': item.get('aggregated_output', '')}
                    tool_position += item.get('exit_code') == 0
                elif kind == 'CollabAgentToolCall':
                    # Preserve ordering, but only separately observed child answers are reviews.
                    converted = {'type': 'collab_tool_call', 'tool': item['tool'], 'status': item['status']}
                    tool_position += item['status'] == 'completed'
                elif kind == 'AgentMessage':
                    converted = {'type': 'agent_message', 'text': ''.join(
                        block['text'] for block in item.get('content', []) if block.get('type') == 'Text')}
                if converted is not None:
                    events.append({'type': 'item.completed', 'item': converted})
            elif row.get('type') == 'response_item' and payload.get('type') == 'agent_message':
                author = payload.get('author')
                if author not in completed or payload.get('recipient') != '/root':
                    continue
                blocks = payload.get('content', [])
                if any(block.get('type') != 'input_text' for block in blocks):
                    continue
                message = ''.join(block['text'] for block in blocks)
                prefix = f'Message Type: FINAL_ANSWER\nTask name: /root\nSender: {author}\nPayload:\n'
                if not message.startswith(prefix):
                    continue
                output = message[len(prefix):]
                match = re.search(r'```json\s*\n(.*?)\n```', output, re.DOTALL)
                try:
                    verdict = json.loads(match.group(1) if match else output)
                except ValueError:
                    continue
                assignment = verdict.get('review_assignment', '') if isinstance(verdict, dict) else ''
                if not isinstance(assignment, str):
                    raise EvalFailure('native_review_assignment_shape')
                if not ('review' in assignment.lower() and re.search(r'read[- ]only', assignment, re.I)):
                    assignment = ''
                reviewers.append({'id': children[author], 'prompt': assignment, 'output': output,
                                  'tool_position': tool_position, 'assignment_source': 'native-reviewer-response'})
                completed.remove(author)
        if not terminal:
            raise EvalFailure('native_incomplete_turn')
        events.append({'type': 'turn.completed'})
        return events, reviewers
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise EvalFailure('malformed_native_rollout') from error


def parse_codex_rollout(text, *, thread_id, project, plugin=ROOT):
    events, reviewers = codex_native_events(text, thread_id=thread_id, project=project)
    transcript = parse_transcript('codex', '\n'.join(map(json.dumps, events)), plugin)
    transcript['reviewers'] = reviewers
    return transcript


def capture_codex_rollout(stdout, *, auth_home, project, output, plugin=ROOT):
    """Read only the fresh exec thread identified by native stdout, never latest."""
    identities = [json.loads(line).get('thread_id') for line in stdout.splitlines()
                  if line.strip() and json.loads(line).get('type') == 'thread.started']
    if len(identities) != 1 or not isinstance(identities[0], str) or not re.fullmatch(
            r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', identities[0]):
        raise EvalFailure('native_thread_identity_missing')
    sessions = (auth_home / 'sessions').resolve()
    paths = list(sessions.glob('**/rollout-*-'+identities[0]+'.jsonl'))
    if len(paths) != 1 or paths[0].is_symlink() or not paths[0].resolve().is_relative_to(sessions):
        raise EvalFailure('native_rollout_missing_or_ambiguous')
    # Keep only evidence envelopes, never reasoning, system instructions or encrypted tool calls.
    selected = []
    for line in paths[0].read_text().splitlines():
        row = json.loads(line)
        kind, payload = row.get('type'), row.get('payload', {})
        if kind == 'session_meta':
            selected.append({'type': kind, 'payload': {key: payload.get(key) for key in ('id', 'cwd', 'source')}})
        elif kind == 'event_msg' and (payload.get('type') == 'task_complete' or (
                payload.get('type') == 'item_completed' and payload.get('item', {}).get('type')
                in ('CommandExecution', 'CollabAgentToolCall', 'AgentMessage', 'SubAgentActivity'))):
            selected.append(row)
        elif (kind == 'response_item' and payload.get('type') == 'agent_message'
              and payload.get('recipient') == '/root' and payload.get('author') != '/root'):
            selected.append(row)
    captured = '\n'.join(map(json.dumps, selected)) + '\n'
    private_transcript(output, captured)
    return parse_codex_rollout(captured, thread_id=identities[0], project=project, plugin=plugin)


def typed(value, expected, label):
    if not isinstance(value, expected):
        raise EvalFailure("malformed_" + label)
    return value

def _parse_transcript(host, text, plugin=ROOT):
    events, skills, tools, pending, reviewers = [], set(), [], {}, []
    invoked, review_assignments = set(), {}
    final, terminal = None, False
    try:
        for line in text.splitlines():
            if line.strip():
                event = json.loads(line)
                if not isinstance(event, dict):
                    raise ValueError("event must be object")
                events.append(event)
    except (ValueError, TypeError) as exc:
        raise EvalFailure("malformed_jsonl") from exc
    for event in events:
        typed(event.get("type"), str, "event_type")
        if host == "codex":
            if event.get("type") in ("error", "turn.failed"):
                raise EvalFailure("host_error")
            terminal |= event.get("type") == "turn.completed"
            item = event.get("item", {})
            if event.get("type") == "item.completed":
                typed(item, dict, "codex_item")
                typed(item.get("type"), str, "codex_item_type")
                if item.get("type") in ("collab_agent_tool_call", "collab_tool_call") and item.get("status") == "completed":
                    prompt = typed(item.get("prompt") or "", str, "collaboration_prompt")
                    operation = typed(item.get("tool", "unknown"), str, "collaboration_tool")
                    states = typed(item.get("agents_states", item.get("agent_states", {})) or {}, dict, "agent_states")
                    identities = typed(item.get("receiver_thread_ids") or [], list, "agent_identities")
                    tools.append({"name": "collaboration:" + operation, "input": prompt, "output": json.dumps(states)})
                    if "review" in prompt.lower() and re.search(r"read[- ]only", prompt, re.I):
                        for identity in identities:
                            typed(identity, str, "agent_identity")
                            review_assignments[identity] = prompt
                    for identity, state in states.items():
                        if identity in review_assignments and isinstance(state, dict) and state.get("status") == "completed" and state.get("message"):
                            typed(state["message"], str, "reviewer_response")
                            reviewers.append({"id": identity, "prompt": review_assignments[identity], "output": state["message"], "tool_position": len(tools)})
                if item.get("type") == "agent_message":
                    final = item.get("text")
                if item.get("type") == "mcp_tool_call" and item.get("status") == "completed":
                    tools.append({"name": "mcp:" + item.get("server", "unknown") + ":" + item.get("tool", "unknown"),
                                  "input": item.get("arguments", {}), "output": "completed"})
                if item.get("type") == "command_execution" and item.get("exit_code") == 0:
                    command = typed(item.get("command"), str, "command_input")
                    output = typed(item.get("aggregated_output", ""), str, "command_output")
                    tools.append({"name": "command", "input": command, "output": output})
                    # A cat/sed/read command must complete and actually return content.
                    skills.update(observed_read_skills(command, output, plugin))
        else:
            # Status/system events may carry plain message strings. Only the
            # assistant/user envelopes contain tool evidence.
            blocks = []
            if event["type"] in ("assistant", "user"):
                message = typed(event.get("message"), dict, "claude_message")
                content = message.get("content")
                if event["type"] == "user" and isinstance(content, str):
                    content = []  # Valid user text cannot prove a tool result.
                blocks = typed(content, list, "claude_content")
            for block in blocks:
                typed(block, dict, "claude_content_block")
                typed(block.get("type"), str, "claude_block_type")
                if block.get("type") == "tool_use":
                    identity = typed(block.get("id"), str, "tool_identity")
                    typed(block.get("name"), str, "tool_name")
                    arguments = typed(block.get("input"), dict, "tool_input")
                    for field in ("prompt", "file_path", "skill", "command"):
                        if field in arguments:
                            typed(arguments[field], str, "tool_input_" + field)
                    pending[identity] = block
                if block.get("type") == "tool_result" and not block.get("is_error"):
                    identity = typed(block.get("tool_use_id"), str, "tool_result_identity")
                    if identity not in pending:
                        raise EvalFailure("malformed_unmatched_tool_result")
                    call = pending[identity]
                    name, arguments = call.get("name", ""), call.get("input", {})
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        text_parts = []
                        for part in result_content:
                            typed(part, dict, "tool_result_block")
                            if "text" in part:
                                text_parts.append(typed(part["text"], str, "tool_result_text"))
                        result_content = "\n".join(text_parts)
                    typed(result_content, str, "tool_result_content")
                    tools.append({"name": name, "input": arguments, "output": result_content})
                    if name in ("Agent", "Task") and "review" in arguments.get("prompt", "").lower() and re.search(r"read[- ]only", arguments.get("prompt", ""), re.I):
                        reviewers.append({"id": block.get("tool_use_id"), "prompt": arguments["prompt"], "output": result_content, "tool_position": len(tools)})
                    if name == "Read" and block.get("content"):
                        skills.update(SKILL_PATH.findall(arguments.get("file_path", "")))
                    if name == "Skill" and block.get("content"):
                        selected_skill = normalize_skill(arguments.get("skill", ""), plugin)
                        skills.add(selected_skill)
                        invoked.add(selected_skill)
                    if name == "Bash" and block.get("content"):
                        command = arguments.get("command", "")
                        skills.update(observed_read_skills(command, result_content, plugin))
            if event.get("type") == "result":
                if event.get("is_error") or event.get("subtype") != "success":
                    raise EvalFailure("host_error")
                terminal, final = True, event.get("result")
                if isinstance(event.get("structured_output"), dict):
                    final = json.dumps(event["structured_output"])
    if not terminal or final is None:
        raise EvalFailure("incomplete_transcript")
    try:
        clean = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", final)
        decision = json.loads(clean)
        if not isinstance(decision, dict):
            raise ValueError("decision must be object")
    except (ValueError, TypeError) as exc:
        raise EvalFailure("malformed_decision") from exc
    decision["primary"] = normalize_skill(decision.get("primary"), plugin)
    if isinstance(decision.get("supporting"), list):
        decision["supporting"] = [normalize_skill(name, plugin) for name in decision["supporting"]]
    return {"decision": decision, "skills": sorted(skills), "invoked_skills": sorted(invoked), "tools": tools, "reviewers": reviewers, "event_count": len(events)}

def check_routing(transcript, expected, repo):
    if set(transcript.get("invoked_skills", [])) & set(expected["prohibited"]):
        raise EvalFailure("prohibited_skill_invoked")
    decision = transcript["decision"]
    supporting = decision.get("supporting")
    if decision.get("primary") != expected["primary"] or not isinstance(supporting, list):
        raise EvalFailure("unexpected_selection")
    selected = [decision["primary"], *supporting]
    if any(not isinstance(item, str) for item in selected) or len(selected) != len(set(selected)):
        raise EvalFailure("duplicate_controller")
    if not set(expected["supporting"]).issubset(supporting) or set(selected) & set(expected["prohibited"]):
        raise EvalFailure("unexpected_selection")
    required_reads = set(selected) - {"native-focused-edit"}
    if not required_reads.issubset(transcript["skills"]):
        raise EvalFailure("missing_skill_evidence")
    for relative in expected["artifacts"]:
        artifact = (repo / relative).resolve()
        if not artifact.is_relative_to(repo.resolve()) or not artifact.is_file() or not artifact.stat().st_size:
            raise EvalFailure("missing_artifact:" + relative)
    if "fallback" in expected:
        observed = json.loads((repo / "fallback.json").read_text())
        if any(observed.get(key) != value for key, value in expected["fallback"].items()):
            raise EvalFailure("incorrect_capability_fallback")
        for tool in transcript["tools"]:
            command = tool["input"] if isinstance(tool["input"], str) else tool["input"].get("command", "")
            if tool["name"] in ("Agent", "Task") or tool["name"].startswith(("collaboration:", "mcp:", "mcp__")) or re.search(r"\b(?:gh\s|git\s+push\b|git\s+worktree\s+(?:add|remove)\b)", command):
                raise EvalFailure("unavailable_capability_invoked")

def fingerprint(root):
    paths = [p for p in root.rglob("*") if p.is_file() and
             not any(part in {".git", ".engineering-method", ".superpowers", ".worktrees", "__pycache__"} for part in p.relative_to(root).parts)]
    data = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()

def retain_project(repo, destination):
    """Retain bounded generated artifacts for replay, including failed runs."""
    destination.mkdir(parents=True, exist_ok=True)
    total, count = 0, 0
    for path in sorted(repo.rglob("*")):
        relative = path.relative_to(repo)
        if any(part in {".git", ".agents", "__pycache__"} for part in relative.parts) or path.is_symlink() or not path.is_file():
            continue
        total += path.stat().st_size
        count += 1
        if total > 20_000_000 or count > 1000:
            raise EvalFailure("artifact_retention_limit")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        target.chmod(0o600)

def prepare_repo(repo, case, plugin):
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    for relative, content in case.get("files", {}).items():
        path = (repo / relative).resolve()
        if not path.is_relative_to(repo.resolve()):
            raise EvalFailure("fixture_path_escape")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    skills = repo / ".agents/skills"
    skills.mkdir(parents=True)
    for path in (plugin / "skills").iterdir():
        if path.is_dir():
            (skills / path.name).symlink_to(path.resolve(), target_is_directory=True)

def stage_plugin(plugin, destination):
    """Native tool grants cover a disposable copy, never the caller's sources."""
    shutil.copytree(plugin, destination, ignore=shutil.ignore_patterns(
        ".git", ".engineering-method", ".superpowers", ".worktrees", "__pycache__"))
    return destination

def host_command(host, repo, plugin, config, model, auth_home=None, prompt="", budget=2, native_auth=False):
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDECODE", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(key, None)
    effort = model_effort(host, model, plugin)
    if os.environ.get("EM_EVAL_" + host.upper() + "_MODEL"):
        prompt += (f"\nExplicit user override for this evaluation: coordinator and all subagents "
                   f"must use {model} at {effort} effort. This overrides adapter defaults and "
                   "earlier model/effort preferences in this task. Do not raise effort or substitute models.")
    if host == "codex":
        env["CODEX_HOME"] = str(auth_home or config)
        schema = config / "decision-schema.json"
        schema.write_text(json.dumps(DECISION_SCHEMA))
        command = ["codex", "exec", "--json", "--ephemeral", "--ignore-user-config",
                   "--sandbox", "workspace-write", "-C", str(repo),
                   "-m", model, "--output-schema", str(schema)]
        if effort is not None:
            command.extend(["-c", f'model_reasoning_effort="{effort}"'])
        command.append(prompt)
    else:
        if not native_auth:
            env["CLAUDE_CONFIG_DIR"] = str(auth_home or config)
        settings = config / "settings.json"
        settings.write_text(json.dumps({"disableAllHooks": True, "enableAllProjectMcpServers": False}))
        command = ["claude", "-p", "--verbose", "--output-format", "stream-json",
                   "--no-session-persistence", "--setting-sources", "", "--settings", str(settings),
                   "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}', "--plugin-dir", str(plugin),
                   "--add-dir", str(plugin), "--model", model, "--permission-mode", "auto",
                   "--permission-prompts", "none", "--max-budget-usd", str(budget), "--no-chrome",
                   "--json-schema", json.dumps(DECISION_SCHEMA)]
        if effort is not None:
            command.extend(["--effort", effort])
        command.append(prompt)
    return command, env

SKILL_DISCOVERY_INSTRUCTION = """
The shared skill files are linked directly at
.agents/skills/<skill-name>/SKILL.md in this repository. The method-qualified
invocation namespace is not an extra filesystem directory. Discover actual paths
with `rg --files --hidden --follow .agents/skills -g SKILL.md`, then read the
selected files. Ordinary searches without symlink following may miss these files;
an invented path or empty non-following search is not evidence of a missing skill.
Read each selected SKILL.md in a separate tool call containing only
`cat <skill-path>` (or the host's native Read tool), with complete output and a
successful exit. Keep discovery, path resolution and repository checks in other
calls so a later unrelated failure cannot invalidate the skill-read evidence.
Resolve each SKILL.md symlink to its actual target before following relative links
to supporting scripts or templates. Those links belong to the plugin containing
that target, not to the fixture's .agents directory. Inspect the resolved path
before declaring a bundled resource unavailable.
"""

ROUTING_INSTRUCTION = SKILL_DISCOVERY_INSTRUCTION + """
Assess the request and current repository using the available method
skills. Perform the first safe assessment step only; do not implement the entire
feature or launch subagents in this routing evaluation. Open the selected skill
instructions through tools before applying them. The assessment includes that
skill's required prerequisite and recovery preamble checks: follow its supporting
skill handoffs through read-only discovery to establish whether a run exists or
is absent and identify the prescribed next action. Do not initialize a run,
recover or mutate canonical state, or execute workflow tasks in this routing
assessment; record those next actions in decision.md instead. Do not
stop merely after choosing or reading the primary skill. This does not authorize
full lifecycle implementation or generating later-phase artifacts.
Write decision.md explaining the
one primary workflow and necessary supporting skills, using repository evidence.
Finish with ONLY a JSON object {"primary": "<skill-name or native-focused-edit>",
"supporting": ["<selected supporting skill names>"]}. Report the skills actually
applied, not every skill considered. Do not invent artifacts, live agents, or tests.
The supporting array lists only skills whose instructions were opened and applied
during this assessment. Mention future implementation or verification skills in
decision.md as next steps instead; exclude future-only skills from the final JSON.
"""
def run_case(host, case, expected, output, timeout, auth_home=None, model=None, plugin=ROOT, native_auth=False):
    source_sha256 = fingerprint(plugin)
    with tempfile.TemporaryDirectory(prefix="engineering-method-eval-") as directory:
        temporary = Path(directory)
        repo, config = temporary / "repo", temporary / "config"
        config.mkdir()
        staged_plugin = stage_plugin(plugin, temporary / "plugin")
        staged_sha256 = fingerprint(staged_plugin)
        prepare_repo(repo, case, staged_plugin)
        policy = model_policy(host, plugin)
        evaluation_kind = "architectural" if case.get("architectural") else "routing"
        evaluation_role = policy["evaluation_roles"][evaluation_kind]
        model = model or policy["roles"][evaluation_role][0]["model"]
        command, env = host_command(host, repo, staged_plugin, config, model, auth_home,
                                    case["prompt"] + "\n" + ROUTING_INSTRUCTION, native_auth=native_auth)
        stdout = ""
        try:
            stdout = execute(command, repo, env, timeout)
            private_transcript(output / f'{case["id"]}-raw.jsonl', stdout)
            retain_project(repo, output / case["id"] / "artifacts")
            transcript = parse_transcript(host, stdout, plugin=staged_plugin)
            check_routing(transcript, expected, repo)
            if fingerprint(plugin) != source_sha256 or fingerprint(staged_plugin) != staged_sha256:
                raise EvalFailure("plugin_changed_during_evaluation")
        except EvalFailure as exc:
            private_transcript(output / f'{case["id"]}-raw.jsonl', exc.transcript or stdout)
            retain_project(repo, output / case["id"] / "artifacts")
            (output / f'{case["id"]}-events.json').write_text(json.dumps(diagnostic_events(exc.transcript or stdout), indent=2) + "\n")
            raise
        retain_project(repo, output / case["id"] / "artifacts")
        private_transcript(output / f'{case["id"]}-raw.jsonl', stdout)
        (output / f'{case["id"]}-events.json').write_text(json.dumps(diagnostic_events(stdout), indent=2) + "\n")
        return {"case_id": case["id"], "status": "passed", "host": host, "model": model,
                "effort": model_effort(host, model, plugin), "source_sha256": source_sha256,
                "primary": transcript["decision"]["primary"], "skills": transcript["skills"],
                "tool_count": len(transcript["tools"]), "event_count": transcript["event_count"],
                "artifacts": {p: hashlib.sha256((repo / p).read_bytes()).hexdigest()
                              for p in expected["artifacts"]},
                "transcript_sha256": hashlib.sha256(stdout.encode()).hexdigest()}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=["codex", "claude"])
    parser.add_argument("--case")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=240,
                        help="maximum seconds per native routing assessment")
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument("--auth-home", type=Path)
    auth.add_argument("--native-auth", action="store_true",
                      help="Claude only: preserve the calling terminal native authentication environment")
    parser.add_argument("--model")
    parser.add_argument("--plugin-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    if args.native_auth and args.host != "claude":
        parser.error("--native-auth is supported only for Claude")
    output = args.output_dir.resolve()
    fixture = (ROOT / "tests/fixtures").resolve()
    if output.is_relative_to(ROOT.resolve()):
        parser.error("output must not overwrite fixture or plugin sources")
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    expected = json.loads((args.plugin_root / f"evals/{args.host}/expected.json").read_text())
    cases = [json.loads(path.read_text()) for path in sorted((args.plugin_root / "evals/shared/triggers").glob("*.json"))]
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
    if not cases:
        parser.error("no evaluation cases selected")
    results = []
    for case in cases:
        try:
            result = run_case(args.host, case, expected[case["id"]], output, args.timeout,
                              args.auth_home, args.model, args.plugin_root, native_auth=args.native_auth)
        except (EvalFailure, OSError, ValueError) as exc:
            result = {"case_id": case["id"], "host": args.host, "status": "failed",
                      "failure": str(exc) if isinstance(exc, EvalFailure) else type(exc).__name__}
        results.append(result)
        (output / f'{case["id"]}.json').write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result), flush=True)
        if result["status"] != "passed":
            break
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=args.plugin_root, capture_output=True, text=True)
    summary = {"status": "passed" if len(results) == len(cases) and all(r["status"] == "passed" for r in results) else "failed",
               "host": args.host, "native_auth": args.native_auth, "source_commit": commit.stdout.strip(),
               "source_sha256": fingerprint(args.plugin_root), "completed_at": datetime.now(timezone.utc).isoformat(),
               "requested_cases": len(cases), "results": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["status"] == "passed" else 1

if __name__ == "__main__":
    raise SystemExit(main())
