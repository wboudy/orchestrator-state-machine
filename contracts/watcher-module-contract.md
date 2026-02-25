# Watcher Runtime Module Contract

This contract defines module boundaries, public interfaces, and lifecycle rules for the watcher runtime.

## Scope

- Deterministic poll/claim/transition loop
- Strict handoff schema validation before execution
- Lease lock and idempotent state interactions
- Fail-closed behavior for ambiguous/invalid input

## Module Boundaries

| Module | Responsibility | Must Not Do |
|---|---|---|
| `watcher.poll_loop` | Select eligible queued beads with valid handoff blocks. | Mutate bead labels/state directly. |
| `watcher.handoff_parser` | Parse/validate handoff payload and return normalized object. | Dispatch commands or update bead state. |
| `watcher.label_invariants` | Normalize mixed-shape labels and enforce state-label invariants. | Bypass human-escalation fail-closed path. |
| `watcher.fsm` | Enforce transition preconditions and compute next state/action labels. | Parse raw note content. |
| `watcher.command_adapter` | Normalize command envelopes and reconcile status/exit-code mismatches. | Decide retry cadence directly. |
| `watcher.lease_lock` | Acquire/heartbeat/release lease ownership for active work. | Classify policy/error outcomes. |
| `watcher.state_store` | Persist idempotent state records with optimistic version checks. | Execute orchestration commands. |

## Public Interfaces

```text
poll_loop.select_eligible_queued(snapshots, limit) -> list[BeadSnapshot]
handoff_parser.parse_handoff_block(notes_text) -> HandoffPayload | HandoffValidationError
label_invariants.validate_and_normalize_labels(labels) -> InvariantResult
fsm.execute_transition(current_state, event, ...) -> TransitionResult
command_adapter.parse_command_envelope(payload) -> CommandEnvelope
command_adapter.reconcile_command_envelope(envelope, terminal_success_observed) -> CommandReconciliation
lease_lock.LeaseLockManager.acquire(owner_id, now_utc) -> LeaseRecord | LeaseBusyError
lease_lock.LeaseLockManager.heartbeat(owner_id, now_utc) -> LeaseRecord | LeaseExpiredError
lease_lock.LeaseLockManager.release(owner_id) -> bool
state_store.HandoffStateStore.load(handoff_key) -> StateRecord | None
state_store.HandoffStateStore.save(handoff_key, record, expected_version) -> SaveResult
state_store.HandoffStateStore.update_atomic(handoff_key, expected_version, fn) -> SaveResult
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

Identifier constraints:
- `origin_id` and `bug_id` MUST match `^[a-z0-9][a-z0-9.-]{1,63}$` (dotted child bead IDs are valid).

StateRecord:
  state: QUEUED|RUNNING|RETRY_WAIT|DONE|HUMAN_REQUIRED
  attempt: int
  last_transition_at: RFC3339 UTC timestamp
  next_retry_at: RFC3339 UTC timestamp|null
  last_error_class: string|null
  owner_id: string|null
  version: int
```

## Lifecycle Contract

1. `poll_loop` selects candidates with `needs:orchestrator` and valid handoff schema.
2. `lease_lock.acquire` must succeed before processing a candidate.
3. `handoff_parser.parse_handoff_block` must pass before transition planning.
4. `label_invariants.validate_and_normalize_labels` runs before FSM decisions.
5. `fsm.execute_transition` computes deterministic label/state changes.
6. `command_adapter.parse_command_envelope` and `reconcile_command_envelope` normalize command outcomes.
7. `state_store.save/update_atomic` commits state changes with version checks.
8. `lease_lock.heartbeat` is renewed during work; lease is released at cycle end.

## Invariants

- A bead cannot have ambiguous primary state labels.
- A `handoff_key` cannot have two active owners.
- A transition requiring command dispatch cannot run without a valid `HandoffPayload`.
- Invalid/ambiguous input fails closed to `HUMAN_REQUIRED` (`needs:human`).

## Invalid Input Behavior

- Missing or malformed handoff block:
  - classify `error_class=schema_invalid`
  - add `needs:human`
  - do not dispatch orchestrator command
- Invalid command envelope payload:
  - reject envelope parse
  - treat as failure path and escalate per classifier/FSM policy
- Ambiguous label state:
  - normalize safe known combinations
  - otherwise escalate with `error_class=fsm_invalid`

## Validation Artifacts

- Normative handoff schema: `contracts/handoff.schema.json`
- Validator script: `scripts/validate_handoff_schema.sh`
- Contract tests: `tests/test_handoff_schema_validation.sh`
