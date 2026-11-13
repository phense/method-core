# Features

This inventory records implemented, changed, and historically removed capabilities. Planned work belongs only in `BACKLOG.md`.

<!-- engineering-method:feature {"schema_version":1,"id":"F-001","name":"Dual-host foundation","summary":"Shared plugin identity, MIT licensing, portable validation and pinned-source provenance controls.","status":"available","related_backlog_ids":["EM-001"],"updated_at":"2026-09-05T10:52:23Z"} -->
## `F-001` Dual-host foundation

- Status: available
- Summary: Shared plugin identity, MIT licensing, portable validation and pinned-source provenance controls.
- Related backlog: `EM-001`

<!-- engineering-method:feature {"schema_version":1,"id":"F-002","name":"Durable project state","summary":"Blocker-first local backlog, feature inventory, GitHub migration and native relationships, offline queue and compact recovery. State checks are read-only even with a writable remote; migration requires an explicitly authorized backlog-to-issues migrate command.","status":"available","related_backlog_ids":["EM-002"],"updated_at":"2026-09-16T08:51:39Z"} -->
## `F-002` Durable project state

- Status: available
- Summary: Blocker-first local backlog, feature inventory, GitHub migration and native relationships, offline queue and compact recovery. State checks are read-only even with a writable remote; migration requires an explicitly authorized backlog-to-issues migrate command.
- Related backlog: `EM-002`

<!-- engineering-method:feature {"schema_version":1,"id":"F-003","name":"Exclusive workflow skills","summary":"Twenty-five shared lifecycle and quality skills with artifact-specific handoffs: the original seventeen engineering skills plus eight documentation and reader-oriented writing skills added by EM-010. All 12 engineering routing cases passed on both hosts for 0784c79; the three documentation routing cases have contract-test coverage only.","status":"changed","related_backlog_ids":["EM-003"],"updated_at":"2026-09-16T07:47:28Z"} -->
## `F-003` Exclusive workflow skills

- Status: changed
- Summary: Twenty-five shared lifecycle and quality skills with artifact-specific handoffs: the original seventeen engineering skills plus eight documentation and reader-oriented writing skills added by EM-010. All 12 engineering routing cases passed on both hosts for 0784c79; the three documentation routing cases have contract-test coverage only.
- Related backlog: `EM-003`

<!-- engineering-method:feature {"schema_version":1,"id":"F-004","name":"Orchestration and architecture gates","summary":"Cohesive slices, protected continuity artifacts, independent review and evidence-driven fixes; relevant Mermaid views and executable checkout success/recovery acceptance. Mermaid sources are semantically checked, not rendered.","status":"available","related_backlog_ids":["EM-004"],"updated_at":"2026-09-05T10:52:23Z"} -->
## `F-004` Orchestration and architecture gates

- Status: available
- Summary: Cohesive slices, protected continuity artifacts, independent review and evidence-driven fixes; relevant Mermaid views and executable checkout success/recovery acceptance. Mermaid sources are semantically checked, not rendered.
- Related backlog: `EM-004`

<!-- engineering-method:feature {"schema_version":1,"id":"F-005","name":"Proportionate execution guidance","summary":"Every skill references shared local-check-first, evidence-reuse, focused-review and effort-brake instructions. Behavioral compliance is not guaranteed across arbitrary prompts.","status":"available","related_backlog_ids":["EM-005.7"],"updated_at":"2026-09-05T19:11:37Z"} -->
## `F-005` Proportionate execution guidance

- Status: available
- Summary: Every skill references shared local-check-first, evidence-reuse, focused-review and effort-brake instructions. Behavioral compliance is not guaranteed across arbitrary prompts.
- Related backlog: `EM-005.7`

<!-- engineering-method:feature {"schema_version":1,"id":"F-006","name":"Stable distribution and English documentation","summary":"Stable v0.1.0 on public GitHub with English documentation, reproducible package, checksum and verified dual-host main/tag installation. Original gate coverage accepted with the documented EM-005 evidence reuse and limits; historical rc.1 remains available.","status":"available","related_backlog_ids":["EM-006","EM-007"],"updated_at":"2026-09-05T19:27:21Z"} -->
## `F-006` Stable distribution and English documentation

- Status: available
- Summary: Stable v0.1.0 on public GitHub with English documentation, reproducible package, checksum and verified dual-host main/tag installation. Original gate coverage accepted with the documented EM-005 evidence reuse and limits; historical rc.1 remains available.
- Related backlog: `EM-006`, `EM-007`

