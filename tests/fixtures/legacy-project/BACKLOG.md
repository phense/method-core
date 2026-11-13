# Backlog
<!-- engineering-method:backlog-document {"schema_version":1,"project_key":"EM","mode":"local"} -->

This is the canonical local task register until GitHub Issues become writable and canonical.
Keep stable IDs unchanged. Order groups unblocker-first, then priority and dependency order.

## Status legend

- `⭕` Open
- `🔄` In progress
- `✅` Complete
- `❌` Blocked

## Tasks

<!-- engineering-method:backlog {"schema_version":1,"id":"EM-000","title":"Approve and commit the consolidated plugin design (`877a7ea`).","status":"complete","priority":"P0","parent_id":null,"depends_on":[],"notes":"","updated_at":"1970-01-01T00:00:00Z"} -->
- ✅ `EM-000` **P0** Approve and commit the consolidated plugin design (`877a7ea`).
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-001","title":"Establish the dual-host plugin foundation and provenance controls. Blocks `EM-002` through `EM-005`.","status":"complete","priority":"P0","parent_id":null,"depends_on":[],"notes":"","updated_at":"1970-01-01T00:00:00Z"} -->
- ✅ `EM-001` **P0** Establish the dual-host plugin foundation and provenance controls. Blocks `EM-002` through `EM-005`.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-001.1","title":"Create compatible Codex and Claude plugin manifests.","status":"complete","priority":"P0","parent_id":"EM-001","depends_on":[],"notes":"","updated_at":"1970-01-01T00:00:00Z"} -->
  - ✅ `EM-001.1` **P0** Create compatible Codex and Claude plugin manifests.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-001.2","title":"Add the dependency-free Python validation and test scaffold.","status":"complete","priority":"P0","parent_id":"EM-001","depends_on":[],"notes":"","updated_at":"1970-01-01T00:00:00Z"} -->
  - ✅ `EM-001.2` **P0** Add the dependency-free Python validation and test scaffold.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-001.3","title":"Pin upstream revisions and implement MIT attribution controls.","status":"complete","priority":"P0","parent_id":"EM-001","depends_on":[],"notes":"","updated_at":"1970-01-01T00:00:00Z"} -->
  - ✅ `EM-001.3` **P0** Pin upstream revisions and implement MIT attribution controls.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-001.4","title":"Add baseline structural validation for both hosts.","status":"complete","priority":"P0","parent_id":"EM-001","depends_on":[],"notes":"","updated_at":"1970-01-01T00:00:00Z"} -->
  - ✅ `EM-001.4` **P0** Add baseline structural validation for both hosts.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-013","title":"Make state checks read-only and verify documentation skill routing","status":"complete","priority":"P0","parent_id":null,"depends_on":[],"notes":"Read-only state-check fix and native routing verified: Codex 5/5, Claude 5/5, OpenCode 2 bounded probes. Corrected native Claude authentication environment after forced config selected different account metadata; 319 tests and independent reviews passed. See docs/verification/EM-013-prepublication.md. No remote publication.","updated_at":"2026-09-16T09:20:15Z"} -->
- ✅ `EM-013` **P0** Make state checks read-only and verify documentation skill routing
  - Notes: Read-only state-check fix and native routing verified: Codex 5/5, Claude 5/5, OpenCode 2 bounded probes. Corrected native Claude authentication environment after forced config selected different account metadata; 319 tests and independent reviews passed. See docs/verification/EM-013-prepublication.md. No remote publication.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-002","title":"Implement durable project state and compact continuity","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-001"],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
