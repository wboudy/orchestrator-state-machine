You are in Bead Swarm Mode for this repository.

Primary objective:
- Continue working until all beads are closed, or until a true human decision blocker is reached.

Execution loop:
1. Run `bd ready` and pick exactly one executable bead.
2. Run `bd show <id>`, then claim it with `bd update <id> --status in_progress`.
3. Implement to acceptance criteria with tests/checks relevant to touched files.
4. Close bead with evidence notes: `bd close <id> --reason "Completed"`.
5. Run session close steps after meaningful progress:
   - `git pull --rebase`
   - `bd sync`
   - `git push`
   - confirm `git status` is clean and up to date
6. Repeat from step 1.

Complex blocker protocol (mandatory):
- If the issue is trivial and local: fix inline and continue current bead.
- If a non-trivial blocker bug appears:
  1. Create dedicated bug bead (`--type bug`, or `--type task --labels bug` fallback).
  2. Include reproduction steps, expected/observed behavior, scope, and evidence.
  3. Link dependency: `bd dep add <current-bead> <bug-bead>`.
  4. Mark current bead blocked with note pointing to bug bead.
  5. Switch focus immediately to the bug bead (`--status in_progress`).
  6. After bug bead closes, return to the original bead and continue.

Stop conditions:
- `bd list --status=open` returns zero items.
- Or a human-only decision is required; in that case create/leave a clear escalation bead with decision request.
