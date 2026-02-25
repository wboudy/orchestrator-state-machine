---
name: bug-blocker-spinout
description: Use when implementation hits a complex blocker and you need to convert it into a dedicated bug bead, block the parent bead, and switch focus to resolving the bug before returning.
---

# Bug Blocker Spinout

Use this workflow when an in-progress bead cannot be safely fixed inline.

## Trigger Conditions

- Root cause is unclear after initial investigation.
- Fix touches broad/high-risk surfaces.
- Repro is non-trivial and needs isolated debugging.
- Continuing inline would jeopardize current bead scope.

## Workflow

1. Capture evidence quickly:
   - command output/logs
   - repro steps
   - expected vs observed behavior
2. Create blocker bug bead:
   - `bd create "Blocker in <parent-id>: <short-title>" --type bug --priority 1 --description "<repro + evidence>" --acceptance "<definition of done>"`
   - If `--type bug` is not supported, use `--type task --labels bug`.
3. Link and block parent bead:
   - `bd dep add <parent-id> <bug-id>`
   - `bd update <parent-id> --status blocked --notes "Blocked by <bug-id>: <one-line reason>"`
4. Switch focus:
   - `bd update <bug-id> --status in_progress`
   - Work bug bead to `closed` or `blocked` with clear notes.
5. Resume flow:
   - If bug closes, move next ready bead to `in_progress` (often original parent).
   - If bug remains blocked, escalate with a human-decision bead and keep dependency graph explicit.

## Required End State

- Parent bead is never left ambiguous.
- Blocker relationship is explicit in dependencies.
- Evidence is preserved in bead notes/description.
