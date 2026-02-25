#!/usr/bin/env python3
from datetime import datetime, timezone
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.fsm import FSMEvent, FSMState, execute_transition
from watcher.handoff_parser import parse_handoff_block
from watcher.label_invariants import validate_and_normalize_labels
from watcher.stale_reconciler import reconcile_stale_running
from watcher.state_store import StateRecord


def _handoff_notes() -> str:
    return """
handoff:
  origin_id: osm-4x3
  bug_id: osm-4x3.10
  error_signature: timeout_network
  expected_minutes: 20
  estimated_loc: 120
  touches_api_or_schema: false
  touches_security_or_auth: false
  quick_test_available: true
"""


class RuntimeIntegrationTests(unittest.TestCase):
    def test_happy_path_queued_to_running_to_done(self) -> None:
        payload = parse_handoff_block(_handoff_notes())
        self.assertEqual(payload.bug_id, "osm-4x3.10")

        queued = validate_and_normalize_labels(["needs:orchestrator"])
        self.assertTrue(queued.valid)
        self.assertEqual(queued.normalized_labels, ["needs:orchestrator"])

        to_running = execute_transition(FSMState.QUEUED, FSMEvent.CLAIM_READY)
        labels_after_claim = set(queued.normalized_labels)
        labels_after_claim.update(to_running.add_labels)
        labels_after_claim.difference_update(to_running.remove_labels)
        normalized_running = validate_and_normalize_labels(labels_after_claim)
        self.assertEqual(normalized_running.normalized_labels, ["orchestrator:running"])

        to_done = execute_transition(FSMState.RUNNING, FSMEvent.COMMAND_SUCCEEDED)
        labels_after_done = set(normalized_running.normalized_labels)
        labels_after_done.update(to_done.add_labels)
        labels_after_done.difference_update(to_done.remove_labels)
        normalized_done = validate_and_normalize_labels(labels_after_done)
        self.assertIn("orchestrator:done", normalized_done.normalized_labels)
        self.assertNotIn("needs:orchestrator", normalized_done.normalized_labels)

    def test_retriable_failure_path_to_retry_wait(self) -> None:
        transition = execute_transition(
            FSMState.RUNNING,
            FSMEvent.COMMAND_FAILED,
            error_class="timeout",
            retry_count=1,
            max_retries=3,
            next_retry_at="2026-02-25T12:10:00Z",
        )
        self.assertEqual(transition.to_state, FSMState.RETRY_WAIT)
        self.assertEqual(transition.error_class, "timeout")
        self.assertEqual(transition.next_retry_at, "2026-02-25T12:10:00Z")

    def test_non_retriable_failure_path_to_human_required(self) -> None:
        transition = execute_transition(
            FSMState.RUNNING,
            FSMEvent.COMMAND_FAILED,
            error_class="schema_invalid",
            retry_count=0,
            max_retries=3,
        )
        self.assertEqual(transition.to_state, FSMState.HUMAN_REQUIRED)
        labels = set(transition.add_labels)
        self.assertIn("needs:human", labels)
        self.assertIn("orchestrator:dead", labels)

    def test_stale_running_recovery_path(self) -> None:
        record = StateRecord(
            state=FSMState.RUNNING.value,
            attempt=2,
            last_transition_at="2026-02-25T12:00:00Z",
            next_retry_at=None,
            last_error_class=None,
            owner_id="watcher-a",
            version=2,
        )
        transition = reconcile_stale_running(
            record,
            now_utc=datetime(2026, 2, 25, 12, 5, 0, tzinfo=timezone.utc),
            stale_after_seconds=60,
            retry_count=2,
            max_retries=3,
            retry_backoff_seconds=120,
        )
        self.assertIsNotNone(transition)
        self.assertEqual(transition.to_state, FSMState.RETRY_WAIT)
        self.assertEqual(transition.error_class, "stale_run")
        self.assertIsNotNone(transition.next_retry_at)


if __name__ == "__main__":
    unittest.main()

