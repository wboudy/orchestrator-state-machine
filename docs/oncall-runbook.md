# On-Call Runbook

## Scope

Operational response guide for watcher/orchestrator automation stages.

## Immediate Checks

1. Confirm `git status` is clean and branch is up to date with `origin/main`.
2. Run health checks:
   - `pytest -q`
   - `./tests/test_handoff_schema_validation.sh`
3. Inspect latest run artifacts under `.beads/orchestrator-runs/`.

## Incident Triage

1. Check recent `watcher_run` entries for:
   - `error_class`
   - `state_from/state_to`
   - `risk_budget_decision`
2. Replay suspicious runs:
   - `python3 scripts/replay_handoff.py --run-file <path> --dry-run`
3. If replay parity fails, pause automation and open a gate blocker bead.
4. For malformed runtime payload suspicions, run focused checks:
   - `pytest -q tests/test_command_adapter.py tests/test_label_invariants.py tests/test_handoff_parser.py`

## Rollback Procedure (State Files)

1. Snapshot current `.beads/` state files:
   - `risk-budget.json`
   - `dedupe.json`
   - `watcher-runs.jsonl`
2. Stop automated actions (shadow/assisted/full as applicable).
3. Restore last known-good snapshot.
4. Re-run health checks and one dry-run replay sample.
5. Resume only after explicit gate approver confirmation.

## Escalation

Escalate to `needs:human` immediately for:

- `policy_ambiguous`
- `schema_invalid`
- `state_divergence`
- `redaction_failed`
- `fsm_invalid`
- repeated replay parity mismatch
