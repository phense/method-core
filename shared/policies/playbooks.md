# Shared Playbooks

A playbook is a scenario-bound procedure with decisions, observable outcomes and
failure paths. A task list or design explanation alone is not a playbook.
Playbooks support the current method lifecycle; they do not create another
controller, executor or documentation work ID. Apply [proportionality](proportionality.md).

## Decide whether one is needed

Assess these two classes independently using requirements, architecture, planned
operations and actual system evidence. A prior incident is not required.

| Class | Create when | Deadline and lifetime |
|---|---|---|
| Development | A multi-step development or publishing operation affects live systems/data, crosses coordinated actors/environments, or needs nontrivial decisions, interruption recovery or rollback. Examples: cutover, staged migration, coordinated release or coordinated publication. | Reviewed and rehearsed to the agreed risk level before the operation; retain evidence, then archive if no longer needed. |
| System | Successful use, operation or recovery depends on a recurring or high-consequence procedure the delivered system or publication does not fully perform itself. Examples: onboarding with decisions, import recovery, backup restoration. | Included in delivery acceptance; maintained with the system and its interfaces. |

A simple reversible edit, self-explanatory action, fully automated operation
with adequate built-in handling, or ordinary task sequence does not by itself
justify a playbook. Automation may still require an operator recovery playbook.
Do not generate speculative catalogs. Record a concise `none` with rationale in
the owning spec/plan when the assessment finds no need. Reassess when scope,
interfaces, operational risk or recovery assumptions change.

## Record the decision in the owning artifacts

Use stable playbook IDs. For each required playbook record: class, scenario and
trigger, source requirement/risk, audience, owner, canonical path, dependent
operation or delivery task, readiness deadline, acceptance criteria and required
validation level/environment. If one procedure serves both classes, record both
obligations and link one canonical procedure; the earlier deadline still applies.
A system obligation cannot be archived merely because development ended.

Follow an existing repository convention. Otherwise use
`docs/playbooks/development/<id>.md` and `docs/playbooks/system/<id>.md`, with
review and rehearsal evidence beside them as `<id>-review.md`. These are output
paths in the target project, not files inside the plugin installation.

## Method integration

The invoking method owns the need decision, tasks, review, rehearsal and
acceptance. Engineering operations can include migrations, release or recovery;
writing operations can include publication, PDF production or recovery from a
failed export. Use the same scenario-bound template and evidence contract.

Method-specific phase hooks live in the consuming method's policies. They may
require playbooks for a concrete risk; shared support never requires an absent
engineering or writing lifecycle. Ordinary authoring, a simple export or a
reversible edit does not justify a playbook by itself. Direct authoring/review
requests use the supporting skill without inventing another lifecycle.

## Evidence and acceptance

Keep three separate facts, not one overloaded status:

1. **Drafted:** source-grounded procedure exists, with unresolved facts explicit.
2. **Reviewed:** content assessed at a named artifact revision; findings recorded.
3. **Rehearsed:** authorized execution or simulation recorded with artifact and
   system revision, environment, date, method, tested branches and actual results.

A review score, valid Markdown, successful generation or an example output is
not rehearsal evidence. Never fill `last_validated` with the creation date.
Choose the required validation level during planning in proportion to risk;
a tabletop exercise does not prove a live recovery. Record untested branches
and environmental limits. If a required rehearsal is unavailable, preserve the
blocker; only an explicit acceptance-scope decision by the authorized owner can
change that requirement, and it must not be labeled as a successful test.

An applicable command, interface, permission, dependency or failure-path change
invalidates affected review/rehearsal evidence until rechecked. A prose-only edit
may reuse evidence with a recorded rationale; do not relabel it as fresh execution.

## Authority and continuity

Authoring or reviewing a playbook does not authorize executing it. A rehearsal
uses existing project permissions, target/environment checks and risk controls;
never introduce blanket reapproval where authority already exists. State any
irreversible boundary and the alternative to rollback before the relevant step.

The owning coordinator uses `project-backlog` recovery, events and checkpoints
for tracked work. Supporting skills return artifact/evidence paths and findings;
they never independently change lifecycle phase or canonical task state. On
resume, read those artifacts and current system evidence before continuing.
