---
name: bead-swarm-long-horizon
description: Use when the user asks to swarm, churn, or work through beads continuously until completion; enforces one-bead-at-a-time execution and complex-blocker bug spinout/switching.
---

# Bead Swarm Long Horizon

Use this skill for sustained queue reduction work across many beads.

## Trigger

- User asks to "keep going", "churn through beads", "swarm beads", or "work until done".

## Workflow

1. Run `bd ready`.
2. Select exactly one ready bead and claim it with `bd update <id> --status in_progress`.
3. Implement to acceptance criteria and run relevant checks.
4. Record evidence in notes and close bead.
5. Sync and push progress regularly using `git pull --rebase`, `bd sync`, `git push`.
6. Repeat until no open beads remain or a human decision is required.

## Complex Blocker Rule

When a non-trivial bug appears during implementation:

1. Create a dedicated bug bead.
2. Add dependency from current bead to bug bead.
3. Mark current bead `blocked` with clear pointer to bug bead.
4. Switch focus to bug bead immediately.
5. Return to current bead only after bug bead is resolved or explicitly escalated.

For detailed blocker mechanics, reuse:

- `skills/bug-blocker-spinout/SKILL.md`

## Prompt Source

If a direct long-horizon execution prompt is requested, use:

- `prompts/bead-swarm-long-horizon.md`
