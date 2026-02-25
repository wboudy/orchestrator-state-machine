# Orchestrator Handoff and Escalation Spec
Version: 0.5
Status: Draft

## 1. Purpose

Define how mid-implementation bug interrupts are routed safely:

1. Preserve the existing Mycelium workflow and skill context.
2. Add watcher-driven orchestration for `model:deep` bug beads.
3. Prevent alert fatigue with trivial-fix gating and time-aware escalation.
4. Prevent infinite orchestration loops with explicit FSM + retry limits.

## 2. Relationship to Existing Workflow

This is not a replacement for existing skills. It is a control-plane extension.

- `mycelium-bug-interrupt` skill:
  - Splits blocker into bug bead.
  - Blocks origin bead.
  - Labels bug bead (`model:deep`, `needs:orchestrator`).
- Watcher (new):
  - Detects and routes queued beads.
  - Enforces FSM, retries, cooldown, escalation policy.
- Orchestrator runner (existing/new command wrapper):
  - Executes the routed bead using configured model.

## 3. System Components

| Component | Responsibility |
|---|---|
| Worker Skill | Emits structured handoff intent on bug bead |
| Watcher Loop | Polls `bd` for queued handoffs and drives state transitions |
| Locking | Ensures only one watcher claims a handoff at a time |
| Orchestrator Command | Runs the selected model for one bead |
| Escalation Sink | Marks `needs:human` and optionally sends notification |

### 3.1 Normative Language

The keywords `MUST`, `MUST NOT`, `SHOULD`, `SHOULD NOT`, and `MAY` are used as normative requirements.

## 4. Handoff Signals

### 4.1 Required Labels on Spawned Bug Bead

- `interrupt`
- `root-cause`
- `model:deep`
- `needs:orchestrator`

### 4.2 Optional Labels

- `triage:trivial-candidate` (worker believes inline/cheap fix is plausible)
- `customer-impact` (enables off-hours high-priority paging)

### 4.3 Required Notes Block

Worker appends a structured block to bead notes:

```yaml
handoff:
  origin_id: <origin-bead-id>
  bug_id: <bug-bead-id>
  error_signature: <stable-short-signature>
  expected_minutes: <int>
  estimated_loc: <int>
  touches_api_or_schema: <bool>
  touches_security_or_auth: <bool>
  quick_test_available: <bool>
```

If this block is missing, watcher treats the bead as non-trivial.

### 4.4 Handoff Schema Constraints (Normative)

All required handoff fields MUST pass these checks before any execution:

| Field | Type | Constraint |
|---|---|---|
| `origin_id` | string | `^[a-z0-9][a-z0-9.-]{1,63}$` |
| `bug_id` | string | `^[a-z0-9][a-z0-9.-]{1,63}$` |
| `error_signature` | string | 8..128 chars, lowercase `[a-z0-9:_-]` |
| `expected_minutes` | integer | 1..480 |
| `estimated_loc` | integer | 1..5000 |
| `touches_api_or_schema` | boolean | strict boolean |
| `touches_security_or_auth` | boolean | strict boolean |
| `quick_test_available` | boolean | strict boolean |

If validation fails, watcher MUST set `needs:human` and `error_class=schema_invalid`, and MUST NOT invoke orchestrator command.

Note: dotted child bead IDs (for example `osm-4x3.1`) are valid for `origin_id` and `bug_id`.

## 5. Finite State Machine

State is represented using labels and retry metadata in notes.

### 5.1 States

| State | Label Contract |
|---|---|
| `QUEUED` | `needs:orchestrator` present, `orchestrator:running` absent |
| `RUNNING` | `orchestrator:running` present |
| `RETRY_WAIT` | `orchestrator:failed` present and retry cooldown active |
| `DONE` | `orchestrator:done` present, `needs:orchestrator` absent |
| `HUMAN_REQUIRED` | `needs:human` present |

### 5.2 Transitions

1. `QUEUED -> RUNNING`
   - Preconditions: watcher lock acquired, bead claim succeeds.
   - Actions: add `orchestrator:running`, remove `needs:orchestrator`.
2. `RUNNING -> DONE`
   - Preconditions: orchestrator returns success.
   - Actions: remove `orchestrator:running`, add `orchestrator:done`.
