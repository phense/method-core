# Orchestration Continuity Contract

Orchestration consumes the EM-002 state service; it does not define or write a
second state format. The installed `continuity-state` interface owns
`.engineering-method/runs/<work-id>/state.json`, `resume.md`, `decisions.md`,
`agent-reports/`, and `events.jsonl`.

```json
{
  "compaction_boundaries": ["before_dispatch", "active_agent", "completed_agent_before_integration", "failed_verification", "mid_fix", "post_slice", "pre_converge", "final_handoff"],
  "downstream_recall_allowed": ["work_id", "artifact_pointers"],
  "authority_on_conflict": "repository_evidence"
}
```

## Ownership

- The coordinator is the sole writer of `state.json`, `resume.md`, and
  `decisions.md`, and the sole event producer for orchestration transitions.
- A subagent writes only its named file below `agent-reports/` through the
  existing EM-002 report interface.
- Git, current artifacts, tests, and canonical backlog or issue state outrank a
  stale checkpoint or recalled memory value.

## Checkpoints

Use the existing EM-002 event and checkpoint operations before and after a
dispatch, after implementation, test, review, and fix transitions, before a
long wait, after each slice, at phase transitions, and before handoff. Record
the exact next action. Event success precedes the checkpoint that records its
result, except dispatch and completion protocols that deliberately bracket the
external action with two checkpoints.

## Recovery

Discover the run read-only before asking for host status. A verified absent run
may initialize with immutable `coordination_mode: coordinator-only` when no
delegation/status capability exists. Preserve this provenance across sequential
checkpoints and phase handoffs. `recover --coordinator-only` verifies complete
state with no agent identities, agent events, ambiguous agent metadata, or agent
reports; it never invents an empty observation. Existing ordinary or uncertain
runs require explicit host-observed live agent IDs and remain blocked without
them. Enrollment cannot retrofit an existing run, and required independent
review remains a real gate. See the supporting state skill's recovery gate.

Validate the recorded
worktree, commits, artifacts, reports, and canonical work before continuing.
Preserve completed slices, keep observed active agents active, and make only
unavailable active agents redispatchable. Downstream memory may provide the
work ID and artifact pointers, but cannot override repository evidence.

## Compaction boundary evidence

Recovery must be exercised from checkpoints representing all of these states:

- before dispatch, with a prepared brief as the exact next action;
- an active agent, preserving it when the host still observes it;
- a completed agent before integration, preserving completed work without
  redispatch;
- failed verification, retaining the failing check and diagnostic next action;
- mid-fix, retaining the finding, attempt evidence, and covering-test action;
- post-slice, preserving completion and advancing only to pending work;
- pre-converge, retaining as-built and integration evidence; and
- final handoff, retaining fresh verification and its exact handoff action.

At every boundary, validate git head/base evidence, artifact existence,
canonical status, live-agent observations, and the saved next action. Git or
canonical progress may safely advance stale state; conversation reconstruction
may not rewind it.

## Downstream recall boundary

An agentic-RAG or other memory adapter may return only the stable work ID and
artifact pointers needed to locate the run. Ignore recalled status, commits,
completed or active work, findings, verification results, and next actions.
Load those values from EM-002 state and then validate them against git,
artifacts, tests, and the canonical backlog or issue source.
