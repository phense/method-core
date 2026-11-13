# Agent Report

```json
{
  "required": ["status", "work_id", "slice_id", "commits", "files", "tests", "root_cause", "fix_findings", "concerns", "next_dependency_facts"],
  "tests_required": ["command", "result"],
  "statuses": ["DONE", "DONE_WITH_CONCERNS", "BLOCKED", "NEEDS_CONTEXT"]
}
```

## Identity and status

- Status: `<status>`
- Work ID: `<work-id>`
- Slice ID: `<slice-id>`

## Changes

- Commits: `<full-sha-and-subject-or-none>`
- Files: `<repository-relative-paths-or-none>`

## Tests

For every test run, record the exact command, result or exit status, and the
relevant red/green output. Do not replace output with an unsupported success
claim.

## Root cause and fix findings

Record the evidence-backed root cause, what the fix changed, and how the test
would catch regression. Use `not applicable` only when the slice is not a fix.

## Concerns

Record unresolved correctness, scope, safety, or evidence concerns, or `none`.

## Next dependency facts

State only facts the next slice can verify: stabilized interfaces, required
integration order, artifact paths, and open blockers.