3. `RUNNING -> RETRY_WAIT`
   - Preconditions: orchestrator fails and retry_count < max_retries.
   - Actions: remove `orchestrator:running`, add `orchestrator:failed` + cooldown metadata.
4. `RUNNING/RETRY_WAIT -> HUMAN_REQUIRED`
   - Preconditions: retry_count >= max_retries, or failure classified as non-retriable.
   - Actions: add `needs:human`, remove `needs:orchestrator` and `orchestrator:running`.

### 5.3 Label Invariants (Normative)

1. Exactly one of these labels MAY be active at any time:
   - `needs:orchestrator`
   - `orchestrator:running`
   - `orchestrator:failed`
   - `orchestrator:done`
   - `orchestrator:dead`
2. `needs:human` MAY co-exist only with:
   - `orchestrator:dead`
   - `orchestrator:failed`
3. Invalid combinations (for example `orchestrator:running` + `orchestrator:done`) MUST trigger `fsm_invalid` handling:
   - auto-normalize only when deterministic
   - otherwise escalate to `needs:human`.

## 6. Trivial Fix Policy

Goal: keep humans out of low-risk noise.

Watcher auto-resolves without escalation only when all are true:

1. `expected_minutes <= 10`
2. `estimated_loc <= 30`
3. `touches_api_or_schema == false`
4. `touches_security_or_auth == false`
5. `quick_test_available == true`
6. Attempts so far <= 2

If any check fails, route through standard orchestrator flow.

## 7. Retry and Loop Prevention

### 7.1 Retry Defaults

- `max_retries = 3`
- Backoff schedule: `1m`, `5m`, `15m`
- Jitter: uniform `-15%..+15%`
- Retry class mapping:
  - retriable: `timeout`, `rate_limited`, `upstream_unavailable`, `network_error`, `state_conflict`, `stale_run`, `unknown_error`
  - non-retriable: `schema_invalid`, `auth_failed`, `permission_denied`, `bad_input`, `policy_invalid`

### 7.2 Loop Guards

1. Single active watcher via lock file (for example `.beads/orchestrator-watch.lock`).
2. Idempotency key:
   - `handoff_key = sha1(origin_id + ":" + bug_id + ":" + error_signature)`
3. Never process bead in `RUNNING` or `DONE`.
4. Do not requeue a `HUMAN_REQUIRED` bead automatically.

## 8. Human Escalation Policy

### 8.1 Escalation Triggers

- Retry budget exhausted.
- Non-retriable failure class (auth, permissions, malformed input).
- Explicit high-risk flags from triage.

### 8.2 Time-Aware Notification

- Business hours (default local weekday `09:00-18:00`):
  - Raise `needs:human` immediately.
- Off-hours:
  - Immediate human notification only for P0/P1 or `customer-impact`.
  - Else queue (`notify:queued`) and schedule next business-hour notification.
- Business-hours interval semantics: local time `[start, end)` (start inclusive, end exclusive).
- Timezone source: policy IANA timezone (`orchestrator-policy.yaml`), default `America/New_York`.
- Day-boundary for counters/budgets: local midnight in policy timezone.
- Holidays are out of scope in v1; weekends are off-hours.

### 8.3 Human Reach-Out Channels

Minimum required: bead labels + notes (`needs:human`, structured failure summary).

Optional integrations:
- Slack webhook
- Email endpoint
- Pager for critical severities only

## 9. Command Contract (Watcher)

Watcher executes a configured command template per claimed bead:

```bash
<orchestrator_cmd> --bead-id <bug_id> --model deep
```

Notes:
- Actual command remains configurable to avoid coupling this spec to one CLI shape.
- Watcher must capture exit code and append summary notes.
- Command envelope MUST include:
  - `run_id`
  - `exit_code`
  - `status` (`success|failure|partial`)
  - optional `error_class`
- `partial` MUST be treated as failure unless post-run reconciliation proves terminal success.

## 10. Observability

Watcher appends machine-parseable notes per attempt:

