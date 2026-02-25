#!/usr/bin/env python3
from datetime import datetime, timedelta, timezone
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.dedupe_store import DedupeStoreError, DedupeSuppressionStore, build_dedupe_key


class DedupeStoreTests(unittest.TestCase):
    def test_first_event_allows_and_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DedupeSuppressionStore(pathlib.Path(temp_dir) / "dedupe.json")
            decision = store.evaluate_and_record(
                origin_id="osm-1",
                error_signature="schema_invalid_case",
                error_class="schema_invalid",
                now_utc=datetime(2026, 2, 26, 2, 0, 0, tzinfo=timezone.utc),
                window_minutes=60,
            )
            self.assertFalse(decision.suppressed)
            self.assertEqual(decision.reason, "outside_window_or_first_seen")

    def test_second_event_within_window_is_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DedupeSuppressionStore(pathlib.Path(temp_dir) / "dedupe.json")
            start = datetime(2026, 2, 26, 2, 0, 0, tzinfo=timezone.utc)
            store.evaluate_and_record(
                origin_id="osm-1",
                error_signature="schema_invalid_case",
                error_class="schema_invalid",
                now_utc=start,
                window_minutes=60,
            )
            decision = store.evaluate_and_record(
                origin_id="osm-1",
                error_signature="schema_invalid_case",
                error_class="schema_invalid",
                now_utc=start + timedelta(minutes=5),
                window_minutes=60,
            )
            self.assertTrue(decision.suppressed)
            self.assertEqual(decision.reason, "suppressed_within_window")
            self.assertGreater(decision.remaining_seconds, 0)

    def test_event_after_window_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DedupeSuppressionStore(pathlib.Path(temp_dir) / "dedupe.json")
            start = datetime(2026, 2, 26, 2, 0, 0, tzinfo=timezone.utc)
            store.evaluate_and_record(
                origin_id="osm-1",
                error_signature="schema_invalid_case",
                error_class="schema_invalid",
                now_utc=start,
                window_minutes=60,
            )
            decision = store.evaluate_and_record(
                origin_id="osm-1",
                error_signature="schema_invalid_case",
                error_class="schema_invalid",
                now_utc=start + timedelta(minutes=61),
                window_minutes=60,
            )
            self.assertFalse(decision.suppressed)

    def test_different_key_not_suppressed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DedupeSuppressionStore(pathlib.Path(temp_dir) / "dedupe.json")
            now = datetime(2026, 2, 26, 2, 0, 0, tzinfo=timezone.utc)
            store.evaluate_and_record(
                origin_id="osm-1",
                error_signature="schema_invalid_case",
                error_class="schema_invalid",
                now_utc=now,
                window_minutes=60,
            )
            decision = store.evaluate_and_record(
                origin_id="osm-1",
                error_signature="auth_failed_case",
                error_class="auth_failed",
                now_utc=now + timedelta(minutes=1),
                window_minutes=60,
            )
            self.assertFalse(decision.suppressed)

    def test_invalid_window_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = DedupeSuppressionStore(pathlib.Path(temp_dir) / "dedupe.json")
            with self.assertRaises(DedupeStoreError):
                store.evaluate_and_record(
                    origin_id="osm-1",
                    error_signature="x",
                    error_class="y",
                    now_utc=datetime(2026, 2, 26, 2, 0, 0, tzinfo=timezone.utc),
                    window_minutes=0,
                )

    def test_build_dedupe_key_is_deterministic(self) -> None:
        key1 = build_dedupe_key(origin_id="osm-1", error_signature="sig", error_class="timeout")
        key2 = build_dedupe_key(origin_id="osm-1", error_signature="sig", error_class="timeout")
        self.assertEqual(key1, key2)
        self.assertEqual(len(key1), 40)


if __name__ == "__main__":
    unittest.main()
