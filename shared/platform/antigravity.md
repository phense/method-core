# Antigravity adapter

Shared Method Core host mapping. Shared skills keep semantic names;
resolve them against this adapter when executing in Google Antigravity
(Antigravity CLI, Antigravity App, Antigravity IDE, and ACP hosts).
The `.antigravity-plugin/plugin.json` manifest exposes the same plugin-root
`skills/` tree used by the Claude and Codex manifests.

## Contents

- Host mapping (the JSON block below)
- Capability resolution
- Isolation and continuity
- Verified CLI interfaces
- Method integration

```json
{
  "host": "antigravity",
  "verified_cli_version": "1.5.14",
  "coordinator": {"model": "gemini-4-neon-medium", "effort": "medium"},
  "evaluation_roles": {"routing": "standard", "architectural": "strong"},
  "roles": {
    "strong": [
      {"model": "gemini-4-neon-high", "effort": "high"},
      {"model": "gemini-4-argon-high", "effort": "high"}
    ],
    "standard": [{"model": "gemini-4-argon-medium", "effort": "medium"}],
    "fast": [{"model": "gemini-3.8-flash-medium", "effort": "medium"}]
  },
  "operations": {
    "dispatch": "invoke_subagent (with define_subagent for custom roles) when exposed by the current host",
    "follow_up": "send_message to an existing subagent conversationId",
    "status": "manage_subagents action='list' for direct subagents; manage_task action='list' or 'status' for background commands",
    "wait": "reactive wakeup on subagent or background-task completion notifications without shell polling",
    "cancel": "manage_subagents action='kill' or 'kill_all' for subagents; manage_task action='kill' for background commands",
    "isolation": "invoke_subagent workspace='share' or 'branch' when exposed; otherwise verified git worktree",
    "model_selection": "invoke_subagent Model tier (inherit, pro, flash, flash_lite) or CLI --model and --effort",
    "sequential_fallback": "existing coordinator executes without claiming a model switch"
  }
}
```

## Capability resolution

Inspect the live tools exposed by the current Antigravity surface before
delegating. Standalone `agy`, Antigravity App, Antigravity IDE, and ACP hosts
may expose different tool sets or permission modes. CLI flags do not prove that
an embedded session exposes every subagent or orchestration tool.

- **Dispatch**: use `invoke_subagent` with a clear `Role`, `TypeName`, and
  bounded `Prompt` (defining a custom role with `define_subagent` only when
  built-in types such as `self` or `research` do not fit). For native
  subagents, map semantic roles onto the exposed `Model` enum (`pro` or
  `inherit` for `strong`, `inherit` or `flash` for `standard`, `flash` or
  `flash_lite` for `fast`).
- **Follow-up**: send follow-up instructions to a live subagent with
  `send_message` and its returned `conversationId` rather than launching a
  duplicate subagent for the same slice.
- **Status and wait**: use `manage_subagents` (`action='list'`) to inspect
  active direct subagents and `manage_task` for background shell commands.
  Rely on Antigravity's reactive wakeup (end the turn with no further tool
  calls while waiting) instead of shell `sleep` loops or repeated polling.
- **Cancel**: terminate unneeded subagents with `manage_subagents`
  (`action='kill'`) and verify the subagent has stopped before reassigning
  its files. Remember that killing a subagent with a `share` or `branch`
  workspace deletes that workspace; integrate or capture outputs first.

Model IDs in the JSON block are preferences verified against `agy models`, not
proof of account entitlement. Try each candidate at most once and each lower
role at most once; record rejected candidates and the resolved model/tier in
the dispatch checkpoint and report. Authentication failure is a blocker, not
permission to switch providers. The coordinator defaults to `medium` effort;
raising coordinator effort to `xhigh` or `max` requires a recommendation and
explicit case-specific user approval. Never claim the main model changed
because a delegated subagent used another model tier.

## Isolation and continuity

Prefer `invoke_subagent` with `workspace='share'` (shared git object store,
separate working copy) or `workspace='branch'` (isolated clone) when parallel
writers need separate checkouts. Default `workspace='inherit'` shares the
parent working tree and does not establish write isolation on its own. When
native workspace isolation is unavailable, inspect
`git worktree list --porcelain` and `git status --short` and apply the shared
worktree skill. Keep each writer's paths and reports disjoint.

Resolve bundled skill references relative to the installed `SKILL.md`
directory, and execute bundled Python scripts with the user's target
repository as the working directory. Installed plugins live as self-contained
copies under the active Antigravity configuration root:

- Standalone Antigravity CLI, App, and IDE: `~/.gemini/config/plugins/<name>`
- Custom or ACP host configurations (for example, hosts launching `agy acp`
  with `--gemini-dir`): `<config-dir>/plugins/<name>`

Workflow artifacts, `BACKLOG.md`, and `.engineering-method/runs/<work-id>/`
checkpoints remain canonical. Conversation compaction (`/compact`), `AGENTS.md`,
`GEMINI.md`, and optional external memory services are supplementary context,
not canonical state. Start a new Antigravity session after installing or
updating a plugin so the updated skill inventory is loaded.

## Verified CLI interfaces

Verified locally with `agy --version`, `agy --help`, `agy plugin --help`,
`agy plugin validate --help`, `agy plugin install`, `agy plugin list --json`,
and `agy models` at version `1.5.14`. Commands describe verified interfaces,
not live model routing claims.

```sh
agy plugin validate --strict "$em_package" --json
env HOME="$em_agy_home" agy plugin install "$em_package"
env HOME="$em_agy_home" agy plugin list --json
env HOME="$em_agy_home" agy plugin uninstall "$method_name"
```

For headless execution in a temporary fixture, `agy` supports print mode:

```sh
agy -p --output-format stream-json --model gemini-4-neon-medium --effort medium
```

Clean-install checks use an isolated temporary `HOME` without credentials so
global user configuration under `~/.gemini/config/` is never mutated. Never
copy, read, or symlink OAuth tokens or credential files for isolation.

For hosts that run `agy acp` with a separate `--gemini-dir`, install into that
host's `<gemini-dir>/config` directory with `scripts/install-antigravity`
passing `--config-dir`.

## Method integration

Both consuming methods bundle this same adapter and shared support. The
invoking method owns lifecycle selection and its method-specific policies.
Read the consumer's `shared/policies/lifecycle-selection.md` when present.
`engineering-method` and `writing-method` coexist cleanly in the same
Antigravity `plugins/` directory; for shared support skills, use the invoking
method's copy once rather than running duplicate copies. Core support does not
require either method's optional skills. Standalone Gemini CLI extensions
(`~/.gemini/extensions/`) remain separate and unverified.