```yaml
watcher_run:
  handoff_key: <hash>
  state_from: <state>
  state_to: <state>
  attempt: <int>
  result: success|retry|human_required
  error_class: <optional>
  policy_version: <optional-policy-hash>
  replay_artifact: <optional-run-file-path>
  capsule_artifact: <optional-repro-capsule-path>
  risk_budget_decision: <optional-allow|defer|bypass-critical>
  signature_trust_score: <optional-0-to-1>
  timestamp: <ISO-8601 UTC>
```

`watcher_run` MUST be append-only and immutable after write.

## 11. Acceptance Criteria

1. Bug beads labeled `needs:orchestrator` are claimed and routed exactly once per attempt.
2. FSM transitions are valid and auditable in bead labels/notes.
3. A failing handoff never retries more than `max_retries`.
4. `needs:human` is set automatically when retry budget is exhausted.
5. Off-hours policy suppresses non-critical immediate paging.
6. Original implementation bead remains blocked until blocker bug is closed.
7. Daily digest is generated and delivered during business hours with escalation summary.
8. Duplicate human notifications for same signature are suppressed within dedupe window.
9. Stale `RUNNING` beads are auto-reconciled without manual intervention.
10. Watcher policy is loaded from versioned config and passes static validation before startup.
11. Any executed handoff attempt is replayable in deterministic dry-run mode.
12. Daily digest includes incident clusters with blast-radius ordering.
13. Failed or escalated handoffs include a sanitized reproducibility capsule.
14. Human escalation flow respects configurable daily risk budget with critical bypass.
15. Model-routing decisions incorporate signature trust history and are auditable.
16. Invalid label combinations are auto-normalized or escalated via deterministic `fsm_invalid` rules.
17. Retry behavior follows class-based retriable/non-retriable taxonomy and jittered schedule.
18. Policy precedence order is deterministic and test-verified.
19. Reproducibility capsules enforce redaction rules and fail closed on redaction errors.
20. Risk-budget counters reset at local midnight in policy timezone.

## 12. Out of Scope (This Spec)

- Full implementation of notification providers.
- Model-specific prompt engineering details.
- Replacing existing manual `mycelium-next` workflow.

## 13. Next Implementation Steps

1. Add watcher script (`src/mycelium/handoff_watcher.py`).
2. Add CLI command (`mycelium-py watch-handoffs`).
3. Add tests:
   - FSM transitions
   - Retry ceilings
   - Off-hours escalation routing
   - Trivial-fix gate behavior
4. Update `mycelium-bug-interrupt` to emit required handoff block.

## 14. Detailed Implementation Plan

### 14.1 Phase 1: Core Reliability

1. Replace basic lock with lease lock + heartbeat.
   - Lock file: `.beads/orchestrator-watch.lock`
   - Lease fields: `owner_id`, `pid`, `started_at`, `last_heartbeat`
   - Heartbeat interval: 10s
   - Stale lease timeout: 45s
2. Add persistent idempotency store.
   - File: `.beads/orchestrator-handoff-state.json`
   - Keys: `handoff_key`, `state`, `attempt`, `last_transition_at`
   - Required invariant: same `handoff_key` cannot execute concurrently.
3. Add stale-run reconciler pass before each poll iteration.
   - If bead labeled `orchestrator:running` and heartbeat stale:
     - transition to `RETRY_WAIT`
     - append recovery note
4. Enforce strict handoff schema validation.
   - Missing required fields => `needs:human` with `error_class=schema_invalid`
   - No execution attempt allowed on invalid payload.
5. Add dead-letter state.
   - Label: `orchestrator:dead`
   - Enter when retry cap reached or hard non-retriable failure occurs.
   - Must always co-occur with `needs:human`.

### 14.2 Phase 2: Signal Quality and Human Load Control

1. Add notification dedupe window.
   - Key: `origin_id + error_signature + error_class`
   - Suppression window: 60 minutes
2. Add daily human digest.
   - Delivery window: next business-hour window (default 09:30 local)
   - Content:
     - New escalations
     - Dead-letter items
     - Top recurring signatures
     - Retry trend and success ratio
3. Add off-hours queuing policy.
   - P0/P1 or `customer-impact`: immediate notify
   - P2+: queue for digest unless explicit urgent override
4. Add escalation priority scoring for digest order.
   - Inputs: priority, customer-impact, retries, age
   - Output: deterministic sort for human triage.

