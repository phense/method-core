---
name: receiving-code-review
description: "Use as the primary workflow for unverified review feedback, including claimed bugs, until checked against the current repository and dispositioned. Not for blindly implementing suggestions or accepting a verdict without evidence."
---

# Receiving Code Review

Apply the shared [proportionality rule](../../shared/policies/proportionality.md)
before adding work, delegating, or repeating verification.

Treat feedback as a technical hypothesis. Understand it, verify against current
code and governing requirements, then act on evidence.

This workflow remains primary while checking an incoming allegation, even when
that check runs code or tests. If the allegation is disproved, record the evidence
and reject it without entering a debugging lifecycle. Transfer to
`systematic-debugging` only for a confirmed failure whose cause still needs
diagnosis; the review finding retains its identity and returns here for its
final disposition after diagnosis and repair.

## Evaluate first

1. Read all findings and their claimed dependencies.
2. Restate each technical requirement in concrete terms. If any item is unclear
   and could affect another, clarify before implementing the set.
3. Verify against current code, tests, platform or version constraints, project
   decisions, and actual call sites.
4. Decide whether the finding is correct, already resolved, out of scope,
   incompatible, or based on incomplete context.
5. Give concise technical pushback with paths and evidence when a suggestion is
   unsound. Escalate a conflict with an approved architecture or user decision.

External review is not automatically authoritative. Current user instructions,
project gates, approved artifacts, and repository evidence retain their normal
authority.

## Resolve findings

Work one finding at a time in impact and dependency order:

1. Critical security, data, or broken-behavior issues.
2. Important requirement, architecture, interface, and test gaps.
3. Accepted Minor improvements within current scope.

For behavior changes, use `test-driven-development` and observe a meaningful
failure before the fix. Run the narrow affected checks after each correction,
then use `verification-before-completion` before claiming the finding resolved.
Re-review when a correction changes an interface or integration boundary.

## Completion

Feedback handling is complete when every finding has a technically evidenced
disposition, accepted changes are implemented and freshly verified, rejected
changes have a concise reason, and no Critical or Important finding remains open.

## Common mistakes

- Agreeing performatively before checking the code.
- Implementing understood items while a related item remains ambiguous.
- Adding an unused abstraction because it sounds more professional.
- Applying a reviewer suggestion that breaks compatibility or an approved
  decision.
- Batch-fixing several findings without isolating their tests and evidence.
