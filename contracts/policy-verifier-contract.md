# Policy Static Verifier Contract

This contract defines static startup checks for policy-as-code safety.

## Input

- Raw policy mapping (possibly partial).
- Optional precedence-order sequence override.

## Processing

1. Inject canonical defaults and validate resulting policy structure.
2. Reject unreachable FSM configurations.
3. Reject conflicting escalation-rule configurations.
4. Reject ambiguous precedence definitions.

## Required Checks

### Unreachable State

- `retry.max_retries < 1` is invalid because `RETRY_WAIT` becomes unreachable.

### Escalation Conflict

- `risk_budget.max_noncritical_escalations_per_day == 0` with
  `risk_budget.max_noncritical_pages_per_hour > 0` is invalid.

### Ambiguous Precedence

Precedence order must match exactly:

1. `policy_load_parse`
2. `schema_validity`
3. `fsm_invariants`
4. `dead_letter_guard`
5. `failure_class_retryable`
6. `criticality_bypass`
7. `risk_budget`
8. `time_window_routing`
9. `dedupe_suppression`
10. `signature_trust_routing`

Any duplicate, missing step, unknown step, or out-of-order sequence is invalid.

## Output

- `PolicyVerificationResult` with deterministic `errors` and `warnings`.
- `ok=true` only when zero errors are present.
- Startup hard-fail path uses `verify_policy_or_raise`.