### 14.3 Phase 3: Adaptive and Advanced Behaviors

1. Add shadow mode.
   - Watcher computes transitions and logs "would-run" outcomes without execution.
   - Exit criterion: 7-day false-positive rate under threshold.
2. Add trivial-fix confidence scoring.
   - Start rule-based; persist prediction vs outcome.
   - Track precision/recall weekly for threshold tuning.
3. Add adaptive retry backoff.
   - Repeated identical transient infra failures => longer cooldown.
   - Unique/first-time transient failures => default schedule.
4. Add daily quality report.
   - Metrics:
     - Auto-resolve rate
     - Human escalation rate
     - Mean time to recovery
     - Loop prevention interventions

### 14.4 Selected Enhancements (Top 3)

The following three additions were selected after evaluating ten candidates.

1. Policy-as-code with static verifier.
   - Source file: `.mycelium/orchestrator-policy.yaml`
   - Startup hard-fail conditions:
     - unreachable FSM states
     - conflicting escalation rules
     - overlapping time-window rules without precedence
   - Persist policy hash in every `watcher_run.policy_version`.
2. Deterministic replay harness ("flight recorder").
   - Persist per-attempt run artifact:
     - `.beads/orchestrator-runs/<handoff_key>/<attempt>.jsonl`
   - Artifact must include:
     - labels and notes snapshot
     - evaluated policy hash
     - local-time window decision path
     - orchestrator command envelope (exit code, parsed status)
   - Add command:
     - `mycelium-py replay-handoff --run-file <path> --dry-run`
3. Incident-cluster digest intelligence.
   - Build derived incident graph keyed by `error_signature`.
   - Cluster features:
     - connected origin beads
     - affected components (if labeled)
     - escalation outcomes and age
   - Daily digest ordering:
     - cluster risk first (priority, spread, age, human impact)

### 14.5 Selected Enhancements (Top 3, New Iteration)

1. Reproducibility capsule generator.
   - For every failure or escalation, persist a sanitized capsule:
     - `.beads/orchestrator-capsules/<handoff_key>/<attempt>.md`
   - Capsule must include:
     - minimal reproduction steps
     - observed vs expected behavior
     - exact command envelope and key logs
     - environment metadata (timezone, policy hash, run id)
   - Capsule path is recorded in `watcher_run.capsule_artifact`.
2. Daily human risk-budget governor.
   - Add policy knobs:
     - `max_noncritical_escalations_per_day`
     - `max_noncritical_pages_per_hour`
   - Decision rules:
     - critical (`P0/P1` or `customer-impact`) always bypass budget
     - noncritical over-budget items are deferred to digest queue
   - Decision is recorded in `watcher_run.risk_budget_decision`.
3. Signature trust ledger for routing.
   - Persist per-signature historical outcomes:
     - auto-resolve success rate
     - mean retries
     - human-escalation rate
   - Use score to route:
     - high trust => cheaper/shallower path first
     - low trust => deep model earlier + stricter guardrails
   - Score is recorded in `watcher_run.signature_trust_score`.

## 15. Deterministic Policy Precedence

When multiple rules apply, watcher MUST evaluate in this exact order:

1. Policy load and parse validity
2. Schema validity (`handoff` + current state readability)
3. FSM invariant validity
4. Dead-letter / max retry guard
5. Failure-class retriable decision
6. Criticality (`P0/P1` or `customer-impact`) bypass
7. Risk-budget checks
8. Time-window routing (business/off-hours)
9. Dedupe suppression
10. Signature-trust routing choice

If any step cannot be evaluated deterministically, watcher MUST fail closed to `needs:human` with `error_class=policy_ambiguous`.

## 16. Canonical Defaults (Normative)

| Key | Default |
|---|---|
| `timezone` | `America/New_York` |
| `business_hours` | `Mon-Fri 09:00-18:00` |
| `max_retries` | `3` |
| `retry_backoff_seconds` | `[60, 300, 900]` |
| `retry_jitter_pct` | `15` |
| `dedupe_window_minutes` | `60` |
| `max_noncritical_escalations_per_day` | `20` |
| `max_noncritical_pages_per_hour` | `5` |
| `initial_signature_trust` | `0.5` |
| `signature_min_samples` | `5` |

