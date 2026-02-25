# Dead-Letter Transition Contract

This contract defines escalation to dead-letter state when retrying is no longer valid.

## Triggers

- Retry budget exhausted (`retry_count >= max_retries`)
- Failure class is non-retriable

## Required Transition Effects

- FSM target state: `HUMAN_REQUIRED`
- Labels added: `orchestrator:dead`, `needs:human`
- `next_retry_at` cleared from persisted state
- `last_error_class` stored as normalized canonical class

## Non-Trigger Case

- Retriable failures with remaining budget do not dead-letter and continue retry flow.
