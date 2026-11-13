---
name: verification-before-completion
description: "Use when about to make any pass, fix, readiness, or completion claim and before committing or handing off work. Requires fresh output from the full command that proves the claim."
---

# Verification Before Completion

Apply the shared [proportionality rule](../../shared/policies/proportionality.md)
before adding work, delegating, or repeating verification.

Evidence precedes every success claim. Confidence, prior output, a partial check,
or another agent's report does not prove the current state.

## Trigger

Use immediately before saying that work passes, is fixed, is ready, or is
complete; before a commit or handoff; and after any fix that could change the
relevant evidence.

## Verification gate

1. **Identify the command** or observable check that directly proves the exact
   claim.
2. **Run the full command** now in the current workspace and state.
3. **Read the complete output**, including failures, warnings, skipped checks,
   counts, and exit status.
4. Compare that evidence with every part of the claim and applicable acceptance
   criteria.
5. If evidence is insufficient or failing, report the actual status and keep the
   work open. If it proves the claim, cite the command and result with the claim.

## Evidence matching

| Claim | Required current evidence |
|---|---|
| Tests pass | Full relevant test command with zero failures and successful exit status |
| Defect fixed | Original reproduction or regression test passes plus affected tests |
| Build succeeds | Complete build command exits successfully |
| Review finding resolved | Fix diff and the check that exercises the finding |
| Requirements met | Requirement-by-requirement artifact and behavior evidence |
| Delegated work complete | Independently inspected diff and rerun verification |

Fresh means produced after the latest relevant change. Prior output, expected
behavior, a narrower check, or a successful unrelated command cannot be reused.

## Completion

Verification completes only when the proof command is current, its entire output
was inspected, exit status and failure counts support the claim, and all claim
dimensions are covered. Otherwise completion remains refused.

## Warning signs

- Words such as should, probably, or seems replace evidence.
- Only a linter is cited for a build or runtime claim.
- A targeted test is generalized to the entire suite.
- Output predates the last code, test, configuration, or artifact change.
- A report from another worker is repeated without inspecting the diff and rerun.
