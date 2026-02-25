#!/usr/bin/env python3
from datetime import datetime, timezone
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.retry_cooldown import (
    CooldownGateError,
    build_retry_resume_record,
    build_retry_wait_record,
    evaluate_retry_cooldown,
)
from watcher.state_store import StateRecord


class RetryCooldownTests(unittest.TestCase):
    def test_gate_ready_when_no_cooldown(self) -> None:
        now = datetime(2026, 2, 25, 21, 0, 0, tzinfo=timezone.utc)
        decision = evaluate_retry_cooldown(None, now)
        self.assertTrue(decision.ready)
        self.assertEqual(decision.wait_seconds, 0)
        self.assertEqual(decision.reason, "no_cooldown")

    def test_gate_blocks_until_next_retry(self) -> None:
        now = datetime(2026, 2, 25, 21, 0, 0, tzinfo=timezone.utc)
        decision = evaluate_retry_cooldown("2026-02-25T21:01:30Z", now)
        self.assertFalse(decision.ready)
        self.assertEqual(decision.wait_seconds, 90)
        self.assertEqual(decision.reason, "cooldown_active")

    def test_gate_allows_when_cooldown_elapsed(self) -> None:
        now = datetime(2026, 2, 25, 21, 2, 0, tzinfo=timezone.utc)
        decision = evaluate_retry_cooldown("2026-02-25T21:01:30Z", now)
        self.assertTrue(decision.ready)
        self.assertEqual(decision.reason, "cooldown_elapsed")

    def test_invalid_timestamp_raises(self) -> None:
        with self.assertRaises(CooldownGateError):
            evaluate_retry_cooldown("not-a-time", datetime(2026, 2, 25, 21, 0, 0, tzinfo=timezone.utc))

    def test_build_retry_wait_record_persists_next_retry(self) -> None:
        now = datetime(2026, 2, 25, 21, 0, 0, tzinfo=timezone.utc)
        retry_at = datetime(2026, 2, 25, 21, 5, 0, tzinfo=timezone.utc)
        current = StateRecord(
            state="RUNNING",
            attempt=2,
            last_transition_at="2026-02-25T20:59:00Z",
            next_retry_at=None,
            last_error_class=None,
            owner_id="watcher-1",
            version=4,
        )
        next_record = build_retry_wait_record(
            current,
            now_utc=now,
            next_retry_at=retry_at,
            error_class="timeout",
            owner_id=None,
        )
        self.assertEqual(next_record.state, "RETRY_WAIT")
        self.assertEqual(next_record.attempt, 3)
        self.assertEqual(next_record.next_retry_at, "2026-02-25T21:05:00Z")
        self.assertEqual(next_record.last_error_class, "timeout")
        self.assertEqual(next_record.version, 4)

    def test_build_retry_resume_record_clears_cooldown(self) -> None:
        now = datetime(2026, 2, 25, 21, 5, 0, tzinfo=timezone.utc)
        current = StateRecord(
            state="RETRY_WAIT",
            attempt=3,
            last_transition_at="2026-02-25T21:00:00Z",
            next_retry_at="2026-02-25T21:05:00Z",
            last_error_class="timeout",
            owner_id=None,
            version=5,
        )
        resumed = build_retry_resume_record(current, now_utc=now, owner_id="watcher-1")
        self.assertEqual(resumed.state, "RUNNING")
        self.assertEqual(resumed.next_retry_at, None)
        self.assertEqual(resumed.attempt, 3)
        self.assertEqual(resumed.owner_id, "watcher-1")

    def test_resume_requires_retry_wait_state(self) -> None:
        current = StateRecord(
            state="RUNNING",
            attempt=1,
            last_transition_at="2026-02-25T21:00:00Z",
            next_retry_at=None,
            last_error_class=None,
            owner_id=None,
            version=1,
        )
        with self.assertRaises(CooldownGateError):
            build_retry_resume_record(
                current,
                now_utc=datetime(2026, 2, 25, 21, 5, 0, tzinfo=timezone.utc),
                owner_id=None,
            )


if __name__ == "__main__":
    unittest.main()
