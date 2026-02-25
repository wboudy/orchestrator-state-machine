# Agent Instructions

This file is the execution contract for coding agents working in this repository.

## Primary Goal

Ship reliable progress while keeping the bead graph accurate, auditable, and fully pushed to remote.

## Session Start

1. Confirm repository state:
   - `git status --short --branch`
2. Confirm bead health:
   - `bd doctor`
3. Select ready work:
   - `bd ready`
   - `bd show <id>`
4. Claim the issue:
   - `bd update <id> --status in_progress`

## Working Loop

1. Implement the task scope from the issue description and acceptance criteria.
2. If new work appears, create follow-up beads immediately:
   - `bd create "..." --type task --priority 2`
3. Keep dependency graph accurate:
   - `bd dep add <blocked-id> <blocker-id>`
4. Validate changes:
   - Run tests/lints/build steps relevant to touched code.
5. Close finished work:
   - `bd close <id> --reason "Completed"`

## Failure and Escalation Protocol

Use this order:

1. Transient/tooling failure:
   - Retry once with narrowed scope and capture exact error in notes.
2. Repeatable implementation blocker:
   - Create a bug/task bead with reproduction details and dependency links.
3. Ambiguous requirements or high-risk behavior:
   - Pause implementation on that thread and create a decision bead.
4. Human escalation required:
   - Record what was tried, what is blocked, and what decision/input is needed.

Do not silently skip failures. Every unresolved blocker must have a bead.

## Optional Watcher Mode

For unattended execution, run:

```bash
scripts/bead_watcher.sh
```

Watcher expectations:

- It picks one ready bead per cycle and invokes `codex exec`.
- It must stop when no ready beads remain.
- It enforces max retries/no-progress caps to prevent infinite loops.
- For complex bugs discovered mid-implementation, it should create a dedicated bug bead, block the parent bead, and prioritize the bug bead next.

## Quick Reference

```bash
bd ready
bd show <id>
bd update <id> --status in_progress
bd close <id> --reason "Completed"
bd sync
```

## Landing the Plane (Mandatory End-of-Session)

Work is not complete until `git push` succeeds.

1. File follow-up issues for unfinished work.
2. Run quality gates for changed code.
3. Update bead statuses (close completed, keep active items accurate).
4. Sync and push:
   ```bash
   git pull --rebase
   bd sync
   git push
   git status
   ```
5. Ensure `git status` shows branch up to date and clean working tree.
6. Clear leftover stashes and prune stale remote refs:
   - `git stash list`
   - `git remote prune origin`
7. Hand off with concise summary: what changed, what is open, what is next.

## Hard Rules

- Never stop with unpushed local commits.
- Never claim work is done before verifying push success.
- Never leave discovered blockers undocumented.