- ✅ `EM-002` **P1** Implement durable project state and compact continuity
  - Depends on: `EM-001`
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-002.1","title":"Add state models and safe filesystem primitives.","status":"complete","priority":"P1","parent_id":"EM-002","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-002.1` **P1** Add state models and safe filesystem primitives.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-002.2","title":"Implement stable local backlog parsing, sorting, and archiving.","status":"complete","priority":"P1","parent_id":"EM-002","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-002.2` **P1** Implement stable local backlog parsing, sorting, and archiving.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-002.3","title":"Maintain the non-duplicative `FEATURES.md` capability inventory.","status":"complete","priority":"P1","parent_id":"EM-002","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-002.3` **P1** Maintain the non-duplicative `FEATURES.md` capability inventory.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-002.4","title":"Add the testable GitHub boundary.","status":"complete","priority":"P1","parent_id":"EM-002","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-002.4` **P1** Add the testable GitHub boundary.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-002.5","title":"Implement idempotent issue migration, relationships, cache, and offline reconciliation.","status":"complete","priority":"P1","parent_id":"EM-002","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-002.5` **P1** Implement idempotent issue migration, relationships, cache, and offline reconciliation.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-002.6","title":"Implement versioned compact-continuity checkpoints and events.","status":"complete","priority":"P1","parent_id":"EM-002","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-002.6` **P1** Implement versioned compact-continuity checkpoints and events.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-002.7","title":"Wire project-state commands and the `project-backlog` skill.","status":"complete","priority":"P1","parent_id":"EM-002","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-002.7` **P1** Wire project-state commands and the `project-backlog` skill.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-003","title":"Build the curated, non-overlapping lifecycle and quality skills","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-001"],"notes":"","updated_at":"2026-09-04T14:43:51Z"} -->
- ✅ `EM-003` **P1** Build the curated, non-overlapping lifecycle and quality skills
  - Depends on: `EM-001`
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-003.1","title":"Define exclusive lifecycle contracts and artifact templates.","status":"complete","priority":"P1","parent_id":"EM-003","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-003.1` **P1** Define exclusive lifecycle contracts and artifact templates.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-003.2","title":"Adapt Spec Kit `specify`, `plan`, `tasks`, and `converge`.","status":"complete","priority":"P1","parent_id":"EM-003","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-003.2` **P1** Adapt Spec Kit `specify`, `plan`, `tasks`, and `converge`.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-003.3","title":"Adapt OpenSpec `propose`, `apply`, and `archive`.","status":"complete","priority":"P1","parent_id":"EM-003","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-003.3` **P1** Adapt OpenSpec `propose`, `apply`, and `archive`.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-003.4","title":"Port Superpowers debugging, TDD, and verification.","status":"complete","priority":"P1","parent_id":"EM-003","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-003.4` **P1** Port Superpowers debugging, TDD, and verification.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-003.5","title":"Port review, worktree, and parallel-dispatch support.","status":"complete","priority":"P1","parent_id":"EM-003","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:50Z"} -->
  - ✅ `EM-003.5` **P1** Port review, worktree, and parallel-dispatch support.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-003.6","title":"Integrate project-backlog support and collision acceptance.","status":"complete","priority":"P1","parent_id":"EM-003","depends_on":[],"notes":"","updated_at":"2026-09-04T14:43:51Z"} -->
  - ✅ `EM-003.6` **P1** Integrate project-backlog support and collision acceptance.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-004","title":"Add efficient subagent orchestration and the architecture gate","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-002","EM-003"],"notes":"","updated_at":"2026-09-05T10:52:23Z"} -->
- ✅ `EM-004` **P1** Add efficient subagent orchestration and the architecture gate
  - Depends on: `EM-002`, `EM-003`
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-004.1","title":"Add shared model roles, host adapters, and agent-role briefs.","status":"complete","priority":"P1","parent_id":"EM-004","depends_on":[],"notes":"","updated_at":"2026-09-05T10:52:23Z"} -->
  - ✅ `EM-004.1` **P1** Add shared model roles, host adapters, and agent-role briefs.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-004.2","title":"Implement cohesive-slice orchestration with targeted review and evidence-driven fix loops.","status":"complete","priority":"P1","parent_id":"EM-004","depends_on":[],"notes":"","updated_at":"2026-09-05T10:52:23Z"} -->
  - ✅ `EM-004.2` **P1** Implement cohesive-slice orchestration with targeted review and evidence-driven fix loops.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-004.3","title":"Implement evidence-driven defect convergence.","status":"complete","priority":"P1","parent_id":"EM-004","depends_on":[],"notes":"","updated_at":"2026-09-05T10:52:23Z"} -->
  - ✅ `EM-004.3` **P1** Implement evidence-driven defect convergence.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-004.4","title":"Implement design-time and as-built UML analysis under `docs/uml/`.","status":"complete","priority":"P1","parent_id":"EM-004","depends_on":[],"notes":"","updated_at":"2026-09-05T10:52:23Z"} -->
  - ✅ `EM-004.4` **P1** Implement design-time and as-built UML analysis under `docs/uml/`.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-004.5","title":"Add the system-architect integration-test gate.","status":"complete","priority":"P1","parent_id":"EM-004","depends_on":[],"notes":"","updated_at":"2026-09-05T10:52:23Z"} -->
  - ✅ `EM-004.5` **P1** Add the system-architect integration-test gate.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-004.6","title":"Verify recovery across compaction and subagent lifecycle boundaries.","status":"complete","priority":"P1","parent_id":"EM-004","depends_on":[],"notes":"","updated_at":"2026-09-05T10:52:23Z"} -->
  - ✅ `EM-004.6` **P1** Verify recovery across compaction and subagent lifecycle boundaries.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-008","title":"Add source-linked OpenCode skill integration","status":"complete","priority":"P1","parent_id":null,"depends_on":[],"notes":"Implemented and independently reviewed; all 17 shared skills discovered from retained main checkout and bounded DeepSeek skill invocation passed. Installed locally; no remote publication or RAG lifecycle acceptance.","updated_at":"2026-09-11T14:19:43Z"} -->
- ✅ `EM-008` **P1** Add source-linked OpenCode skill integration
  - Notes: Implemented and independently reviewed; all 17 shared skills discovered from retained main checkout and bounded DeepSeek skill invocation passed. Installed locally; no remote publication or RAG lifecycle acceptance.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-009","title":"Publish OpenCode integration as patch release 0.1.1","status":"complete","priority":"P1","parent_id":null,"depends_on":[],"notes":"Published v0.1.1 from b6bff25; 317 tests, reproducible package and isolated native installs passed. Downloaded GitHub asset matches c96f758a14c4ed3fd2c5b457d6c97beee3c4a37b3262e7de70a7e11e96a1a448.","updated_at":"2026-09-11T15:11:54Z"} -->
- ✅ `EM-009` **P1** Publish OpenCode integration as patch release 0.1.1
  - Notes: Published v0.1.1 from b6bff25; 317 tests, reproducible package and isolated native installs passed. Downloaded GitHub asset matches c96f758a14c4ed3fd2c5b457d6c97beee3c4a37b3262e7de70a7e11e96a1a448.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-010","title":"Add scale-aware documentation and reader-oriented writing skills","status":"complete","priority":"P1","parent_id":null,"depends_on":[],"notes":"Eight original skills, writing-depth and reader-oriented-output policies, curse-of-knowledge filter, five documentation templates, handoff graph and trigger matrix extension. Local suite, validators and Claude strict validation passed; native routing evaluation of the new cases not run (paid); OpenCode discovery of new skills not re-verified.","updated_at":"2026-09-16T07:48:30Z"} -->
- ✅ `EM-010` **P1** Add scale-aware documentation and reader-oriented writing skills
  - Notes: Eight original skills, writing-depth and reader-oriented-output policies, curse-of-knowledge filter, five documentation templates, handoff graph and trigger matrix extension. Local suite, validators and Claude strict validation passed; native routing evaluation of the new cases not run (paid); OpenCode discovery of new skills not re-verified.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-010.1","title":"Add writing-depth and reader-oriented-output shared policies and documentation templates.","status":"complete","priority":"P1","parent_id":"EM-010","depends_on":[],"notes":"","updated_at":"2026-09-16T07:48:29Z"} -->
  - ✅ `EM-010.1` **P1** Add writing-depth and reader-oriented-output shared policies and documentation templates.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-010.2","title":"Add the documentation-planning, documentation-authoring and documentation-review lifecycle skills.","status":"complete","priority":"P1","parent_id":"EM-010","depends_on":[],"notes":"","updated_at":"2026-09-16T07:48:29Z"} -->
  - ✅ `EM-010.2` **P1** Add the documentation-planning, documentation-authoring and documentation-review lifecycle skills.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-010.3","title":"Add explaining-concepts, writing-procedures, empathic-troubleshooting, terminology-guard and visual-placeholders supporting skills.","status":"complete","priority":"P1","parent_id":"EM-010","depends_on":[],"notes":"","updated_at":"2026-09-16T07:48:29Z"} -->
  - ✅ `EM-010.3` **P1** Add explaining-concepts, writing-procedures, empathic-troubleshooting, terminology-guard and visual-placeholders supporting skills.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-010.4","title":"Extend handoff graph, trigger matrix, contract tests and host adapters.","status":"complete","priority":"P1","parent_id":"EM-010","depends_on":[],"notes":"","updated_at":"2026-09-16T07:48:29Z"} -->
  - ✅ `EM-010.4` **P1** Extend handoff graph, trigger matrix, contract tests and host adapters.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-010.5","title":"Record sources, update README, usage, features and verification evidence.","status":"complete","priority":"P1","parent_id":"EM-010","depends_on":[],"notes":"","updated_at":"2026-09-16T07:48:29Z"} -->
  - ✅ `EM-010.5` **P1** Record sources, update README, usage, features and verification evidence.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-011","title":"Integrate adapted Humanizer drafting constraints into medium and large documentation writing","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-010"],"notes":"Humanizer drafting rules loaded before medium/large authoring; contextual preservation rules, provenance and independent review verified. See docs/verification/EM-011-humanizer-drafting.md. Native host routing and installation are not claimed.","updated_at":"2026-09-16T08:07:31Z"} -->
- ✅ `EM-011` **P1** Integrate adapted Humanizer drafting constraints into medium and large documentation writing
  - Depends on: `EM-010`
  - Notes: Humanizer drafting rules loaded before medium/large authoring; contextual preservation rules, provenance and independent review verified. See docs/verification/EM-011-humanizer-drafting.md. Native host routing and installation are not claimed.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-012","title":"Add local Quarto and Typst PDF export for documentation","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-011"],"notes":"Original Quarto/Typst manual template and export skill integrated; native en/de and reordered 120-row table checks passed, source bytes preserved, pages visually inspected. Independent review Ready. See docs/verification/EM-012-quarto-pdf.md. No remote publication or host-routing acceptance.","updated_at":"2026-09-16T08:29:21Z"} -->
- ✅ `EM-012` **P1** Add local Quarto and Typst PDF export for documentation
  - Depends on: `EM-011`
  - Notes: Original Quarto/Typst manual template and export skill integrated; native en/de and reordered 120-row table checks passed, source bytes preserved, pages visually inspected. Independent review Ready. See docs/verification/EM-012-quarto-pdf.md. No remote publication or host-routing acceptance.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-014","title":"Integrate development and system-deliverable playbooks into engineering lifecycles","status":"complete","priority":"P1","parent_id":null,"depends_on":[],"notes":"Two supporting playbook skills and need/evidence policy integrated into Spec Kit and OpenSpec. 319 tests, validators, pinned-source audit, independent review, reproducible package and disposable Claude/Codex installation passed. No publication, persistent installation or native routing evaluation. See docs/verification/EM-014-playbooks.md.","updated_at":"2026-09-17T07:16:38Z"} -->
- ✅ `EM-014` **P1** Integrate development and system-deliverable playbooks into engineering lifecycles
  - Notes: Two supporting playbook skills and need/evidence policy integrated into Spec Kit and OpenSpec. 319 tests, validators, pinned-source audit, independent review, reproducible package and disposable Claude/Codex installation passed. No publication, persistent installation or native routing evaluation. See docs/verification/EM-014-playbooks.md.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-015","title":"Publish documentation, PDF, playbook and state-check work as minor release 0.2.0","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-013","EM-014"],"notes":"Published v0.2.0 from a050f0e; 319 tests, validators and reproducible package passed. Downloaded GitHub asset matches 3549be2d733267397b868d1f2b2aa21cce758cd2baf31ade482f644fd12a5e2c.","updated_at":"2026-09-17T08:12:00Z"} -->
- ✅ `EM-015` **P1** Publish documentation, PDF, playbook and state-check work as minor release 0.2.0
  - Depends on: `EM-013`, `EM-014`
  - Notes: Published v0.2.0 from a050f0e; 319 tests, validators and reproducible package passed. Downloaded GitHub asset matches 3549be2d733267397b868d1f2b2aa21cce758cd2baf31ade482f644fd12a5e2c.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-016","title":"Refine the documentation PDF template with professional A4 typography","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-012"],"notes":"Professional A4 template and native PDF checks pass. Authorized for publication in v0.2.1. A stale installed wrapper created closed GitHub Issues #82-134; they remain closed and were not deleted.","updated_at":"2026-09-18T16:29:51Z"} -->
- ✅ `EM-016` **P1** Refine the documentation PDF template with professional A4 typography
  - Depends on: `EM-012`
  - Notes: Professional A4 template and native PDF checks pass. Authorized for publication in v0.2.1. A stale installed wrapper created closed GitHub Issues #82-134; they remain closed and were not deleted.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-017","title":"Publish the professional PDF template as patch release 0.2.1","status":"complete","priority":"P1","parent_id":null,"depends_on":["EM-016"],"notes":"Published stable Latest v0.2.1 from 49aa3c6; 319 tests, native PDF checks, validators, reproducible 256-file package and clean installs passed. Downloaded asset matches 2a0d0b6d520d509276c7d04d80b83a43a5aada78132d1ae48461c03fe3c21693.","updated_at":"2026-09-18T16:32:15Z"} -->
- ✅ `EM-017` **P1** Publish the professional PDF template as patch release 0.2.1
  - Depends on: `EM-016`
  - Notes: Published stable Latest v0.2.1 from 49aa3c6; 319 tests, native PDF checks, validators, reproducible 256-file package and clean installs passed. Downloaded asset matches 2a0d0b6d520d509276c7d04d80b83a43a5aada78132d1ae48461c03fe3c21693.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-005","title":"Validate, document, and package the complete plugin","status":"complete","priority":"P2","parent_id":null,"depends_on":["EM-001","EM-004"],"notes":"All nine original gate criteria accepted on 0784c79 with explicit same-package evidence reuse, Claude checkpoint supplement and independently verified ownership metadata correction. Failed reports preserved; see docs/verification/EM-005-acceptance.md. Accidental Issues #1-38 removed with approval; local backlog remains canonical.","updated_at":"2026-09-05T19:11:37Z"} -->
- ✅ `EM-005` **P2** Validate, document, and package the complete plugin
  - Depends on: `EM-001`, `EM-004`
  - Notes: All nine original gate criteria accepted on 0784c79 with explicit same-package evidence reuse, Claude checkpoint supplement and independently verified ownership metadata correction. Failed reports preserved; see docs/verification/EM-005-acceptance.md. Accidental Issues #1-38 removed with approval; local backlog remains canonical.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.1","title":"Finalize platform adapters and marketplace metadata.","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"","updated_at":"2026-09-05T11:04:23Z"} -->
  - ✅ `EM-005.1` **P2** Finalize platform adapters and marketplace metadata.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.2","title":"Add Codex/Claude trigger, collision, fallback, and workflow evaluations.","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"All 12 routing cases passed on each host: gpt-6-astra low and claude-fable-5-1 low, package 0784c79.","updated_at":"2026-09-05T19:11:37Z"} -->
  - ✅ `EM-005.2` **P2** Add Codex/Claude trigger, collision, fallback, and workflow evaluations.
    - Notes: All 12 routing cases passed on each host: gpt-6-astra low and claude-fable-5-1 low, package 0784c79.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.3","title":"Execute the large-feature architecture fixture on both hosts.","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"All ten architecture phases and original native-review/hash/integration assertions passed on both hosts; Claude required the documented invocation supplement and one clerical report correction. See docs/verification/EM-005-acceptance.md.","updated_at":"2026-09-05T19:11:37Z"} -->
  - ✅ `EM-005.3` **P2** Execute the large-feature architecture fixture on both hosts.
    - Notes: All ten architecture phases and original native-review/hash/integration assertions passed on both hosts; Claude required the documented invocation supplement and one clerical report correction. See docs/verification/EM-005-acceptance.md.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.4","title":"Complete static, package, and clean-install validation.","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"308 tests, both validators, provenance, reproducible 188-file package and both native clean installs passed on 0784c79.","updated_at":"2026-09-05T19:11:37Z"} -->
  - ✅ `EM-005.4` **P2** Complete static, package, and clean-install validation.
    - Notes: 308 tests, both validators, provenance, reproducible 188-file package and both native clean installs passed on 0784c79.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.5","title":"Write and verify the public README and third-party notices.","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"","updated_at":"2026-09-05T11:04:23Z"} -->
  - ✅ `EM-005.5` **P2** Write and verify the public README and third-party notices.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.6","title":"Run the system-architect release gate.","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"Independent Astra low reviewer accepted complete original gate coverage with explicit evidence reuse; no unresolved Critical or Important findings. Not a successful single release-check invocation.","updated_at":"2026-09-05T19:11:37Z"} -->
  - ✅ `EM-005.6` **P2** Run the system-architect release gate.
    - Notes: Independent Astra low reviewer accepted complete original gate coverage with explicit evidence reuse; no unresolved Critical or Important findings. Not a successful single release-check invocation.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.7","title":"Apply shared proportionality and an effort brake to every skill.","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"User-approved scope correction; see docs/verification/EM-005-completion-path.md for remaining release evidence.","updated_at":"2026-09-05T13:22:56Z"} -->
  - ✅ `EM-005.7` **P2** Apply shared proportionality and an effort brake to every skill.
    - Notes: User-approved scope correction; see docs/verification/EM-005-completion-path.md for remaining release evidence.
  <!-- engineering-method:backlog {"schema_version":1,"id":"EM-005.8","title":"Capture native Codex reviewer replies with independently confirmed scope","status":"complete","priority":"P2","parent_id":"EM-005","depends_on":[],"notes":"305 local tests, one independent bounded code review and one successful native Codex capture probe (90-second maximum). Existing release assertions unchanged; full architecture/release acceptance remains open.","updated_at":"2026-09-05T14:49:20Z"} -->
  - ✅ `EM-005.8` **P2** Capture native Codex reviewer replies with independently confirmed scope
    - Notes: 305 local tests, one independent bounded code review and one successful native Codex capture probe (90-second maximum). Existing release assertions unchanged; full architecture/release acceptance remains open.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-006","title":"Publish the documented public prerelease with bounded verification","status":"complete","priority":"P2","parent_id":null,"depends_on":[],"notes":"Published phense/engineering-method and v0.1.0-rc.1 at 9ff0bdd. Verified public visibility, tag, prerelease flag, downloaded ZIP/checksum and GitHub install/update/disable/removal on both hosts. EM-005 remains incomplete; no issue migration.","updated_at":"2026-09-05T14:13:52Z"} -->
- ✅ `EM-006` **P2** Publish the documented public prerelease with bounded verification
  - Notes: Published phense/engineering-method and v0.1.0-rc.1 at 9ff0bdd. Verified public visibility, tag, prerelease flag, downloaded ZIP/checksum and GitHub install/update/disable/removal on both hosts. EM-005 remains incomplete; no issue migration.
<!-- engineering-method:backlog {"schema_version":1,"id":"EM-007","title":"Publish stable version 0.1.0 and update public documentation","status":"complete","priority":"P2","parent_id":null,"depends_on":["EM-005"],"notes":"Published v0.1.0 at e9f5130 as stable Latest with checked ZIP and SHA256SUMS. 308 tests, validators, provenance, reproducible packaging, both clean installs, downloaded bytes and GitHub/main plus fixed-tag installs verified. Prior rc.1 unchanged; no issue migration.","updated_at":"2026-09-05T19:27:21Z"} -->
- ✅ `EM-007` **P2** Publish stable version 0.1.0 and update public documentation
  - Depends on: `EM-005`
  - Notes: Published v0.1.0 at e9f5130 as stable Latest with checked ZIP and SHA256SUMS. 308 tests, validators, provenance, reproducible packaging, both clean installs, downloaded bytes and GitHub/main plus fixed-tag installs verified. Prior rc.1 unchanged; no issue migration.