Policy file values override defaults. Missing values MUST fall back to these defaults.

## 17. Algorithm Specifications

### 17.1 Retry Delay

For attempt `n` (1-indexed):

1. `base = retry_backoff_seconds[min(n-1, len(retry_backoff_seconds)-1)]`
2. `jitter_factor = 1 + U(-jitter_pct, +jitter_pct)`
3. `delay = round(base * jitter_factor)`
4. `next_retry_at = now_utc + delay`

### 17.2 Signature Trust Score

For a signature with `S=auto_resolve_successes`, `H=human_escalations`:

`trust = (S + 1) / (S + H + 2)`

Routing policy:
- if samples `< signature_min_samples`: treat as neutral (`0.5`)
- `trust >= 0.75`: shallow/cheaper route first
- `0.45 <= trust < 0.75`: normal route
- `trust < 0.45`: deep route first + strict guardrails

### 17.3 Incident Cluster Risk Score

Cluster score used for digest sorting:

`score = priority_weight + spread_weight + age_weight + human_weight`

Where:
- `priority_weight`: `P0=8, P1=5, P2=3, P3=1, P4=0`
- `spread_weight`: number of unique origin beads in cluster
- `age_weight`: `min(cluster_age_days, 7)`
- `human_weight`: `2 * unresolved_needs_human_count`

Higher score appears earlier in digest.

## 18. Reproducibility Capsule Redaction Rules

Capsule generation MUST redact sensitive material before write:

1. Redact values for keys matching case-insensitive patterns:
   - `token`, `secret`, `password`, `api_key`, `authorization`, `cookie`
2. Redact bearer/basic auth strings in logs and command envelopes.
3. Replace filesystem home prefixes with `<HOME>` when outside project root appears.
4. If redaction step fails, watcher MUST:
   - avoid writing raw capsule
   - escalate `needs:human` with `error_class=redaction_failed`.

## 19. Ambiguity and Fail-Closed Rules

Watcher MUST fail closed (no auto-execution) when any of the following occur:

1. Missing or malformed required handoff fields.
2. Multiple active orchestrator state labels.
3. Unresolved policy conflict or unknown precedence outcome.
4. Non-deterministic replay inputs (missing run artifact fields).
5. Clock/timezone evaluation failure.

Fail-closed action:
- set `needs:human`
- append structured `watcher_run` with `result=human_required`
- include specific `error_class`
- stop processing that handoff for current cycle.

## 20. Failure Modes and Mitigation Plan

### 20.1 Two Watchers Claim Same Bead

- Failure mode: duplicate execution due to race.
- Prevention:
  - Lease lock with heartbeat.
  - Atomic claim transition: add `orchestrator:running` and remove `needs:orchestrator` in one guarded update.
- Detection:
  - Invariant check: no bead may have multiple active watcher owners.
  - Alert on duplicate `RUNNING` notes for same `handoff_key`.
- Recovery:
  - Keep earliest owner; demote later owner attempt to no-op.
  - Append conflict note and continue with single owner.

### 20.2 Stuck `RUNNING` After Crash/Reboot

- Failure mode: orphaned in-flight state blocks progress.
- Prevention:
  - Heartbeat required while running.
  - Max run duration per attempt (for example 20m).
- Detection:
  - Reconciler identifies stale heartbeat or exceeded runtime.
- Recovery:
  - Transition to `RETRY_WAIT` with `error_class=stale_run`.
  - Increment attempt and schedule backoff.

### 20.3 Origin/Bug Loop Due to Dependency Cleanup Drift

- Failure mode: bug closes but origin remains blocked or re-enters interrupt loop repeatedly.
- Prevention:
  - Resume workflow must remove dependency and set origin `in_progress`.
  - Enforce max re-interrupt count per origin+signature.
- Detection:
  - Repeated interrupts with same signature over threshold.
  - Closed bug with origin still blocked beyond grace period.
- Recovery:
  - Auto-open follow-up bead with `needs:human`.
  - Mark pair as circuit-broken; stop auto re-interrupt for that signature.

### 20.4 Timezone/DST Escalation Mistakes

- Failure mode: notifications sent in wrong window.
- Prevention:
  - Store schedule in explicit IANA timezone, not UTC offsets.
  - Normalize all internal timestamps to UTC + timezone conversion at evaluation.
