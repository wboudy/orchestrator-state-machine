# Integration Guide

This guide explains how to embed `orchestrator-state-machine` into another project.

## What This Repo Is

This repository contains:

- Runtime modules in `src/watcher` (the real implementation)
- Contracts and tests (`contracts/`, `tests/`)
- Optional agent skills/prompts (`skills/`, `prompts/`) for development workflows

The runtime modules are the part you integrate into your product. Skills are optional.

## Integration Model

Treat this repo as a deterministic orchestration core. Your host project supplies:

- Bead/issue data source and updates
- Command execution adapter
- Policy config source
- Notification delivery backend

The watcher runtime supplies:

- Handoff parsing/validation (`handoff_parser.py`)
- Label invariant normalization (`label_invariants.py`)
- FSM transitions (`fsm.py`)
- Command envelope reconciliation (`command_adapter.py`)
- Retry/dead-letter logic (`retry_scheduler.py`, `retry_cooldown.py`, `dead_letter.py`)
- State/lease persistence helpers (`state_store.py`, `lease_lock.py`)
- Artifact and digest utilities

## How To Add It

Common options:

1. Git submodule or subtree under your mono-repo
2. Vendored copy of `src/watcher` + pinned commit SHA in your docs
3. Internal package wrapping `src/watcher` modules

Current tests assume import path via `src`. In host environments, ensure module resolution includes this path.

## Minimal Wiring Sequence

1. Fetch candidate work items from your tracker and map to `poll_loop.BeadSnapshot`
2. Use `poll_loop.select_eligible_queued(...)` to filter valid queued candidates
3. Acquire a lease with `LeaseLockManager.acquire(...)`
4. Parse handoff block via `parse_handoff_block(notes_text)`
5. Normalize labels via `validate_and_normalize_labels(labels)`
6. Load state record from `HandoffStateStore.load(handoff_key)`
7. Evaluate policy + retry budget (policy modules, risk budget store)
8. Execute transition using `execute_transition(...)`
9. Dispatch orchestrator command in your environment
10. Parse command envelope using `parse_command_envelope(...)`
11. Reconcile outcome with `reconcile_command_envelope(...)`
12. Persist new state via `HandoffStateStore.save/update_atomic(...)`
13. Emit run artifacts / watcher runs / notifications as needed
14. Release lease

## Fail-Closed Expectations

Your integration should preserve fail-closed behavior:

- Invalid handoff schema => no command dispatch, escalate to human path
- Ambiguous label state => escalate with `fsm_invalid`
- Non-retriable failures => `HUMAN_REQUIRED`
- Command envelope parse errors => failure path with explicit classification

## Persistence Surfaces

Typical persisted files used by modules:

- State store JSON (`state_store.py`)
- Lease lock JSON (`lease_lock.py`)
- Run artifacts JSONL (`run_artifact_emitter.py`)
- Watcher run append-only JSONL (`watcher_run_writer.py`)
- Risk budget and dedupe stores (`risk_budget_store.py`, `dedupe_store.py`)

Place these under a controlled writable directory (for example `.beads/` or app-specific state dir).

## Operational Checks

Recommended checks in CI or pre-deploy:

```bash
pytest -q
./tests/test_handoff_schema_validation.sh
```

For incident triage and replay:

- `docs/oncall-runbook.md`
- `python3 scripts/replay_handoff.py --run-file <path> --dry-run`

## Skills vs Runtime (FAQ)

- "Is this repo a skill?"
  - No. The runtime is the product (`src/watcher`).
- "Can I still use the skills?"
  - Yes. `skills/` helps agent workflows (bead swarm, blocker spinout), but runtime integration does not require them.
