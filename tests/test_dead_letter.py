#!/usr/bin/env python3
from datetime import datetime, timezone
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.dead_letter import (
    DeadLetterError,
    build_dead_letter_record,
    build_dead_letter_transition,
    evaluate_dead_letter,
)
from watcher.fsm import FSMState
from watcher.state_store import StateRecord


class DeadLetterTests(unittest.TestCase):
    def test_retry_exhaustion_triggers_dead_letter(self) -> None:
        decision = evaluate_dead_letter(error_class="timeout", retry_count=3, max_retries=3)
        self.assertTrue(decision.should_dead_letter)
        self.assertEqual(decision.reason, "retry_exhausted")

    def test_non_retriable_error_triggers_dead_letter(self) -> None:
        decision = evaluate_dead_letter(error_class="auth_failed", retry_count=0, max_retries=3)
        self.assertTrue(decision.should_dead_letter)
        self.assertEqual(decision.reason, "non_retriable_error")

    def test_retriable_under_budget_does_not_dead_letter(self) -> None:
        decision = evaluate_dead_letter(error_class="timeout", retry_count=1, max_retries=3)
        self.assertFalse(decision.should_dead_letter)
        self.assertEqual(decision.reason, "retry_budget_remaining")

    def test_transition_adds_required_dead_letter_labels(self) -> None:
        transition = build_dead_letter_transition(
            current_state=FSMState.RUNNING,
            error_class="auth_failed",
            retry_count=0,
            max_retries=3,
        )
        self.assertIsNotNone(transition)
        self.assertIn("orchestrator:dead", transition.add_labels)
        self.assertIn("needs:human", transition.add_labels)
        self.assertEqual(transition.to_state, FSMState.HUMAN_REQUIRED)

    def test_transition_returns_none_when_not_dead_letter(self) -> None:
        transition = build_dead_letter_transition(
            current_state=FSMState.RUNNING,
            error_class="timeout",
            retry_count=1,
            max_retries=3,
        )
        self.assertIsNone(transition)

    def test_build_dead_letter_record_sets_human_required(self) -> None:
        current = StateRecord(
            state="RUNNING",
            attempt=3,
            last_transition_at="2026-02-25T22:00:00Z",
            next_retry_at="2026-02-25T22:05:00Z",
            last_error_class="timeout",
            owner_id="watcher-1",
            version=2,
        )
        record = build_dead_letter_record(
            current_record=current,
            now_utc=datetime(2026, 2, 25, 22, 6, 0, tzinfo=timezone.utc),
            error_class="auth_failed",
            owner_id=None,
        )
        self.assertEqual(record.state, "HUMAN_REQUIRED")
        self.assertEqual(record.next_retry_at, None)
        self.assertEqual(record.last_error_class, "auth_failed")
        self.assertEqual(record.attempt, 3)

    def test_invalid_retry_inputs_raise(self) -> None:
        with self.assertRaises(DeadLetterError):
            evaluate_dead_letter(error_class="timeout", retry_count=-1, max_retries=3)


if __name__ == "__main__":
    unittest.main()
