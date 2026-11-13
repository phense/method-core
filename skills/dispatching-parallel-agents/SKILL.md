---
name: dispatching-parallel-agents
description: "Use when two or more work domains may be independent and concurrency would materially help. Not for related failures, shared mutable state, overlapping file ownership, or sequential dependencies."
---

# Dispatching Parallel Agents

Apply the shared [proportionality rule](../../shared/policies/proportionality.md)
before adding work, delegating, or repeating verification.

Parallelism begins only after independence is established. Give each worker a
bounded, self-contained domain and retain integration responsibility in the
coordinator.

## Independence gate

For each proposed pair, establish from current evidence that:

- one result cannot invalidate or subsume the other's work;
- there is no unresolved shared root cause or sequential dependency;
- required inputs are stable for the duration of the work;
- writes, resources, and integration boundaries cannot interfere.

When independence is unknown, investigate together or serialize. Similar error
messages, nearby files, or convenience are not evidence of independence.

## Read-only investigation

Independent read-only investigation may run in parallel across separate failure
domains, components, requirements, or review passes. Each brief names the
question, allowed evidence, constraints, and required report. Workers do not
mutate shared state during a read-only assignment.

## Parallel writes

Parallel writes require all of:

- disjoint ownership of files and generated artifacts;
- stable agreed interface contracts;
- safe isolation owned by the platform;
- separate mutable resources and test state;
- an explicit integration order and acceptance evidence.

If any condition is absent, serialize writes and preserve concurrency only for
read-only work. Never assign two workers to edit the same file or shared
generated output.

## Dispatch contract

Every worker brief contains:

- one problem domain and expected outcome;
- exact owned paths and forbidden overlap;
- relevant requirements, errors, and current evidence;
- dependencies and interfaces that must remain stable;
- targeted verification to run;
- a report contract covering root cause or changes, tests, and concerns.

Platform adapters resolve worker creation and communication. The shared skill
does not name host tools or provider models.

## Integration

The coordinator reads every report, inspects each diff, checks ownership and
interface assumptions again, resolves conflicts, and reruns targeted checks.
After integration, run the full test suite appropriate to the combined risk.
Worker success reports alone are not completion evidence.

## Completion

Parallel work is complete only when all reports and diffs are reconciled, no
ownership or interface conflict remains, and fresh integrated verification
passes.

## Common mistakes

- Parallelizing failures before determining whether one root cause explains all.
- Treating different filenames as proof of independent state.
- Sending vague briefs that omit ownership or acceptance evidence.
- Integrating summaries without inspecting the actual changes.
