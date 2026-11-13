---
name: playbook-authoring
description: "Create or update a scenario-bound playbook for a development or publishing operation, or as a recurring-use deliverable, after its need is identified or on direct request. Use for decision paths, actions, recovery and verification. Not for generic documentation, task planning, playbook review, or executing the procedure."
---

# Playbook Authoring

Apply [proportionality](../../shared/policies/proportionality.md) and the
[playbook policy](../../shared/policies/playbooks.md). Support the existing
method owner; do not start a competing lifecycle.

## Trigger

A required operation or delivered playbook has an authoring task, an existing
procedure changed, review findings require corrections, or the user directly
requests a playbook. A planned operation or accepted future usage requirement
is sufficient origin evidence; do not wait for an incident.

## Consumes

Read the need decision, relevant spec/plan/tasks, intended reader or agent,
current interfaces/configuration, source evidence and any existing playbook and
review. Use only authorized read-only lookups for additional context. Sources
must identify the actual artifact and version, not recollection.

## Produces

Create or update the assigned canonical Markdown playbook using the
[template](../../templates/playbooks/playbook.md). Preserve stable IDs and
record origin, owner, class, target version and last-edited date. Keep review,
validation gaps and rehearsal results in the separate
[evidence record](../../templates/playbooks/review.md), linked from the playbook.
For a reusable template distinguish intentional parameters from missing facts.

## Workflow

1. Confirm scenario, applicability, class, readiness deadline and acceptance
   requirements from the owning artifacts. Reuse existing procedures and paths.
   For direct requests infer reasonable scope from evidence; ask only for missing
   facts that materially affect correctness. Unknown required facts block readiness.
2. Inspect actual commands, interfaces, permissions and dependencies. Never invent
   commands, owners, thresholds, expected outputs or successful test results.
   Label expected results as expectations; actual results belong in evidence.
3. Write preconditions the operator can check, when to use and not use the
   playbook, bounded inputs, and the initial read-only checks appropriate to the
   scenario. Incident symptoms/triage are conditional, not mandatory for normal use.
4. Define decisions before their dependent actions. Each actionable step names
   the actor, target, action, expected observable result and where to go if it
   fails. Include stop conditions, interruption/resume behavior and evidence to
   preserve. Mark non-idempotent steps and check prior state before repeating them.
5. Before consequential changes describe scope, applicable authority and rollback
   or irreversibility with a recovery/escalation alternative. Reuse existing
   permission boundaries. Drafting does not authorize execution or publication.
6. State whole-scenario completion and maintenance triggers. Resolve nonapplicable
   optional sections rather than leaving empty incident, dashboard or contact fields.
   Keep supplied parameters distinct from unresolved local facts. Do not embed secrets.
7. Self-check against the acceptance criteria and return paths plus unresolved
   facts to the owner. Request `playbook-review`; fixes stay with this authoring
   task and preserve previously accepted unaffected work.

## Completion and handoff

Authoring completes when the applicable template fields and decision paths are
source-grounded and unresolved facts are explicit. This means **drafted**, not
reviewed or rehearsed. Never set `last_validated` on creation or claim readiness
with unresolved required facts. The owner arranges review and authorized
rehearsal at the agreed level. Material procedure changes mark affected evidence
stale. Return to the invoking phase; do not complete its tasks independently.

For tracked work the coordinator recovers and checkpoints through
`project-backlog` before canonical mutations. A direct standalone request needs
no invented run or backlog entry.
