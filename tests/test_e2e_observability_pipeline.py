#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.capsule_generator import generate_reproducibility_capsule
from watcher.command_adapter import WatcherResult, parse_command_envelope, reconcile_command_envelope
from watcher.dedupe_store import DedupeSuppressionStore
from watcher.digest_builder import IncidentRecord, build_daily_digest
from watcher.handoff_parser import HandoffPayload, parse_handoff_block
from watcher.notification_transport import BeadNativeTransport, NotificationMessage
from watcher.replay_handoff import replay_handoff_run
from watcher.retry_cooldown import build_retry_wait_record, evaluate_retry_cooldown
from watcher.retry_scheduler import compute_retry_schedule
from watcher.risk_budget_store import RiskBudgetCounterStore
from watcher.run_artifact_emitter import emit_run_artifact
from watcher.watcher_run_writer import append_watcher_run
from watcher.worker_adapter import OriginResumeContext, emit_worker_handoff_block, evaluate_origin_resume


class EndToEndObservabilityPipelineTests(unittest.TestCase):
    def test_retry_flow_replay_capsule_and_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir)
            now = datetime(2026, 2, 26, 15, 0, 0, tzinfo=timezone.utc)

            handoff_payload = HandoffPayload(
                origin_id="osm-11i",
                bug_id="osm-11i.12",
                error_signature="timeout_case_sig",
                expected_minutes=20,
                estimated_loc=80,
                touches_api_or_schema=False,
                touches_security_or_auth=False,
                quick_test_available=True,
            )
            block = emit_worker_handoff_block(handoff_payload)
            parsed_handoff = parse_handoff_block(block)
            self.assertEqual(parsed_handoff.bug_id, "osm-11i.12")

            envelope = parse_command_envelope(
                {
                    "run_id": "run-001",
                    "exit_code": 1,
                    "status": "partial",
                    "error_class": "timeout",
                }
            )
            reconciliation = reconcile_command_envelope(envelope, terminal_success_observed=False)
            self.assertEqual(reconciliation.watcher_result, WatcherResult.RETRY)

            schedule = compute_retry_schedule(
                now_utc=now,
                attempt=1,
                backoff_seconds=[60, 300, 900],
                jitter_pct=15,
                jitter_unit=0.0,
            )
            retry_record = build_retry_wait_record(
                current_record=None,
                now_utc=now,
                next_retry_at=schedule.next_retry_at,
                error_class=reconciliation.normalized_error_class or "unknown_error",
                owner_id=None,
            )
            gate = evaluate_retry_cooldown(retry_record.next_retry_at, now + timedelta(seconds=30))
            self.assertFalse(gate.ready)

            watcher_log_path = root / ".beads" / "watcher-runs.jsonl"
            append_watcher_run(
                watcher_log_path,
                {
                    "handoff_key": "a1b2c3d4e5f6a7b8",
                    "state_from": "RUNNING",
                    "state_to": "RETRY_WAIT",
                    "attempt": 1,
                    "result": "retry",
                    "timestamp": now.isoformat().replace("+00:00", "Z"),
                    "error_class": "timeout",
                    "risk_budget_decision": "allow",
                },
            )

            run_artifact_path = emit_run_artifact(
                artifacts_root=root / ".beads" / "orchestrator-runs",
                record={
                    "timestamp": now.isoformat().replace("+00:00", "Z"),
                    "handoff_key": "a1b2c3d4e5f6a7b8",
                    "attempt": 1,
                    "inputs": {
                        "labels": ["needs:orchestrator", "orchestrator:running"],
                        "notes_snapshot_hash": "sha256:notes",
                        "policy_hash": "sha256:policy",
                        "local_time_eval": {"tz": "UTC", "local_time": "2026-02-26T15:00:00Z"},
                    },
                    "decision_path": [{"step": "failure_class_retryable", "outcome": "retriable"}],
                    "command_envelope": {
                        "run_id": "run-001",
                        "exit_code": 1,
                        "status": "partial",
                        "error_class": "timeout",
                    },
                    "transition": {
                        "from": "RUNNING",
                        "to": "RETRY_WAIT",
                        "result": "retry",
                        "error_class": "timeout",
                    },
                },
            )
            replay = replay_handoff_run(run_file=run_artifact_path, dry_run=True)
            self.assertTrue(replay.parity_match)
            self.assertEqual(replay.expected_result, "retry")

            capsule_path = generate_reproducibility_capsule(
                artifacts_root=root / ".beads" / "orchestrator-capsules",
                project_root=root,
                home_dir="/Users/testuser",
                capsule_payload={
                    "handoff_key": "a1b2c3d4e5f6a7b8",
                    "attempt": 1,
                    "timestamp": now.isoformat().replace("+00:00", "Z"),
                    "reproduction_steps": ["Run command", "Observe timeout"],
                    "observed": "Authorization: Bearer abc.def",
                    "expected": "Retry is scheduled and secret redacted",
                    "command_envelope": {"authorization": "Bearer top.secret"},
                    "logs": ["token=abc", "path=/Users/testuser/private/file.log"],
                    "metadata": {"run_file": str(run_artifact_path)},
                },
            )
            capsule_text = capsule_path.read_text(encoding="utf-8")
            self.assertIn("<REDACTED>", capsule_text)
            self.assertIn("<HOME>/private/file.log", capsule_text)

            risk_store = RiskBudgetCounterStore(root / ".beads" / "risk-budget.json")
            risk_decision = risk_store.evaluate_and_record(
                now_utc=now,
                timezone_name="UTC",
                is_critical=False,
                max_noncritical_escalations_per_day=5,
                max_noncritical_pages_per_hour=2,
            )
            self.assertEqual(risk_decision.decision, "allow")

            dedupe_store = DedupeSuppressionStore(root / ".beads" / "dedupe.json")
            dedupe = dedupe_store.evaluate_and_record(
                origin_id="osm-11i",
                error_signature="timeout_case_sig",
                error_class="timeout",
                now_utc=now,
                window_minutes=60,
            )
            self.assertFalse(dedupe.suppressed)

            digest = build_daily_digest(
                incidents=[
                    IncidentRecord(
                        incident_id="inc-1",
                        error_signature="timeout_case_sig",
                        origin_id="osm-11i",
                        priority=2,
                        created_at_utc=now - timedelta(hours=1),
                        unresolved_needs_human=True,
                        dead_letter=False,
                        suppressed_by_dedupe=False,
                        deferred_by_budget=False,
                    )
                ],
                now_utc=now,
                timezone_name="UTC",
            )
            self.assertEqual(digest.new_escalations, 1)
            self.assertEqual(digest.clusters[0].error_signature, "timeout_case_sig")

    def test_human_required_transport_and_origin_resume_path(self) -> None:
        now = datetime(2026, 2, 26, 16, 0, 0, tzinfo=timezone.utc)
        envelope = parse_command_envelope(
            {
                "run_id": "run-200",
                "exit_code": 1,
                "status": "failure",
                "error_class": "auth_failed",
            }
        )
        reconciliation = reconcile_command_envelope(envelope, terminal_success_observed=False)
        self.assertEqual(reconciliation.watcher_result, WatcherResult.HUMAN_REQUIRED)
        self.assertEqual(reconciliation.normalized_error_class, "auth_failed")

        transport = BeadNativeTransport()
        receipt = transport.send(
            NotificationMessage(
                handoff_key="a1b2c3d4e5f6a7b8",
                bug_id="osm-11i.12",
                priority=1,
                error_class="auth_failed",
                summary="Authentication failure requires human intervention",
                queued=False,
                metadata={"timestamp": now.isoformat().replace("+00:00", "Z")},
            )
        )
        self.assertIn("needs:human", receipt.labels)
        self.assertIn("notify:immediate", receipt.labels)

        blocked = evaluate_origin_resume(
            OriginResumeContext(
                origin_id="osm-11i",
                bug_id="osm-11i.12",
                bug_closed=False,
                dependency_present=True,
                origin_blocked=True,
                origin_in_progress=False,
            )
        )
        self.assertFalse(blocked.can_resume)

        resumable = evaluate_origin_resume(
            OriginResumeContext(
                origin_id="osm-11i",
                bug_id="osm-11i.12",
                bug_closed=True,
                dependency_present=False,
                origin_blocked=True,
                origin_in_progress=False,
            )
        )
        self.assertTrue(resumable.can_resume)
        self.assertIn("set_origin_in_progress", resumable.actions)


if __name__ == "__main__":
    unittest.main()
