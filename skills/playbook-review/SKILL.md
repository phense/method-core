---
name: playbook-review
description: "Review a drafted or changed playbook for a development or publishing operation, or a recurring-use deliverable against its scenario and acceptance requirements. Check decisions, executable steps, failure paths and evidence freshness without hidden context. Not for authoring fixes, general code review, or executing the procedure."
---

# Playbook Review

Apply [proportionality](../../shared/policies/proportionality.md) and the
[playbook policy](../../shared/policies/playbooks.md). Review as a capable reader
or agent who has no author-specific background. Retain the owning lifecycle.

## Consumes

Read the playbook, its source requirement/risk and acceptance criteria, linked
system/interface evidence and any earlier findings or rehearsal records. Name
the exact artifact and system revision under review. Verify references through
authorized read-only inspection; do not invent operational facts or execute steps.

## Review checks

- Is the scenario applicable, with clear use/exclusion conditions and a bounded
  target? Is the operation-readiness or delivery obligation satisfied?
- Can the intended reader verify prerequisites, obtain inputs and identify the
  correct environment with the documented access and tools?
- Does each decision name an observable condition and an explicit next action?
  Are normal completion, failure and stop paths reachable without guessing?
- Does each action identify its target and expected evidence? Flag vague actions
  such as checking logs or restarting a service without the required specifics.
- Are risky actions scoped, consistent with existing authority, and preceded by
  rollback/abort conditions or an explicit irreversible boundary and alternative?
- Can an interrupted operation resume without duplicating non-idempotent effects?
- Are ownership, escalation conditions and the evidence to preserve actionable?
  Require only tools, dashboards and contacts actually needed by this scenario.
- Are facts sourced, secrets absent and placeholders either declared inputs or
  clearly unresolved blockers? Templates may intentionally retain placeholders;
  a deployment-ready artifact cannot hide missing facts behind them.
- Are review and rehearsal records current for relevant procedure/system changes?
  Separate expected outputs from observed results and enumerate untested branches.
  Missing access limits the review; it is a blocker when required claims cannot
  be verified, not an automatic demand for a connector the project does not use.

## Produces

Write a separate report using the [review/evidence template](../../templates/playbooks/review.md).
Give stable finding IDs, severity, quoted/path evidence and the required change.
Critical or Important means a correctness, authority, recovery, required evidence
or acceptance gap; Minor means a nonblocking improvement. Report content-review
verdict `Ready` only with no open Critical or Important findings. Otherwise use
`Changes required` or `Blocked` and return findings to `playbook-authoring` through
the owner. Do not edit the procedure as its reviewer.

Report rehearsal status independently: not run, passed, failed or stale, with
method and limits. A Ready content review never certifies practical execution.
Delivery/operation readiness additionally requires every agreed validation
criterion; an untested required branch remains open even with a Ready review.
Never turn a missing test into a pass or set last-validated from the review date.

## Independence and handoff

Follow the existing [review-depth contract](../requesting-code-review/SKILL.md):
risky or integration-bearing acceptance needs an independent reviewer; bounded
low-risk work may use a disclosed coordinator review. Record the actual reviewer
and method. If required independence is unavailable, report the blocker.

Return report paths and findings to the invoking executor or acceptance gate.
The coordinator retains task state and `project-backlog` continuity. Any rehearsal
is separate authorized work; this skill performs no mutations to the live system.
