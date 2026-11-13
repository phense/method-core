# Claude adapter

Shared Method Core host mapping. Shared skills keep semantic names;
resolve them against this adapter in Claude Code. The conventional plugin-root
`skills/` directory is the same tree exposed by the Codex manifest.

```json
{
  "host": "claude",
  "verified_cli_version": "2.1.259",
  "coordinator": {"model": "fable", "effort": "medium"},
  "evaluation_roles": {"routing": "standard", "architectural": "strong"},
  "roles": {
    "strong": [{"model": "fable", "effort": "medium"}, {"model": "opus", "effort": "high"}],
    "standard": [{"model": "sonnet", "effort": "medium"}],
    "fast": [{"model": "haiku", "effort": "medium"}]
  },
  "operations": {
    "dispatch": "Agent tool when exposed by the current host",
    "follow_up": "Agent resume or message capability only when present in the live schema",
    "status": "host task status capability; CLI background sessions use claude agents",
    "wait": "host task completion notification or bounded status wait",
    "cancel": "host task cancellation capability; CLI background sessions use claude stop",
    "isolation": "Agent worktree capability when exposed; otherwise verified git worktree",
    "model_selection": "Agent model schema and observed availability; CLI --model and --effort",
    "sequential_fallback": "existing coordinator executes without claiming a model switch"
  }
}
```

## Capability resolution

Inspect the live `Agent` tool schema before using `model`, resume, background,
or worktree arguments. Claude CLI help is not proof that the Agent tool
accepts every CLI flag or alias. Inspect actual task status/wait/cancel tools;
if unavailable, use foreground serial dispatch and its returned completion
instead of inventing tools or observing an unrelated CLI background session.
For actual CLI background sessions, `claude agents`, `claude logs <id>`, and
`claude stop <id>` provide their own status, output, and cancellation. Never
substitute those IDs for Agent task IDs.

Aliases in the table are preferences. Use a full model ID only when it is
actually exposed or confirmed by the host; record the resolved model from
the response. Try candidates at most once and each lower role at most once;
record the rejected choices and selected role/model/effort. Authentication
failure is a blocker, not permission to switch providers. If the host cannot
select the requested child effort, do not claim it did: use an adequate
permitted coordinator or record the limitation. Never claim the main model
changed because a delegated task used another model.

The coordinator and all Fable assignments, including strong reviews, default
to medium. Higher Fable effort requires a recommendation and explicit
case-specific user approval. Opus uses high. A strong role alone does not
authorize increasing Fable effort.

Resume the same agent with the precise finding, prior evidence, and owned
paths when supported. Otherwise use a new bounded task carrying its report
and checkpoint, after confirming the original writer has stopped. Wait on
host completion notifications rather than repeated tool polling; bound waits
to 60 seconds when progress-update rules apply. A cancellation request alone
is not proof that writes have stopped.

## Isolation and continuity

Use native worktree isolation if the host exposes it; otherwise inspect
`git worktree list --porcelain` and `git status --short` and apply the shared
worktree skill. A background agent alone does not establish write isolation.
CLI `--worktree` exists, but should not create another worktree inside an
already isolated fixture. Keep each writer's paths and reports disjoint.

`${CLAUDE_PLUGIN_ROOT}` is available in supported plugin command contexts;
do not assume it is set in an arbitrary shell. Resolve shared skill links
from the installed SKILL.md directory, and run scripts from the target cwd.
Claude memory and CLAUDE.md are context, not the canonical checkpoint. Recover
state from repository evidence and actual host-observed live task IDs. Restart
the session after plugin installation/update; session-only `--plugin-dir`
loads the supplied directory without a global installation mutation.

## Verified CLI interfaces

Verified with `claude --help`, `claude plugin validate --help`, `claude plugin
marketplace add --help`, and `claude plugin install --help` at the stated
version. Commands describe interfaces, not completed live validation.

Set `method_name` to the installed consumer identity from
`.codex-plugin/plugin.json` (`engineering-method` or `writing-method`).

```sh
env CLAUDE_CONFIG_DIR="$em_claude_home" claude plugin validate "$em_package" --strict --json
env CLAUDE_CONFIG_DIR="$em_claude_home" claude plugin marketplace add "$em_package"
env CLAUDE_CONFIG_DIR="$em_claude_home" claude plugin install "${method_name}@${method_name}"
env CLAUDE_CONFIG_DIR="$em_claude_home" claude -p --plugin-dir "$em_package" --output-format stream-json --verbose --no-session-persistence --setting-sources "" --strict-mcp-config --permission-mode dontAsk --permission-prompts none --model fable --effort medium --max-budget-usd 1
```

Set cwd to a temporary fixture, bound the subprocess process group by wall
time, and capture stdout JSONL separately from stderr. Use fixture-specific
tool grants; denied required edits cause failure. Validate observed skill
invocations, artifact changes, and the terminal result; authentication errors,
timeouts, malformed output, and missing evidence cannot count as passes.

The behavioral driver stages a disposable plugin copy beside the fixture and
passes only that copy through `--plugin-dir` and `--add-dir`. The latter lets
native file tools follow the fixture's skill links without granting access to
the caller's source checkout. It uses `--permission-mode auto` so the native
permission classifier can assess bounded tool calls when `--permission-prompts
none` has no interactive approver. It never uses bypassPermissions and preserves
inherited safety-mode flags and managed restrictions. A denial remains failed
evidence. Source and staged-plugin fingerprints must remain unchanged.

Clean installs use temporary configuration homes without authentication. A
fresh home on the tested host reports not logged in. Authorized live runs may
retain the existing authenticated home, use isolated settings and the
session-only plugin path, and disable session persistence; disclose that this
does not isolate all caches, memory discovery, or host state. Do not copy,
read, or symlink credentials, mutate global settings, or substitute API keys.
A fully isolated live home requires human-controlled OAuth login.

Do not use `--bare`: it disables OAuth/keychain and requires API authentication.
Do not use `--safe-mode`: it disables plugins and skills. If using the separate
`claude plugin eval` feature, include `--no-publish`; report publication can
otherwise be enabled by default. The custom stream driver above does not use
that feature.

## Method integration

Both consuming methods bundle this same adapter and shared support. The invoking
method owns lifecycle selection and its method-specific policies. Read the
consumer's `shared/policies/lifecycle-selection.md` when present. For shared
support choose the invoking plugin's namespace; do not run duplicate copies or
start another method merely because it is installed. Core support does not
require either method's optional skills. Gemini-specific behavior is deferred
until a separate adapter has been verified.
