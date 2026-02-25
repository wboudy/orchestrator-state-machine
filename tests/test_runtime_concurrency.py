#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.lease_lock import LeaseBusyError, LeaseLockManager
from watcher.state_store import HandoffStateStore, StateRecord


def _base_record() -> StateRecord:
    return StateRecord(
        state="RUNNING",
        attempt=1,
        last_transition_at="2026-02-25T12:00:00Z",
        next_retry_at=None,
        last_error_class=None,
        owner_id="worker-a",
    )


class RuntimeConcurrencyTests(unittest.TestCase):
    def test_dual_watcher_lock_contention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = pathlib.Path(tmp) / "orchestrator-watch.lock"
            watcher_a = LeaseLockManager(lock_path, lease_seconds=30)
            watcher_b = LeaseLockManager(lock_path, lease_seconds=30)
            now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

            watcher_a.acquire("watcher-a", now)
            with self.assertRaises(LeaseBusyError):
                watcher_b.acquire("watcher-b", now + timedelta(seconds=10))

    def test_stale_lease_recovery_between_watchers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = pathlib.Path(tmp) / "orchestrator-watch.lock"
            watcher_a = LeaseLockManager(lock_path, lease_seconds=10)
            watcher_b = LeaseLockManager(lock_path, lease_seconds=10)
            start = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)

            watcher_a.acquire("watcher-a", start)
            reclaimed = watcher_b.acquire("watcher-b", start + timedelta(seconds=11))
            self.assertEqual(reclaimed.owner_id, "watcher-b")

    def test_optimistic_version_conflict_prevents_double_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStateStore(pathlib.Path(tmp) / "orchestrator-handoff-state.json")
            key = "handoff-key-1"
            initial = _base_record()
            store.save(key, initial, expected_version=0)

            watcher_a_view = store.load(key)
            watcher_b_view = store.load(key)
            self.assertEqual(watcher_a_view.version, 1)
            self.assertEqual(watcher_b_view.version, 1)

            result_a = store.save(
                key,
                replace(watcher_a_view, attempt=watcher_a_view.attempt + 1),
                expected_version=watcher_a_view.version,
            )
            self.assertTrue(result_a.saved)
            self.assertEqual(result_a.version, 2)

            result_b = store.save(
                key,
                replace(watcher_b_view, attempt=watcher_b_view.attempt + 1),
                expected_version=watcher_b_view.version,
            )
            self.assertFalse(result_b.saved)
            self.assertTrue(result_b.conflict)
            self.assertEqual(result_b.version, 2)

            final_record = store.load(key)
            self.assertEqual(final_record.attempt, 2)
            self.assertEqual(final_record.version, 2)


if __name__ == "__main__":
    unittest.main()

