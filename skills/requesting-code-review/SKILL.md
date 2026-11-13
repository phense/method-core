---
name: requesting-code-review
description: "Use when an implementation slice needs review against requirements before integration or handoff. Requires independent review for risky or integration-bearing work and permits coordinator review for mechanical work."
---

# Requesting Code Review

Apply the shared [proportionality rule](../../shared/policies/proportionality.md)
before adding work, delegating, or repeating verification.

Review the complete change against its requirements and current repository
evidence before defects cascade into later slices.

## Review depth

| Slice risk | Required reviewer |
|---|---|
| Mechanical slices with obvious behavior, narrow files, and no integration impact | Coordinator review is sufficient |
| Ordinary multi-file behavior with clear interfaces | A reviewer independent of the implementation is preferred |
| Risky or integration-bearing slices, security or data changes, migrations, architecture, or final large-feature review | An independent reviewer is required |

Independence means the reviewer did not implement the reviewed slice and receives
the requirements and evidence rather than the implementer's conclusions.

## Prepare the review

Provide:

- a concise description of what changed;
- the authoritative plan, task, specification, and acceptance criteria;
- the exact base and head revisions or an equivalent bounded diff;
- relevant verification commands and current output;
- known constraints, decisions, and unresolved concerns.

Use [code-reviewer.md](code-reviewer.md) as the review contract. Keep the review
read-only and do not give the reviewer unrelated session history.

## Act on findings

1. Check every finding against the referenced code and requirements.
2. Fix Critical findings immediately and do not integrate with any open Critical
   or Important finding.
3. Treat Minor findings as actionable when they affect the current acceptance
   contract; otherwise record their disposition explicitly.
4. Use `receiving-code-review` for unclear or questionable feedback.
5. Re-run the narrow affected checks after each fix and review the fix diff.
6. Repeat review when a fix materially changes risk, interfaces, or integration
   behavior.

## Completion

Review is complete when the reviewer inspected the full bounded diff, tied every
finding to evidence, gave a clear verdict, and all Critical and Important
findings are resolved with fresh verification.

## Common mistakes

- Reviewing only the latest fix instead of the complete slice.
- Giving a reviewer a summary without the governing requirements.
- Accepting a verdict without inspecting its evidence.
- Treating passing unit tests as proof of cross-component correctness.
