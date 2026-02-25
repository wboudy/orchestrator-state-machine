# Orchestrator Policy Schema Contract

This contract defines parser semantics for `.mycelium/orchestrator-policy.yaml`.

## Required Top-Level Keys

1. `timezone`
2. `business_hours`
3. `retry`
4. `risk_budget`
5. `dedupe`
6. `trust`

## Field Semantics and Invariants

### `timezone`

- Type: string
- Constraint: must be a non-empty IANA-style timezone string (`Region/City` shape).

### `business_hours`

- Type: object
- Required keys:
  - `weekdays`: list of weekday abbreviations (`Mon`..`Sun`)
  - `start`: `HH:MM` 24h
  - `end`: `HH:MM` 24h
- Invariants:
  - `weekdays` must not be empty
  - all weekday values must be valid abbreviations
  - `start` and `end` must be valid 24h times and `start < end` in same-day minutes

### `retry`

- Type: object
- Required keys:
  - `max_retries`: integer >= 0
  - `backoff_seconds`: non-empty list of positive integers
  - `jitter_pct`: integer 0..100

### `risk_budget`

- Type: object
- Required keys:
  - `max_noncritical_escalations_per_day`: integer >= 0
  - `max_noncritical_pages_per_hour`: integer >= 0

### `dedupe`

- Type: object
- Required keys:
  - `window_minutes`: integer > 0

### `trust`

- Type: object
- Required keys:
  - `initial_score`: number 0..1
  - `min_samples`: integer >= 1

## Strictness Rules

- Top-level unknown keys are invalid.
- Nested unknown keys are invalid.
- Validator aggregates all detected violations and returns them in one error.

## Parser Behavior

- Parser is strict for required keys and value types/ranges.
- Parser aggregates all validation failures and returns them together.
- On validation failure, parser raises `PolicyValidationError` with message prefix `POLICY_INVALID: ...`; caller must fail closed with `error_class=policy_invalid`.
- Default injection is out-of-scope for this parser contract (`osm-oh0.2`).

## Validation Artifacts

- Schema file: `contracts/orchestrator_policy.schema.json`
- Parser: `src/watcher/policy_contract.py`
- Tests: `tests/test_policy_contract.py`