- Detection:
  - Emit evaluated window metadata in logs (`local_time`, `tz`, `policy_path`).
  - Add DST boundary tests.
- Recovery:
  - If schedule ambiguity detected, fall back to safe mode:
    - queue non-critical
    - immediately notify critical.

### 20.5 Partial Success with Non-Zero Exit

- Failure mode: orchestrator changed bead state but process exits as failure.
- Prevention:
  - Command contract must support structured status output (success/failure + action id).
  - Idempotent side effects keyed by `handoff_key` + `attempt`.
- Detection:
  - Post-run state reconciliation compares expected vs actual labels/notes.
- Recovery:
  - If state indicates success, transition to `DONE` and record `result=success_with_exit_mismatch`.
  - Else treat as retriable failure.

### 20.6 Manual Label Edits Break FSM Invariants

- Failure mode: impossible combinations (for example `needs:orchestrator` + `orchestrator:done`).
- Prevention:
  - Invariant validator runs each loop and before transitions.
  - Optional protected-label policy for orchestrator-owned labels.
- Detection:
  - Validator emits `fsm_invalid` with full label snapshot.
- Recovery:
  - Auto-normalize to nearest valid state when unambiguous.
  - Escalate to `needs:human` when ambiguous.

### 20.7 `bd` Staleness and Sync Inconsistency

- Failure mode: watcher acts on stale issue view.
- Prevention:
  - Poll cycle includes `bd sync --status` health check.
  - Use monotonic snapshot token and skip processing when stale warning present.
- Detection:
  - Mismatch between local bead state and command write result.
  - Repeated optimistic-update failures.
- Recovery:
  - Refresh state, retry once with jitter.
  - If mismatch persists, set `needs:human` with `error_class=state_divergence`.

## 21. Additional Test Matrix

1. Lease handoff race simulation with two watcher instances.
2. Crash/restart stale heartbeat reconciliation.
3. DST transition cases for off-hours policy.
4. Duplicate notification suppression in dedupe window.
5. Partial-success exit mismatch reconciliation.
6. Manual label corruption auto-normalization.
7. Dead-letter transition after max retries.
8. Daily digest generation with mixed severities and dedupe.
9. Policy verifier rejects contradictory or unreachable rule sets.
10. Replay harness reproduces identical transitions under deterministic inputs.
11. Incident-cluster digest groups related signatures and ranks by blast radius.
12. Reproducibility capsule generation validates completeness and redaction rules.
13. Risk-budget governor enforces quotas while always allowing critical bypass.
14. Signature trust ledger updates deterministically and changes routing as expected.
15. Policy precedence order is enforced exactly and tested against conflict cases.
16. Invalid label-set combinations trigger deterministic `fsm_invalid` handling.
17. Retry classifier sends non-retriable classes directly to human-required state.
18. Capsule redaction failure never writes unredacted content.
19. Default policy fallback values are used when policy keys are absent.
20. Timezone/day-boundary handling resets budgets at local midnight.

## 22. Implementation Work Packages

### 22.1 WP-1: Core Watcher Engine

Goal: implement deterministic FSM processing loop.

Tasks:
1. Implement poll loop with configurable interval (`poll_seconds`, default `15`).
2. Implement handoff loader and schema validator (Section 4.4).
3. Implement state transition executor for Section 5 transitions.
4. Implement invariant validator for Section 5.3.
5. Implement fail-closed behavior for Section 19.

Exit Criteria:
1. All Section 5 transitions are executable and tested.
2. Invalid states are normalized or escalated deterministically.
3. No handoff runs without valid schema.

### 22.2 WP-2: Lease Locking and Idempotency

Goal: prevent duplicate execution and recover from stale runs.

Tasks:
1. Implement lease file lifecycle at `.beads/orchestrator-watch.lock`.
2. Implement heartbeat writer and stale lease detector.
3. Implement idempotency state store at `.beads/orchestrator-handoff-state.json`.
4. Implement stale `RUNNING` reconciler and retry transition.

Exit Criteria:
1. Two concurrent watchers cannot execute same handoff.
2. Stale lease recovery is automatic without manual cleanup.
3. Repeated processing of same `handoff_key` is idempotent.