<!-- engineering-method:feature {"schema_version":1,"id":"F-007","name":"Native OpenCode skill integration","summary":"Source-linked additive skill and adapter loading with guarded reversible installation; 17 skills discovered and bounded DeepSeek skill use verified on OpenCode 1.18.30. Full lifecycle and RAG hooks are outside this acceptance.","status":"available","related_backlog_ids":["EM-008"],"updated_at":"2026-09-11T14:19:43Z"} -->
## `F-007` Native OpenCode skill integration

- Status: available
- Summary: Source-linked additive skill and adapter loading with guarded reversible installation; 17 skills discovered and bounded DeepSeek skill use verified on OpenCode 1.18.30. Full lifecycle and RAG hooks are outside this acceptance.
- Related backlog: `EM-008`

<!-- engineering-method:feature {"schema_version":1,"id":"F-008","name":"Scale-aware documentation and reader-oriented writing","summary":"Writing-depth scale decision (small, medium, large); documentation-planning, documentation-authoring and documentation-review lifecycle with plan, chunk manifest, glossary, asset manifest and review templates under docs/writing; didactic skills explaining-concepts, writing-procedures and empathic-troubleshooting applied to documentation and ordinary replies; terminology-guard and visual-placeholders; human-prose-drafting (adapted from Humanizer, MIT) applied while drafting medium and large texts. Contract tests and validators pass; five bounded native routing cases pass on both Codex and Claude, with OpenCode pre-draft Humanizer invocation verified. These probes do not claim full document quality.","status":"available","related_backlog_ids":["EM-009","EM-010","EM-011","EM-013"],"updated_at":"2026-09-16T09:47:44Z"} -->
## `F-008` Scale-aware documentation and reader-oriented writing

- Status: available
- Summary: Writing-depth scale decision (small, medium, large); documentation-planning, documentation-authoring and documentation-review lifecycle with plan, chunk manifest, glossary, asset manifest and review templates under docs/writing; didactic skills explaining-concepts, writing-procedures and empathic-troubleshooting applied to documentation and ordinary replies; terminology-guard and visual-placeholders; human-prose-drafting (adapted from Humanizer, MIT) applied while drafting medium and large texts. Contract tests and validators pass; five bounded native routing cases pass on both Codex and Claude, with OpenCode pre-draft Humanizer invocation verified. These probes do not claim full document quality.
- Related backlog: `EM-009`, `EM-010`, `EM-011`, `EM-013`

<!-- engineering-method:feature {"schema_version":1,"id":"F-009","name":"Local Markdown book PDF export","summary":"Optional documentation-pdf skill with a professional A4 Quarto/Typst template: dark-navy editorial hierarchy, separate cover and contents, 12 pt body text, ordered Markdown chapters, linked contents and current/total page numbers. Native macOS English, German and long-table checks pass; PDF skill selection is verified on Codex, Claude and OpenCode. Rendering remains local.","status":"changed","related_backlog_ids":["EM-012","EM-013","EM-016"],"updated_at":"2026-09-18T16:29:51Z"} -->
## `F-009` Local Markdown book PDF export

- Status: changed
- Summary: Optional documentation-pdf skill with a professional A4 Quarto/Typst template: dark-navy editorial hierarchy, separate cover and contents, 12 pt body text, ordered Markdown chapters, linked contents and current/total page numbers. Native macOS English, German and long-table checks pass; PDF skill selection is verified on Codex, Claude and OpenCode. Rendering remains local.
- Related backlog: `EM-012`, `EM-013`, `EM-016`

<!-- engineering-method:feature {"schema_version":1,"id":"F-010","name":"Engineering playbook authoring and acceptance","summary":"Two supporting skills distinguish development-operation and system-deliverable playbooks, with phase-specific need assessment, authoring/review templates, interruption and rollback paths, and separate current review and rehearsal evidence. Local contracts, independent instruction scenarios and disposable Claude/Codex installation verified; no native-host routing or operational rehearsal claimed.","status":"available","related_backlog_ids":["EM-014"],"updated_at":"2026-09-17T07:16:38Z"} -->
## `F-010` Engineering playbook authoring and acceptance

- Status: available
- Summary: Two supporting skills distinguish development-operation and system-deliverable playbooks, with phase-specific need assessment, authoring/review templates, interruption and rollback paths, and separate current review and rehearsal evidence. Local contracts, independent instruction scenarios and disposable Claude/Codex installation verified; no native-host routing or operational rehearsal claimed.
- Related backlog: `EM-014`
