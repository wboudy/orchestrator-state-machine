# Orchestrator State Machine

State-machine control plane for routing implementation-time failures into a deterministic escalation workflow.

## What This Project Does

- Defines a finite-state machine (FSM) for worker/orchestrator handoff.
- Separates fast-path implementation from deeper triage and escalation.
- Enforces retry budgets, dead-letter handling, and audit-friendly transitions.
- Produces reproducible artifacts and daily human digest inputs.
- Normalizes malformed runtime inputs (command envelopes, labels, handoff fields) to fail safely.

## Current Status

This repository is in active implementation mode with runtime modules and tests landed.

- Detailed design and rollout context live in `SPEC.orchestrator-handoff.md`.
- Execution is tracked in Beads (`.beads/issues.jsonl`) with prefix `osm-`.
- Current quality gate: `pytest -q` (full watcher test suite).

## Repository Layout

- `SPEC.orchestrator-handoff.md`: full implementation spec and rollout model.
- `AGENTS.md`: agent operating protocol and required end-of-session workflow.
- `src/watcher/`: watcher runtime modules (FSM, parser, adapters, stores, policy, retry pipeline).
- `tests/`: unit and integration coverage for runtime contracts.
- `contracts/`: normative interface and schema contracts.
- `docs/oncall-runbook.md`: operator response and escalation playbook.
- `.beads/`: issue graph and dependency state.

## Prerequisites

- `git`
- `bd` (beads CLI)
- `python3` + `pytest`
- `jq` (recommended for JSON output filtering)

## Quick Start

```bash
git clone https://github.com/wboudy/orchestrator-state-machine.git
cd orchestrator-state-machine
bd onboard
pytest -q
bd ready
```

## Daily Workflow (Human)

1. Pick unblocked work:
   - `bd ready`
   - `bd show <id>`
2. Claim and execute:
   - `bd update <id> --status in_progress`
3. Close with evidence:
   - `bd close <id> --reason "Completed"`
4. Sync and push:
   - `git pull --rebase`
   - `bd sync`
   - `git push`

## Reliability Checks

Run these before handoff or after graph edits:

```bash
pytest -q
./tests/test_handoff_schema_validation.sh
bd dep cycles
bd doctor
```

## Recent Hardening

- Command adapter now normalizes `run_id`/`status` and coerces numeric-like `exit_code` safely.
- Label invariant guard now handles mixed-shape label payloads (string/list/dict/set) deterministically.
- Input ambiguity continues to fail closed to human escalation paths.

## Complex Blockers

When implementation hits a non-trivial blocker, use:

- `skills/bug-blocker-spinout/SKILL.md`
- `prompts/bead-swarm-long-horizon.md` for long-horizon swarm execution loops

This defines how to spin out a dedicated bug bead, block the parent bead, and switch focus safely.

## Troubleshooting Quick Hits

- `bd ready` is empty:
  - Check blockers with `bd show <id>` and `bd dep list <id>`.
- IDs or prefixes look inconsistent:
  - Run `bd doctor` first, then use migration commands only if doctor indicates mismatch.
- Bead changes not reflected in git:
  - Run `bd sync` and re-check `git status`.
