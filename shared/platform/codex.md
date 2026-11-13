# Codex adapter

Shared Method Core host mapping. Shared skills keep semantic names;
resolve those names against this adapter when executing in Codex. Both host
manifests expose the same plugin-root `skills/` tree.

## Contents

- Host mapping (the JSON block below)
- Capability resolution
- Isolation and continuity
- Verified CLI interfaces
- Method integration

```json
{
  "host": "codex",
  "verified_cli_version": "0.153.0",
  "coordinator": {"model": "gpt-6-astra", "effort": "medium"},
  "evaluation_roles": {"routing": "fast", "architectural": "strong"},
  "roles": {
    "strong": [{"model": "gpt-6-astra", "effort": "medium"}, {"model": "gpt-5.6-sol", "effort": "high"}],
    "standard": [{"model": "gpt-5.6-terra", "effort": "medium"}],
    "fast": [{"model": "gpt-5.6-luna", "effort": "medium"}]
  },
  "operations": {
    "dispatch": "collaboration.spawn_agent",
    "follow_up": "collaboration.followup_task or collaboration.send_message for a running agent",
    "status": "collaboration.list_agents",
    "wait": "collaboration.wait_agent",
    "cancel": "collaboration.interrupt_agent",
    "isolation": "host-owned workspace first; verified git worktree fallback",
    "model_selection": "actual spawn tool model and reasoning-effort allowlist",
    "sequential_fallback": "existing coordinator executes without claiming a model switch"
  }
}
```

## Capability resolution

Inspect the actual tools and argument schemas exposed by the current host.
Do not assume a CLI subprocess has the enclosing session's collaboration
tools. Read the spawn allowlist and concurrency limit before dispatch. Pass
`task_name`, a bounded `message`, `model`, and `reasoning_effort` only when the
actual schema permits them. With this host's schema a model override requires
`fork_turns: "none"` or a bounded positive turn count; an all-history fork
inherits the parent. Supply explicit file-backed context for isolated agents.

The table is preference configuration, not proof of account availability.
Try each available candidate at most once, then the next lower role at most
once. Record rejected candidates and actual selected model/effort in the
dispatch checkpoint and report. Stop retrying on an authentication failure;
record a blocker. If no suitable permitted candidate or dispatch capability
exists, execute sequentially in the existing coordinator, or record why the
required independent review cannot proceed. Never claim that the main model
changed because a child used another model.

The coordinator and all Astra assignments, including strong reviews, default
to medium. Higher Astra effort requires a recommendation and explicit
case-specific user approval. Sol uses high. A task's strong role does not
silently authorize raising Astra effort.

Observe live IDs before recovery. `list_agents` supplies status;
`followup_task` resumes an idle agent with its fix brief, while `send_message`
delivers context to a running agent without starting a new turn. Wait using
`wait_agent` rather than polling shell sleeps; keep individual waits within
60 seconds when communication rules require regular updates. Interruption
does not prove an agent has stopped writing: observe status again before
reassigning ownership or integrating its files.

## Isolation and continuity

Inspect `git rev-parse --show-toplevel`, `git rev-parse --git-common-dir`,
`git worktree list --porcelain`, and `git status --short` in the target.
Use an already isolated host workspace when available. Otherwise follow the
shared worktree skill and verify disjoint write ownership before parallel
implementation. A spawn alone does not establish filesystem isolation.

Resolve bundled references relative to the installed SKILL.md, then invoke
scripts with the target repository as cwd. Native Codex memory is optional
context; recover from current repository artifacts and the EM-002 checkpoint.
Never use remembered agent IDs as current host observations. Installed plugin
changes require a new session to demonstrate discovery of the new files.

## Verified CLI interfaces

Verified locally with `codex exec --help`, `codex plugin marketplace add
--help`, `codex plugin add --help`, and `codex plugin list --help`.
The following are command shapes, not claims of successful live evaluation.
Variables denote absolute paths supplied by the caller.

Set `method_name` to the installed consumer identity from
`.codex-plugin/plugin.json` (`engineering-method` or `writing-method`).

```sh
env CODEX_HOME="$em_codex_home" codex plugin marketplace add "$em_package" --json
env CODEX_HOME="$em_codex_home" codex plugin add "${method_name}@${method_name}" --json
env CODEX_HOME="$em_codex_home" codex plugin list --marketplace "$method_name" --json
env CODEX_HOME="$em_codex_home" codex exec -C "$em_fixture" --ephemeral --json --sandbox workspace-write -m gpt-6-astra -c 'model_reasoning_effort="medium"' -o "$em_output/final.txt" -
```

Use a subprocess process-group timeout and retain stdout JSONL plus stderr
separately. Validate terminal completion and actual skill/file evidence;
nonzero exits, malformed events, timeout, missing commands, authentication
failure, or missing evidence are failures. `--ephemeral` disables persisted
session files, not every cache or log write. `--ignore-user-config` suppresses
user config but authentication still uses CODEX_HOME; it can also suppress
installed-plugin configuration, so do not combine it blindly with discovery.

Clean-install checks use temporary configuration homes without credentials.
On the tested host a fresh home reports not logged in. Live evaluations can
use the existing authenticated home with isolated invocation settings and
ephemeral mode when explicitly authorized; that is not a temporary-home auth
test. Never copy, read, or symlink credentials for isolation, and never mutate
global plugin settings. A fully isolated live home needs human-controlled
login. Preserve account authentication and never fall back to an API key.

## Method integration

Both consuming methods bundle this same adapter and shared support. The invoking
method owns lifecycle selection and its method-specific policies. Read the
consumer's `shared/policies/lifecycle-selection.md` when present. For shared
support choose the invoking plugin's namespace; do not run duplicate copies or
start another method merely because it is installed. Core support does not
require either method's optional skills. Gemini-specific behavior is deferred
until a separate adapter has been verified.
