# OpenCode adapter

Engineering Method is active through OpenCode's native skill tool. Its shared
skills retain their original names and descriptions. Load the applicable skill
on demand; preserve small-change proportionality. This adapter supplies host
semantics, not a central methodology router.

## Installation and resource resolution

The source-linked loader adds the package's absolute skills directory and this
adapter to the in-memory OpenCode configuration. Resolve every relative resource
link from the actual SKILL.md directory supplied by the skill tool. Run bundled
Python scripts from the user's target project directory, not the plugin checkout.
The checkout or extracted package must remain at its installation path. Updating
that source becomes effective after the OpenCode helper restarts.

OpenCode 1.18.30 discovery was verified; permissions may hide individual skills.
Same-name skills in other skill paths can collide. Use native discovery to verify
origins rather than assuming a namespaced Claude/Codex plugin name exists here.
Do not disable another package or broaden permissions automatically.

## Capability resolution

Use only tools and fields exposed in the current session. OpenCode documents a
native skill tool and task-based subagents. T3's OpenCode connection can expose a
different subset than the standalone CLI. CLI flags do not establish tool schema
support. In particular, do not invent Agent, collaboration, status, cancellation,
worktree, background, or resume APIs.

- Dispatch: use the native task tool only if present and its permissions allow it.
  Pass a bounded assignment, owned paths and required evidence. Select only an
  actually available agent type.
- Follow-up: use the returned task identifier only if the live task schema
  documents resumption. Do not substitute a thread, message or CLI session ID.
- Status and wait: a synchronous returned result proves that invocation completed.
  It is not a global inventory of active agents. Use asynchronous status/wait only
  if the host exposes it.
- Cancel: request cancellation only through an exposed capability and confirm the
  writer stopped before assigning its paths elsewhere.
- Isolation: a subagent is not an isolated worktree. Verify Git worktree ownership
  and disjoint writes before concurrent implementation; otherwise work serially.
- Independent review: a coordinator rereading its own patch is not independent.
  Use a separate available reviewer invocation when required, or record a blocker.

When required delegation/status capabilities are missing, follow the existing
project-backlog recovery contract. New-run coordinator-only enrollment requires
verified absent state and the documented missing host capability. Existing
ordinary runs cannot be relabeled coordinator-only to evade recovery checks.
Do not fabricate an empty live-agent inventory.

## Models and effort

The plugin does not override the user's model, variants, agent definitions or API
provider. strong, standard and fast are task responsibility roles, not a claim
that this host has three different quality tiers. Record the actual model and
effort if observable; otherwise record the limitation.

For the current direct DeepSeek setup, deepseek/deepseek-flash is the selected
baseline and deepseek/deepseek-v4-pro is a separately available comparison model.
This is not an assertion that Pro is stronger. Resolve availability at runtime.
Both can fill a role only when adequate for that task; if evidence is insufficient,
record it instead of silently upgrading, lowering quality or changing providers.

OpenCode custom agents can specify a model; otherwise subagents may inherit the
primary model. The task tool does not thereby gain an arbitrary model parameter.
The UI or CLI may select a main model for a new invocation. Never claim the current
main model changed because a child used another model. Respect explicit user
effort/budget limits. A higher reasoning setting alone does not prove actual
reasoning activation or quality.

No automatic best-model router, fallback between paid providers, or LiteLLM
configuration is installed by this integration.

## Continuity and memory

Workflow artifacts and explicit checkpoints remain canonical. This loader does
not implement session-start, prompt-recall, transcript ingestion or compaction
hooks. Native OpenCode compaction is not proof of Engineering Method checkpoint
recovery. Follow the shared recovery checks in new and resumed sessions.

agentic-rag remains separate. An existing read-only MCP server can be used when
needed and permitted, but this plugin neither configures it nor grants write
access. Never read or copy credential files to another host or provider.

## Method integration

Both consuming methods bundle this same adapter and shared support. The invoking
method owns lifecycle selection and its method-specific policies. Read the
consumer's `shared/policies/lifecycle-selection.md` when present. For shared
support choose the invoking plugin's namespace; do not run duplicate copies or
start another method merely because it is installed. Core support does not
require either method's optional skills. Gemini-specific behavior is deferred
until a separate adapter has been verified.
