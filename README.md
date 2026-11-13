---
type: reference
audience: Method maintainers familiar with Git and Python
version: 0.1.0
---
# Method Core

Method Core is the shared source for [Engineering Method](https://github.com/phense/engineering-method) and [Writing Method](https://github.com/phense/writing-method). The repositories remain separate, with their own Issues and pull requests, and share the `agent-methods` topic. Install either method; Core is a source dependency bundled inside each plugin.

## Ownership

| Core owns | Consumer owns |
|---|---|
| Claude, Codex and OpenCode adapters | Its lifecycle selection, handoff graph and domain-specific roles |
| Backlog and continuity runtime | Its specifications, documents, task state and acceptance decisions |
| Verification, review, worktree and delegation support | Engineering lifecycles or writing/didactic skills |
| Generic playbook authoring, review, policy and templates | Why a particular operation needs a playbook and its rehearsal requirements |
| Export integrity, packaging and OpenCode installation tools | Plugin identity, marketplace, releases and method-specific tests |

Gemini has no verified adapter yet. Installing a method into another client does not prove adapter support.

## Terms

An **export** is a file listed in `method-core.json`. A **consumer** is one of the two methods. A **vendored copy** is the consumer's local copy of an export. The **core lock** (`method-core.lock.json`) records the immutable Git revision, file hashes and executable modes. A **playbook** is a scenario-bound procedure with decisions, failure paths and verification; its draft, review and rehearsal are separate facts.

## Updating a consumer

Prerequisites: Python 3.11 or newer, Git, a clean committed Core checkout, and a clean consumer checkout. Run commands from the consumer root. Replace `/path/to/method-core` with the actual Core checkout.

1. Commit and test the intended Core change in its own repository.
2. Synchronize that committed revision into the consumer:

   ```sh
   python3 /path/to/method-core/scripts/sync-core --source-root /path/to/method-core --target-root .
   ```

3. Check the resulting copy without network access:

   ```sh
   python3 scripts/sync-core --check
   python3 scripts/validate-plugin
   python3 -m unittest discover -s tests -t . -v
   ```

4. Review the consumer diff and commit its copies and lock together. Repeat for the other method, then verify both lock revisions agree.

A successful sync prints `status: passed`, a revision and a file count. A conflict exits nonzero before writing. Sync refuses unowned destination files even when their content matches; initial extraction must explicitly remove only reviewed, backed-up legacy shared copies before synchronization. It never changes host authentication or target-project state.

## Rollback and recovery

To return a consumer to a previous Core revision, supply its full commit SHA with `--revision` to the sync command. Current managed files must match the installed lock first. Revert an accidental local edit through Git after reviewing it; synchronization deliberately refuses to overwrite it. A failed filesystem transaction restores the prior files, modes and lock. Review permissions or disk errors before retrying. The old `.engineering-method/` project-state path and `engineering_method` Python package name remain for compatibility in both consumers.

## Coexistence

Both plugins expose the same eight shared support skills under their own namespaces. Choose the invoking method's namespace, for example `writing-method:playbook-authoring`; run one copy. Shared files are identical for a common Core revision. OpenCode uses distinct loader names and preserves user configuration.

## Development and verification

```sh
python3 -m unittest discover -s tests -t . -v
python3 scripts/validate-plugin
```

Tests exercise real local Git/file operations, rollback after an injected write failure, existing state/continuity contracts, archive identity and OpenCode loader coexistence. They do not establish live model routing or provider availability. License/source metadata is retained in [third-party notices](THIRD_PARTY_NOTICES.md); original code uses the [MIT License](LICENSE).
