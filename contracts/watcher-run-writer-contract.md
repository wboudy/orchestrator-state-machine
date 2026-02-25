# Watcher Run Writer Contract

This contract defines schema validation and append-only persistence for `watcher_run`.

## Required Fields

- `handoff_key`
- `state_from`
- `state_to`
- `attempt`
- `result` (`success|retry|human_required`)
- `timestamp` (RFC3339 UTC)

## Optional Fields

- `error_class`
- `policy_version`
- `replay_artifact`
- `capsule_artifact`
- `risk_budget_decision` (`allow|defer|bypass-critical`)
- `signature_trust_score` (`0..1`)

## Invariants

- Unknown fields are rejected.
- Missing required fields are rejected.
- `handoff_key + attempt` must be unique in a log file.
- Write path is append-only and immutable (no in-place mutation/truncation).

## Storage

- Writer appends JSONL records to target log path.
- Writes are protected by file lock and fsync for durability.
