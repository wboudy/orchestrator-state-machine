# Run Artifact Emitter Contract

This contract implements Section 23.3 run artifact requirements.

## Required Fields

- `timestamp`
- `handoff_key`
- `attempt`
- `inputs`
- `decision_path`
- `command_envelope`
- `transition`

## Validation Rules

- `inputs` must include: `labels`, `notes_snapshot_hash`, `policy_hash`, `local_time_eval`.
- `command_envelope` must include: `run_id`, `exit_code`, `status`.
- `transition` must include: `from`, `to`, `result`.
- Enumerated values are strictly validated (`status`, states, transition result).

## Storage Rules

- File path: `.beads/orchestrator-runs/<handoff_key>/<attempt>.jsonl`
- One immutable JSONL record per attempt file.
- Existing attempt file cannot be overwritten (`O_EXCL` creation).
