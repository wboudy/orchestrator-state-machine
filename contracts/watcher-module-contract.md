# Watcher Runtime Module Contract

This contract defines module boundaries, public interfaces, and lifecycle rules for WP-1/WP-2 core watcher runtime.

## Scope

- Deterministic poll/claim/transition loop
- Strict handoff schema validation before execution
- Lease lock and idempotent state interactions
- Fail-closed behavior for ambiguous/invalid input

## Module Boundaries

| Module | Responsibility | Must Not Do |
|---|---|---|
| `watcher.queue_scanner` | Poll candidate beads and extract potential handoff blocks. | Execute transitions directly. |
| `watcher.handoff_parser` | Parse/validate handoff payload and return normalized object. | Mutate bead labels/state. |
| `watcher.fsm_engine` | Enforce transition preconditions and compute next state/action. | Read raw notes directly. |
| `watcher.lock_manager` | Acquire/renew/release lease lock and detect stale owners. | Decide policy/escalation behavior. |
| `watcher.state_store` | Read/write idempotency state keyed by `handoff_key`. | Perform command dispatch. |
| `watcher.invariant_guard` | Validate label/state invariants and normalize/stop if invalid. | Bypass fail-closed rules. |

## Public Interfaces

```text
queue_scanner.find_candidates(now_utc, limit) -> list[BeadSnapshot]
handoff_parser.parse_and_validate(notes_text) -> HandoffPayload | ValidationError
fsm_engine.plan_transition(snapshot, handoff, state_record, policy_eval) -> TransitionPlan
lock_manager.acquire(owner_id, now_utc) -> LeaseHandle | LockBusy
lock_manager.heartbeat(lease_handle, now_utc) -> LeaseHandle | LeaseExpired
lock_manager.release(lease_handle) -> bool
state_store.load(handoff_key) -> StateRecord | None
state_store.save(handoff_key, state_record, expected_version) -> SaveResult
invariant_guard.check(snapshot) -> InvariantOk | InvariantViolation
```

## Core Data Types

```text
HandoffPayload:
  origin_id: string
  bug_id: string
  error_signature: string
  expected_minutes: int
  estimated_loc: int
  touches_api_or_schema: bool
  touches_security_or_auth: bool
  quick_test_available: bool

StateRecord:
  state: QUEUED|RUNNING|RETRY_WAIT|DONE|HUMAN_REQUIRED
  attempt: int
  last_transition_at: RFC3339 UTC timestamp
  next_retry_at: RFC3339 UTC timestamp|null
  last_error_class: string|null
  owner_id: string|null
```

## Lifecycle Contract

1. `queue_scanner` returns candidate.
2. `lock_manager.acquire` must succeed before processing candidate.
3. `handoff_parser.parse_and_validate` must pass before any transition command.
4. `invariant_guard.check` runs before transition planning.
5. `fsm_engine.plan_transition` returns deterministic transition/action.
6. `state_store.save` commits state change atomically with optimistic version check.
7. `lock_manager.heartbeat` is renewed while work is active; release at cycle end.

## Invariants

- A bead cannot be in `RUNNING` and `DONE` labels simultaneously.
- A `handoff_key` cannot have two active owners.
- A transition requiring command dispatch cannot run without a valid `HandoffPayload`.
- Invalid/ambiguous input always fails closed to `HUMAN_REQUIRED`.

## Invalid Input Behavior

- Missing or malformed handoff block:
  - classify `error_class=schema_invalid`
  - add `needs:human`
  - do not dispatch orchestrator command
- Schema field violation:
  - no retries
  - transition to `HUMAN_REQUIRED`
  - append run artifact describing violated fields

## Validation Artifact

- Normative schema file: `contracts/handoff.schema.json`
- Validator: `scripts/validate_handoff_schema.sh`
- Test: `tests/test_handoff_schema_validation.sh`
