# Review Report

```json
{
  "purpose": "review",
  "required": ["work_id", "slice_id", "base_commit", "head_commit", "requirements_verdict", "quality_verdict", "findings", "evidence", "test_evidence_assessed"]
}
```

## Range and verdicts

Record the work and slice IDs, full base and head commits, then give separate
requirements and quality verdicts for the complete range.

## Findings

For each finding record severity, requirement, repository-relative evidence,
why it matters, and the observable resolution condition. Say `none` only after
checking the entire range. Do not park actionable defects.

## Evidence assessment

Identify which reported commands/results were current and relevant, and which
cross-slice facts the coordinator must verify independently.