### 22.3 WP-3: Policy Engine and Defaults

Goal: make routing and escalation policy deterministic.

Tasks:
1. Implement loader for `.mycelium/orchestrator-policy.yaml`.
2. Implement default fallback injection (Section 16).
3. Implement static policy verifier checks:
   - unreachable states
   - conflicting escalation rules
   - ambiguous time-window precedence
4. Implement precedence evaluation order (Section 15).

Exit Criteria:
1. Watcher fails startup on invalid policy.
2. Precedence order is logged and replayable for each attempt.
3. Missing policy keys use canonical defaults.

### 22.4 WP-4: Retry and Error Classifier

Goal: standardize failure handling and backoff behavior.

Tasks:
1. Implement error classifier to retriable/non-retriable taxonomy.
2. Implement jittered backoff formula (Section 17.1).
3. Persist `next_retry_at` and enforce cooldown gating.
4. Implement dead-letter transition to `orchestrator:dead`.

Exit Criteria:
1. Non-retriable errors bypass retries and escalate.
2. Retriable errors obey configured schedule with jitter.
3. Retry budget cap is enforced exactly.

### 22.5 WP-5: Observability, Replay, and Capsules

Goal: make each decision auditable and reproducible.

Tasks:
1. Implement append-only `watcher_run` writer.
2. Implement replay artifact emitter (`.beads/orchestrator-runs/...`).
3. Implement `replay-handoff` CLI dry-run command.
4. Implement capsule generator with redaction rules (Section 18).

Exit Criteria:
1. Every executed attempt has replay artifact path.
2. Replay reproduces same transition outcome under deterministic input.
3. Redaction failure fails closed and never writes raw sensitive data.

### 22.6 WP-6: Escalation, Digest, and Risk Budget

Goal: control human notification load while preserving critical signal.

Tasks:
1. Implement critical bypass logic.
2. Implement noncritical daily/hourly budget enforcement.
3. Implement dedupe suppression window.
4. Implement daily digest builder with incident-cluster sorting.
5. Implement notification transport interface (bead-native required, optional email/slack/pager).

Exit Criteria:
1. Critical incidents bypass budget and notify immediately.
2. Noncritical incidents over budget are deferred and appear in digest.
3. Digest ordering matches Section 17.3 risk scoring.

### 22.7 WP-7: Integration with Worker and Orchestrator

Goal: wire existing workflows to watcher contracts.

Tasks:
1. Update worker handoff emitter to include full schema block.
2. Implement orchestrator command adapter with required envelope.
3. Map `partial` status through reconciliation rule.
4. Implement origin-bead resume checks after bug closure.

Exit Criteria:
1. End-to-end interrupt -> route -> retry/escalate -> resume flow works.
2. `partial` is never treated as success without reconciliation.

## 23. Canonical Data Contracts

### 23.1 Policy File Schema (`.mycelium/orchestrator-policy.yaml`)

Required keys:
1. `timezone`: IANA timezone string.
2. `business_hours`: object with `weekdays`, `start`, `end`.
3. `retry`: object with `max_retries`, `backoff_seconds`, `jitter_pct`.
4. `risk_budget`: object with `max_noncritical_escalations_per_day`, `max_noncritical_pages_per_hour`.
5. `dedupe`: object with `window_minutes`.
6. `trust`: object with `initial_score`, `min_samples`.

Example:
```yaml
timezone: America/New_York
business_hours:
  weekdays: [Mon, Tue, Wed, Thu, Fri]
  start: "09:00"
  end: "18:00"
retry:
  max_retries: 3
  backoff_seconds: [60, 300, 900]
  jitter_pct: 15
risk_budget:
  max_noncritical_escalations_per_day: 20
  max_noncritical_pages_per_hour: 5
dedupe:
  window_minutes: 60
trust:
  initial_score: 0.5
  min_samples: 5
```

### 23.2 Handoff State Store (`.beads/orchestrator-handoff-state.json`)

Top-level object keyed by `handoff_key`.

Per-key required fields:
1. `state`
2. `attempt`
3. `last_transition_at`
4. `next_retry_at` (nullable)
5. `last_error_class` (nullable)
6. `owner_id` (nullable)

