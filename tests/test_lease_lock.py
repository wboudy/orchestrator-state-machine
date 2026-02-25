#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.lease_lock import (
    LeaseBusyError,
    LeaseExpiredError,
    LeaseLockManager,
    LeaseOwnershipError,
)


class LeaseLockTests(unittest.TestCase):
    def test_acquire_and_release_happy_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LeaseLockManager(pathlib.Path(tmp) / "orchestrator-watch.lock", lease_seconds=30)
            now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
            lease = manager.acquire("worker-a", now)

            self.assertEqual(lease.owner_id, "worker-a")
            self.assertTrue(manager.release("worker-a"))
            self.assertIsNone(manager.load())

    def test_second_owner_cannot_acquire_active_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LeaseLockManager(pathlib.Path(tmp) / "orchestrator-watch.lock", lease_seconds=30)
            now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
            manager.acquire("worker-a", now)

            with self.assertRaises(LeaseBusyError):
                manager.acquire("worker-b", now + timedelta(seconds=10))

    def test_stale_lease_can_be_reclaimed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LeaseLockManager(pathlib.Path(tmp) / "orchestrator-watch.lock", lease_seconds=30)
            now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
            manager.acquire("worker-a", now)

            reclaimed = manager.acquire("worker-b", now + timedelta(seconds=31))
            self.assertEqual(reclaimed.owner_id, "worker-b")

    def test_heartbeat_renews_expiry_for_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LeaseLockManager(pathlib.Path(tmp) / "orchestrator-watch.lock", lease_seconds=30)
            now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
            first = manager.acquire("worker-a", now)
            refreshed = manager.heartbeat("worker-a", now + timedelta(seconds=10))

            self.assertNotEqual(first.expires_at, refreshed.expires_at)
            self.assertEqual(refreshed.owner_id, "worker-a")

    def test_heartbeat_rejects_wrong_owner_and_expired(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LeaseLockManager(pathlib.Path(tmp) / "orchestrator-watch.lock", lease_seconds=10)
            now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
            manager.acquire("worker-a", now)

            with self.assertRaises(LeaseOwnershipError):
                manager.heartbeat("worker-b", now + timedelta(seconds=3))

            with self.assertRaises(LeaseExpiredError):
                manager.heartbeat("worker-a", now + timedelta(seconds=11))

    def test_release_rejects_wrong_owner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = LeaseLockManager(pathlib.Path(tmp) / "orchestrator-watch.lock", lease_seconds=30)
            now = datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc)
            manager.acquire("worker-a", now)

            with self.assertRaises(LeaseOwnershipError):
                manager.release("worker-b")


if __name__ == "__main__":
    unittest.main()

