#!/usr/bin/env python3
"""Unscripted routing evaluations: plain requests, several plugins, no routing instruction.

The routing harness tells a host to select a workflow. This one sends the case
prompt exactly as written, with every given plugin loaded, and records which
skills the host loaded on its own. Expectations never enter prompts. A case is
repeated `--runs` times and reported as a count, because loading is statistical.

The host runs as its user runs it: with the adapter's coordinator model, and on
Codex with the plugins as they are installed in the given Codex home. An
installed copy whose skills differ from the source stops the run.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

try:
    from scripts import run_host_evals as harness
except ImportError:  # executed as a script: the scripts directory is on the path
    import run_host_evals as harness

ROOT = harness.ROOT
EvalFailure = harness.EvalFailure
READ_ONLY_TOOLS = "Read,Glob,Grep,Skill"


def bare(name):
    """`plugin:skill` and `skill` name the same skill here: several plugins are loaded."""
    return name.rsplit(":", 1)[-1] if isinstance(name, str) else ""


def events(text):
    found = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except ValueError as exc:
            raise EvalFailure("malformed_jsonl", text) from exc
        if isinstance(event, dict):
            found.append(event)
    return found


def loaded_skills(host, text, plugins):
    """Skills the host loaded through a successful tool call, in first-load order.

    A skill path that only appears inside some file's content is not a load.
    """
    order, terminal, pending = [], False, {}

    def add(names):
        for name in names:
            if name and name not in order:
                order.append(name)

    for event in events(text):
        kind = event.get("type")
        if host == "codex":
            if kind in ("error", "turn.failed"):
                raise EvalFailure("host_error", text)
            terminal |= kind == "turn.completed"
            item = event.get("item")
            if kind == "item.completed" and isinstance(item, dict) \
                    and item.get("type") == "command_execution" and item.get("exit_code") == 0:
                command, output = item.get("command"), item.get("aggregated_output", "")
                if isinstance(command, str) and isinstance(output, str):
                    for plugin in plugins:
                        add(sorted(harness.observed_read_skills(command, output, plugin)))
            continue
        if kind == "result":
            if event.get("is_error") or event.get("subtype") != "success":
                raise EvalFailure("host_error", text)
            terminal = True
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and isinstance(block.get("id"), str):
                pending[block["id"]] = block
            if block.get("type") == "tool_result" and not block.get("is_error") and block.get("content"):
                call = pending.get(block.get("tool_use_id"), {})
                arguments = call.get("input") if isinstance(call.get("input"), dict) else {}
                if call.get("name") == "Skill":
                    add([bare(arguments.get("skill"))])
                if call.get("name") == "Read":
                    add(harness.SKILL_PATH.findall(str(arguments.get("file_path", ""))))
                if call.get("name") == "Bash":
                    output = block["content"]
                    if isinstance(output, list):
                        output = "\n".join(str(part.get("text", "")) for part in output if isinstance(part, dict))
                    for plugin in plugins:
                        add(sorted(harness.observed_read_skills(str(arguments.get("command", "")), str(output), plugin)))
    if not terminal:
        raise EvalFailure("incomplete_transcript", text)
    return order


def judge(loaded, expected):
    """A run hits when an expected skill was loaded and no prohibited one was."""
    if set(loaded) & set(expected.get("prohibited", [])):
        return False
    wanted = expected.get("any", [])
    return bool(set(loaded) & set(wanted)) if wanted else not loaded


def skills_fingerprint(plugin):
    """Content of every skill file of a plugin, independent of where the plugin lies."""
    return harness.fingerprint(plugin / "skills")


def plugin_name(plugin):
    manifest = plugin / ".codex-plugin/plugin.json"
    return json.loads(manifest.read_text())["name"] if manifest.is_file() else plugin.name


def installed_codex_plugins(sources, codex_home):
    """The installed copy of each source plugin; its skills must equal the source."""
    found = []
    for source in sources:
        name, wanted = plugin_name(source), skills_fingerprint(source)
        copies = [path for path in sorted((codex_home / "plugins/cache").glob(f"*/{name}/*"))
                  if (path / "skills").is_dir()]
        match = [path for path in copies if skills_fingerprint(path) == wanted]
        if not match:
            raise EvalFailure(("installed_plugin_differs:" if copies else "plugin_not_installed:") + name)
        found.append(match[-1])
    return found


def prepare_repo(repo, case):
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    for relative, content in case.get("files", {}).items():
        path = (repo / relative).resolve()
        if not path.is_relative_to(repo.resolve()):
            raise EvalFailure("fixture_path_escape")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)


def host_command(host, repo, plugins, config, model, effort, prompt, auth_home=None, native_auth=False, budget=2):
    env = os.environ.copy()
    for key in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDECODE", "ANTHROPIC_AUTH_TOKEN"):
        env.pop(key, None)
    if host == "codex":
        # The user's own Codex home: plugins load the way they are installed, not through repository links.
        env["CODEX_HOME"] = str(auth_home)
        command = ["codex", "exec", "--json", "--ephemeral",
                   "--sandbox", "read-only", "-C", str(repo), "-m", model]
        if effort is not None:
            command.extend(["-c", f'model_reasoning_effort="{effort}"'])
    else:
        if not native_auth:
            env["CLAUDE_CONFIG_DIR"] = str(auth_home or config)
        settings = config / "settings.json"
        settings.write_text(json.dumps({"disableAllHooks": True, "enableAllProjectMcpServers": False}))
        command = ["claude", "-p", "--verbose", "--output-format", "stream-json",
                   "--no-session-persistence", "--setting-sources", "", "--settings", str(settings),
                   "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
        for plugin in plugins:
            command.extend(["--plugin-dir", str(plugin)])
        command.extend(["--model", model, "--allowedTools", READ_ONLY_TOOLS,
                        "--max-budget-usd", str(budget), "--no-chrome"])
        if effort is not None:
            command.extend(["--effort", effort])
    command.append(prompt)
    return command, env


def run_once(host, case, output, label, timeout, sources, auth_home=None, model=None, native_auth=False):
    with tempfile.TemporaryDirectory(prefix="method-natural-eval-") as directory:
        temporary = Path(directory)
        repo, config = temporary / "repo", temporary / "config"
        config.mkdir()
        if host == "codex":
            staged = installed_codex_plugins(sources, Path(auth_home))
        else:
            staged = [harness.stage_plugin(source, temporary / f"plugin-{index}")
                      for index, source in enumerate(sources)]
        prepare_repo(repo, case)
        coordinator = harness.model_policy(host, sources[0])["coordinator"]
        effort = coordinator["effort"] if model in (None, coordinator["model"]) \
            else harness.model_effort(host, model, sources[0])
        model = model or coordinator["model"]
        command, env = host_command(host, repo, staged, config, model, effort, case["prompt"],
                                    auth_home, native_auth)
        stdout = ""
        try:
            stdout = harness.execute(command, repo, env, timeout)
            return loaded_skills(host, stdout, staged), model
        except EvalFailure as exc:
            stdout = exc.transcript or stdout
            raise
        finally:
            harness.private_transcript(output / f"{label}-raw.jsonl", stdout)


def run_case(host, case, expected, output, runs, min_hits, timeout, sources, **options):
    before = [harness.fingerprint(source) for source in sources]
    observations, hits, model = [], 0, None
    for index in range(1, runs + 1):
        try:
            loaded, model = run_once(host, case, output, f'{case["id"]}-{index}', timeout, sources, **options)
            hit = judge(loaded, expected)
            observations.append({"run": index, "loaded": loaded, "hit": hit})
            hits += hit
        except (EvalFailure, OSError, ValueError) as exc:
            observations.append({"run": index, "hit": False,
                                 "failure": str(exc) if isinstance(exc, EvalFailure) else type(exc).__name__})
    changed = before != [harness.fingerprint(source) for source in sources]
    result = {"case_id": case["id"], "host": host, "model": model, "runs": runs, "hits": hits,
              "expected_any": expected.get("any", []), "prohibited": expected.get("prohibited", []),
              "observations": observations,
              "status": "passed" if hits >= min_hits and not changed else "failed"}
    if changed:
        result["failure"] = "plugin_changed_during_evaluation"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, choices=["codex", "claude"])
    parser.add_argument("--case")
    parser.add_argument("--runs", type=int, default=1, help="repetitions per case")
    parser.add_argument("--min-hits", type=int, help="hits a case needs to pass; default: every run")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=420, help="maximum seconds per run")
    auth = parser.add_mutually_exclusive_group()
    auth.add_argument("--auth-home", type=Path)
    auth.add_argument("--native-auth", action="store_true",
                      help="Claude only: preserve the calling terminal native authentication environment")
    parser.add_argument("--model", help="default: the coordinator model of the host adapter")
    parser.add_argument("--plugin-root", type=Path, default=ROOT,
                        help="plugin whose evals/natural cases are run")
    parser.add_argument("--with-plugin", type=Path, action="append", default=[],
                        help="another plugin root to load beside it; repeatable")
    args = parser.parse_args(argv)
    if args.native_auth and args.host != "claude":
        parser.error("--native-auth is supported only for Claude")
    if args.host == "codex" and args.auth_home is None:
        parser.error("Codex needs --auth-home: the Codex home in which the plugins are installed")
    if args.runs < 1:
        parser.error("--runs must be at least 1")
    min_hits = args.runs if args.min_hits is None else args.min_hits
    if not 0 <= min_hits <= args.runs:
        parser.error("--min-hits must lie between 0 and --runs")
    sources = [args.plugin_root.resolve(), *[path.resolve() for path in args.with_plugin]]
    for source in sources:
        if not (source / "skills").is_dir():
            parser.error(f"not a plugin root: {source}")
    output = args.output_dir.resolve()
    if any(output.is_relative_to(source) for source in sources):
        parser.error("output must not be written into a plugin source")
    natural = sources[0] / "evals/natural"
    expected_file = natural / "expected.json"
    cases = [json.loads(path.read_text()) for path in sorted((natural / "cases").glob("*.json"))]
    if args.case:
        cases = [case for case in cases if case["id"] == args.case]
    if not cases or not expected_file.is_file():
        parser.error("no natural evaluation cases selected")
    expected = json.loads(expected_file.read_text())
    if args.host == "codex":
        try:
            installed_codex_plugins(sources, args.auth_home)
        except EvalFailure as exc:
            parser.error(f"{exc}: reinstall the plugin in that Codex home, then run again")
    output.mkdir(parents=True, exist_ok=True)
    os.chmod(output, 0o700)
    results = []
    for case in cases:
        result = run_case(args.host, case, expected[case["id"]], output, args.runs, min_hits, args.timeout,
                          sources, auth_home=args.auth_home, model=args.model, native_auth=args.native_auth)
        results.append(result)
        (output / f'{case["id"]}.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(json.dumps({key: result[key] for key in ("case_id", "status", "hits", "runs")}
                         | {"loaded": [o.get("loaded", o.get("failure")) for o in result["observations"]]},
                         ensure_ascii=False), flush=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=sources[0], capture_output=True, text=True)
    summary = {"status": "passed" if all(r["status"] == "passed" for r in results) else "failed",
               "host": args.host, "native_auth": args.native_auth, "runs": args.runs, "min_hits": min_hits,
               "source_commit": commit.stdout.strip(),
               "plugins": [{"root": source.name, "sha256": harness.fingerprint(source)} for source in sources],
               "completed_at": datetime.now(timezone.utc).isoformat(),
               "hits": sum(r["hits"] for r in results), "total_runs": args.runs * len(results), "results": results}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