Example:
```json
{
  "a41d...": {
    "state": "RETRY_WAIT",
    "attempt": 2,
    "last_transition_at": "2026-02-25T17:20:11Z",
    "next_retry_at": "2026-02-25T17:25:23Z",
    "last_error_class": "timeout",
    "owner_id": null
  }
}
```

### 23.3 Run Artifact Contract (`.beads/orchestrator-runs/...jsonl`)

Each line MUST include:
1. `timestamp`
2. `handoff_key`
3. `attempt`
4. `inputs` (labels, notes snapshot hash, policy hash, local-time eval)
5. `decision_path` (ordered precedence steps + outcomes)
6. `command_envelope`
7. `transition` (`from`, `to`, `result`, `error_class`)

### 23.4 Digest Artifact Contract

Daily digest record MUST include:
1. `date_local`
2. `timezone`
3. `new_escalations`
4. `dead_letter_count`
5. `clusters` (sorted by risk score desc)
6. `suppressed_by_dedupe`
7. `deferred_by_budget`

## 24. Control-Flow Scenarios

### 24.1 Happy Path

1. Worker creates bug bead with required labels and handoff block.
2. Watcher validates schema and invariants.
3. Watcher claims handoff (`QUEUED -> RUNNING`).
4. Orchestrator command returns `success`.
5. Watcher records run, writes capsule/replay, transitions to `DONE`.

### 24.2 Retriable Failure Path

1. Command returns retriable error class (for example `timeout`).
2. Watcher computes `next_retry_at` with jitter.
3. State transitions to `RETRY_WAIT`.
4. On cooldown expiry, watcher re-enters `RUNNING`.
5. On retry cap exhaustion, transition to `HUMAN_REQUIRED` + `orchestrator:dead`.

### 24.3 Non-Retriable Failure Path

1. Schema invalid or `auth_failed` is detected.
2. No command execution occurs (or immediate stop if already running).
3. Watcher transitions directly to `HUMAN_REQUIRED`.
4. Digest pipeline includes incident with context capsule when available.

### 24.4 Off-Hours Noncritical Path

1. Event is noncritical and outside business hours.
2. Risk budget is evaluated.
3. If budget exceeded, event is deferred.
4. Event appears in next daily digest with cluster ranking.

## 25. Rollout and Gating Plan

### 25.1 Stage 0: Dry Simulation

1. Run watcher in shadow mode only.
2. Emit `watcher_run` and replay artifacts without state mutation.
3. Exit gate: >=95% decision consistency across replay runs.

### 25.2 Stage 1: Read-Only + Escalation Draft

1. Enable state reads and policy checks.
2. Write advisory notes only; no label transitions.
3. Exit gate: zero ambiguous-policy events for 7 consecutive days.

### 25.3 Stage 2: Limited Write Path

1. Enable transitions for one project scope.
2. Keep human confirmation required for `DONE` and `dead-letter`.
3. Exit gate: no duplicate-claim incidents and retry behavior matches tests.

### 25.4 Stage 3: Full Automation

1. Enable full transition and escalation pipeline.
2. Enable digest publishing and budget enforcement.
3. Exit gate: stable SLOs over 14 days.

## 26. Operational Runbook

### 26.1 SLO Targets

1. `handoff_claim_latency_p95` <= 30s
2. `stale_running_recovery_p95` <= 2m
3. `digest_generation_success_rate` >= 99%
4. `duplicate_execution_rate` = 0

### 26.2 On-Call Triage Steps

1. Check latest `watcher_run` for `error_class`.
2. Replay latest run artifact in dry-run mode.
3. Verify policy hash and local-time evaluation.
4. Validate state store and lock lease freshness.
5. If unresolved, set manual override note and keep `needs:human`.

### 26.3 Manual Override Policy

1. Overrides MUST be written as structured note with actor and timestamp.
2. Override TTL MUST be explicit (default 24h).
3. Expired overrides MUST be ignored automatically.

### 26.4 Disaster Recovery

1. Stop watcher process.
2. Backup `.beads/orchestrator-handoff-state.json` and lock file.
3. Rebuild in-memory state from replay artifacts.
4. Run invariant scan before re-enabling writes.
