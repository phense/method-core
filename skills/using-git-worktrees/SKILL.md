---
name: using-git-worktrees
description: "Use when feature work needs isolation or parallel writes need separate ownership. Not for creating a second worktree when already isolated or when branch safety and baseline health are unknown."
---

# Using Git Worktrees

Apply the shared [proportionality rule](../../shared/policies/proportionality.md)
before adding work, delegating, or repeating verification.

Detect existing isolation first, prefer the platform's native worktree
capability, and use a guarded portable fallback only when necessary.

## Detect the environment

Resolve and compare:

- the current resolved git directory;
- the repository's common git directory;
- the current branch name or detached HEAD state;
- the superproject path used to distinguish a submodule from a linked worktree.

Different resolved and common git directories indicate an existing linked
worktree only when the checkout is not a submodule. When already isolated, reuse
it and do not create nested isolation. A detached HEAD must be reported before
work begins because branch integration may require platform-owned action.

## Isolation order

1. Honor an explicit user or project worktree location.
2. Prefer a native worktree capability when the platform exposes one; native
   lifecycle ownership prevents phantom worktree state.
3. Otherwise use the platform adapter's portable fallback with a project-local
   `.worktrees/` directory, or `worktrees/` only when that is the established
   repository convention.
4. If safe isolation is unavailable, serialize writes in the current checkout
   after reporting the limitation and verifying branch safety.

## Fallback safety

Before portable fallback creation:

- verify the chosen worktree parent is ignored by repository rules;
- keep the target within that explicit parent and use an unambiguous branch name;
- ensure the target does not already contain unrelated data;
- never resolve a target to a broad path such as the filesystem root, a home
  directory, temporary-directory root, or repository root;
- do not delete, reset, move, or overwrite an existing path to make room;
- obtain any authority required by the platform before creation.

The platform adapter performs the actual branch and linked-worktree operation.
The shared skill supplies semantics and guards, not host invocation syntax.

## Project setup and baseline

Inside the selected checkout, inspect project manifests and use the established
dependency setup. Run the project's baseline tests before implementation. If
baseline tests fail, report their exact current output and distinguish them from
feature work before proceeding.

## Completion

Isolation is ready when the checkout path, branch or detached state, ownership,
ignore rule, project setup, and baseline test result are recorded. Do not claim a
clean baseline without fresh output.

## Common mistakes

- Assuming a checkout is not already linked without comparing git directories.
- Mistaking a submodule for a worktree.
- Bypassing native lifecycle management when it exists.
- Using an unignored project-local parent.
- Removing an existing directory as cleanup without proving ownership.
