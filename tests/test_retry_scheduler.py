#!/usr/bin/env python3
from datetime import datetime, timezone
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.retry_scheduler import RetryScheduleError, compute_retry_schedule, format_rfc3339_utc


class RetrySchedulerTests(unittest.TestCase):
    def test_attempt_uses_expected_base(self) -> None:
        now = datetime(2026, 2, 25, 20, 0, 0, tzinfo=timezone.utc)
        result = compute_retry_schedule(
            now_utc=now,
            attempt=1,
            backoff_seconds=[60, 300, 900],
            jitter_pct=15,
            jitter_unit=0.0,
        )
        self.assertEqual(result.base_delay_seconds, 60)
        self.assertEqual(result.delay_seconds, 60)
        self.assertEqual(format_rfc3339_utc(result.next_retry_at), "2026-02-25T20:01:00Z")

    def test_attempt_beyond_backoff_uses_last_slot(self) -> None:
        now = datetime(2026, 2, 25, 20, 0, 0, tzinfo=timezone.utc)
        result = compute_retry_schedule(
            now_utc=now,
            attempt=8,
            backoff_seconds=[60, 300, 900],
            jitter_pct=0,
            jitter_unit=0.0,
        )
        self.assertEqual(result.base_delay_seconds, 900)
        self.assertEqual(result.delay_seconds, 900)

    def test_jitter_bounds_min_and_max(self) -> None:
        now = datetime(2026, 2, 25, 20, 0, 0, tzinfo=timezone.utc)

        min_result = compute_retry_schedule(
            now_utc=now,
            attempt=1,
            backoff_seconds=[60],
            jitter_pct=15,
            jitter_unit=-1.0,
        )
        max_result = compute_retry_schedule(
            now_utc=now,
            attempt=1,
            backoff_seconds=[60],
            jitter_pct=15,
            jitter_unit=1.0,
        )

        self.assertEqual(min_result.delay_seconds, 51)
        self.assertEqual(max_result.delay_seconds, 69)

    def test_delay_never_drops_below_one_second(self) -> None:
        now = datetime(2026, 2, 25, 20, 0, 0, tzinfo=timezone.utc)
        result = compute_retry_schedule(
            now_utc=now,
            attempt=1,
            backoff_seconds=[1],
            jitter_pct=100,
            jitter_unit=-1.0,
        )
        self.assertEqual(result.delay_seconds, 1)

    def test_invalid_inputs_raise(self) -> None:
        now = datetime(2026, 2, 25, 20, 0, 0)
        with self.assertRaises(RetryScheduleError):
            compute_retry_schedule(
                now_utc=now,
                attempt=1,
                backoff_seconds=[60],
                jitter_pct=15,
            )
        with self.assertRaises(RetryScheduleError):
            compute_retry_schedule(
                now_utc=datetime(2026, 2, 25, 20, 0, 0, tzinfo=timezone.utc),
                attempt=0,
                backoff_seconds=[60],
                jitter_pct=15,
            )
        with self.assertRaises(RetryScheduleError):
            compute_retry_schedule(
                now_utc=datetime(2026, 2, 25, 20, 0, 0, tzinfo=timezone.utc),
                attempt=1,
                backoff_seconds=[],
                jitter_pct=15,
            )
        with self.assertRaises(RetryScheduleError):
            compute_retry_schedule(
                now_utc=datetime(2026, 2, 25, 20, 0, 0, tzinfo=timezone.utc),
                attempt=1,
                backoff_seconds=[60],
                jitter_pct=200,
            )


if __name__ == "__main__":
    unittest.main()
