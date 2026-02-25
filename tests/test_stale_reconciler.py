#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.fsm import FSMState
from watcher.stale_reconciler import is_stale_running, reconcile_stale_running
from watcher.state_store import StateRecord


def _record(state: str, last_transition_at: str) -> StateRecord:
    return StateRecord(
        state=state,
        attempt=1,
        last_transition_at=last_transition_at,
        next_retry_at=None,
        last_error_class=None,
        owner_id="worker-a",
        version=1,
    )


class StaleReconcilerTests(unittest.TestCase):
    def test_is_stale_running_true_for_old_running_record(self) -> None:
        now = datetime(2026, 2, 25, 12, 5, 0, tzinfo=timezone.utc)
        record = _record(FSMState.RUNNING.value, "2026-02-25T12:00:00Z")
        self.assertTrue(is_stale_running(record, now, stale_after_seconds=60))

    def test_is_stale_running_false_for_recent_running_record(self) -> None:
        now = datetime(2026, 2, 25, 12, 0, 30, tzinfo=timezone.utc)
        record = _record(FSMState.RUNNING.value, "2026-02-25T12:00:00Z")
        self.assertFalse(is_stale_running(record, now, stale_after_seconds=60))

    def test_is_stale_running_false_for_non_running_state(self) -> None:
        now = datetime(2026, 2, 25, 12, 5, 0, tzinfo=timezone.utc)
        record = _record(FSMState.RETRY_WAIT.value, "2026-02-25T12:00:00Z")
        self.assertFalse(is_stale_running(record, now, stale_after_seconds=60))

    def test_reconcile_stale_running_to_retry_wait_when_retries_available(self) -> None:
        now = datetime(2026, 2, 25, 12, 5, 0, tzinfo=timezone.utc)
        record = _record(FSMState.RUNNING.value, "2026-02-25T12:00:00Z")

        transition = reconcile_stale_running(
            record,
            now_utc=now,
            stale_after_seconds=60,
            retry_count=1,
            max_retries=3,
            retry_backoff_seconds=120,
        )
        self.assertIsNotNone(transition)
        self.assertEqual(transition.to_state.value, FSMState.RETRY_WAIT.value)
        self.assertEqual(transition.error_class, "stale_run")
        self.assertIsNotNone(transition.next_retry_at)

    def test_reconcile_stale_running_to_human_required_when_retries_exhausted(self) -> None:
        now = datetime(2026, 2, 25, 12, 5, 0, tzinfo=timezone.utc)
        record = _record(FSMState.RUNNING.value, "2026-02-25T12:00:00Z")

        transition = reconcile_stale_running(
            record,
            now_utc=now,
            stale_after_seconds=60,
            retry_count=3,
            max_retries=3,
            retry_backoff_seconds=120,
        )
        self.assertIsNotNone(transition)
        self.assertEqual(transition.to_state.value, FSMState.HUMAN_REQUIRED.value)
        self.assertEqual(transition.error_class, "stale_run")

    def test_reconcile_returns_none_when_not_stale(self) -> None:
        now = datetime(2026, 2, 25, 12, 0, 30, tzinfo=timezone.utc)
        record = _record(FSMState.RUNNING.value, "2026-02-25T12:00:00Z")
        transition = reconcile_stale_running(
            record,
            now_utc=now,
            stale_after_seconds=60,
            retry_count=1,
            max_retries=3,
        )
        self.assertIsNone(transition)

    def test_reconcile_rejects_non_running(self) -> None:
        now = datetime(2026, 2, 25, 12, 5, 0, tzinfo=timezone.utc)
        record = _record(FSMState.RETRY_WAIT.value, "2026-02-25T12:00:00Z")
        with self.assertRaises(ValueError):
            reconcile_stale_running(
                record,
                now_utc=now,
                stale_after_seconds=60,
                retry_count=1,
                max_retries=3,
            )

    def test_is_stale_requires_positive_threshold(self) -> None:
        now = datetime(2026, 2, 25, 12, 5, 0, tzinfo=timezone.utc)
        record = _record(FSMState.RUNNING.value, "2026-02-25T12:00:00Z")
        with self.assertRaises(ValueError):
            is_stale_running(record, now, stale_after_seconds=0)


if __name__ == "__main__":
    unittest.main()

