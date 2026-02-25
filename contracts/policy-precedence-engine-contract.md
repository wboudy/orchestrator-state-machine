# Policy Precedence Engine Contract

This contract defines deterministic evaluation order and fail-closed behavior.

## Evaluation Order (Normative)

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

## Inputs

- Policy validity, schema validity, FSM validity
- Retry counters and failure class
- Criticality, budget decision, business-hours decision, dedupe decision
- Signature trust score and optional sample counts

## Output

- `PrecedenceDecision`:
  - `result`: `retry|human_required|human_required_queued|human_required_suppressed`
  - `error_class`
  - `model_route`: `shallow|normal|deep|null`
  - `decision_path`: ordered step outcomes

## Fail-Closed Rule

If any required step input is missing/invalid or failure class is unknown,
engine returns:

- `result=human_required`
- `error_class=policy_ambiguous`

No retry or auto-routing action is emitted when ambiguity is present.
