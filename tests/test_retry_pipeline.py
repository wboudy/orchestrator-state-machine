#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.dead_letter import build_dead_letter_record, build_dead_letter_transition
from watcher.error_classifier import classify_error
from watcher.fsm import FSMState
from watcher.retry_cooldown import build_retry_wait_record, evaluate_retry_cooldown
from watcher.retry_scheduler import compute_retry_schedule, format_rfc3339_utc
from watcher.state_store import StateRecord


class RetryPipelineTests(unittest.TestCase):
    def test_retriable_pipeline_classification_schedule_and_cooldown(self) -> None:
        now = datetime(2026, 2, 25, 23, 0, 0, tzinfo=timezone.utc)
        classification = classify_error("rate-limit")
        self.assertEqual(classification.normalized_error_class, "rate_limited")
        self.assertTrue(classification.retryable)

        schedule = compute_retry_schedule(
            now_utc=now,
            attempt=2,
            backoff_seconds=[60, 300, 900],
            jitter_pct=15,
            jitter_unit=0.0,
        )
        self.assertEqual(schedule.delay_seconds, 300)
        self.assertEqual(format_rfc3339_utc(schedule.next_retry_at), "2026-02-25T23:05:00Z")

        current = StateRecord(
            state="RUNNING",
            attempt=1,
            last_transition_at="2026-02-25T22:58:00Z",
            next_retry_at=None,
            last_error_class=None,
            owner_id="watcher-1",
            version=2,
        )
        retry_record = build_retry_wait_record(
            current_record=current,
            now_utc=now,
            next_retry_at=schedule.next_retry_at,
            error_class=classification.normalized_error_class,
            owner_id=None,
        )
        self.assertEqual(retry_record.state, "RETRY_WAIT")
        self.assertEqual(retry_record.attempt, 2)

        gate_before = evaluate_retry_cooldown(retry_record.next_retry_at, now + timedelta(seconds=120))
        self.assertFalse(gate_before.ready)
        self.assertGreater(gate_before.wait_seconds, 0)

        gate_after = evaluate_retry_cooldown(retry_record.next_retry_at, now + timedelta(seconds=301))
        self.assertTrue(gate_after.ready)

    def test_dead_letter_transition_on_retry_exhaustion(self) -> None:
        transition = build_dead_letter_transition(
            current_state=FSMState.RUNNING,
            error_class="timeout",
            retry_count=3,
            max_retries=3,
        )
        self.assertIsNotNone(transition)
        self.assertEqual(transition.to_state, FSMState.HUMAN_REQUIRED)
        self.assertIn("orchestrator:dead", transition.add_labels)
        self.assertIn("needs:human", transition.add_labels)

    def test_non_retriable_goes_directly_to_dead_letter(self) -> None:
        transition = build_dead_letter_transition(
            current_state=FSMState.RUNNING,
            error_class="permission_denied",
            retry_count=0,
            max_retries=3,
        )
        self.assertIsNotNone(transition)
        self.assertEqual(transition.error_class, "permission_denied")
        self.assertEqual(transition.to_state, FSMState.HUMAN_REQUIRED)

    def test_dead_letter_record_clears_next_retry(self) -> None:
        current = StateRecord(
            state="RETRY_WAIT",
            attempt=3,
            last_transition_at="2026-02-25T23:00:00Z",
            next_retry_at="2026-02-25T23:05:00Z",
            last_error_class="timeout",
            owner_id=None,
            version=7,
        )
        record = build_dead_letter_record(
            current_record=current,
            now_utc=datetime(2026, 2, 25, 23, 5, 1, tzinfo=timezone.utc),
            error_class="policy_invalid",
            owner_id=None,
        )
        self.assertEqual(record.state, "HUMAN_REQUIRED")
        self.assertIsNone(record.next_retry_at)
        self.assertEqual(record.last_error_class, "policy_invalid")


if __name__ == "__main__":
    unittest.main()
