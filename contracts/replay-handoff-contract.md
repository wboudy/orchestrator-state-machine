# Replay Handoff Dry-Run Contract

This contract defines deterministic no-side-effect replay from run artifacts.

## Command

- `scripts/replay_handoff.py --run-file <path> --dry-run`

## Input

- Single-line JSONL run artifact file generated from `.beads/orchestrator-runs/<handoff_key>/<attempt>.jsonl`

## Behavior

1. Validate artifact against run-artifact schema.
2. Re-evaluate expected outcome deterministically from recorded fields:
   - `status=success` => expected `success`
   - `status=failure|partial` + `transition.to=HUMAN_REQUIRED` => expected `human_required`
   - otherwise => expected `retry`
3. Return parity result (`expected_result` vs recorded `transition.result`).
4. Perform no writes or external side effects.

## Output

- Machine-readable JSON with:
  - `dry_run`
  - `run_file`
  - `handoff_key`
  - `attempt`
  - `replay_result`
  - `expected_result`
  - `parity_match`
  - `checks`
