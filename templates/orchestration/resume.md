# Orchestration Resume

```json
{
  "purpose": "recovery",
  "required": ["work_id", "phase", "current_slice", "completed_work", "active_work", "pending_work", "artifact_pointers", "agent_identities", "open_findings", "last_verification", "next_action"]
}
```

## Validated position

Record the work ID, lifecycle phase, current slice, completed/active/pending
work, current commit, and the repository or remote evidence used to validate
them. Reference large artifacts by path and commit rather than copying them.

## Agents and findings

Record observed active and completed agent identities, unavailable agents that
may be redispatched, report paths, and open evidence-backed findings.

## Verification and next action

Record the latest successful command, timestamp, output digest, and exactly one
next action. Recalled memory values are pointers only until revalidated.
