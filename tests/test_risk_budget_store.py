#!/usr/bin/env python3
from datetime import datetime, timezone
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.risk_budget_store import RiskBudgetCounterStore, RiskBudgetStoreError


class RiskBudgetStoreTests(unittest.TestCase):
    def test_noncritical_allow_increments_counters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RiskBudgetCounterStore(pathlib.Path(temp_dir) / "risk-budget.json")
            decision = store.evaluate_and_record(
                now_utc=datetime(2026, 2, 26, 1, 0, 0, tzinfo=timezone.utc),
                timezone_name="America/New_York",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            self.assertEqual(decision.decision, "allow")
            self.assertEqual(decision.noncritical_day_count, 1)
            self.assertEqual(decision.noncritical_hour_count, 1)

    def test_hourly_budget_defer(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RiskBudgetCounterStore(pathlib.Path(temp_dir) / "risk-budget.json")
            now = datetime(2026, 2, 26, 1, 0, 0, tzinfo=timezone.utc)
            for _ in range(2):
                store.evaluate_and_record(
                    now_utc=now,
                    timezone_name="America/New_York",
                    is_critical=False,
                    max_noncritical_escalations_per_day=20,
                    max_noncritical_pages_per_hour=2,
                )
            decision = store.evaluate_and_record(
                now_utc=now,
                timezone_name="America/New_York",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=2,
            )
            self.assertEqual(decision.decision, "defer")
            self.assertEqual(decision.reason, "hourly_noncritical_budget_exhausted")

    def test_daily_rollover_resets_counts_at_local_midnight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RiskBudgetCounterStore(pathlib.Path(temp_dir) / "risk-budget.json")

            # 2026-02-25 23:30:00 America/New_York
            before_midnight = datetime(2026, 2, 26, 4, 30, 0, tzinfo=timezone.utc)
            store.evaluate_and_record(
                now_utc=before_midnight,
                timezone_name="America/New_York",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )

            # 2026-02-26 00:30:00 America/New_York (next local day)
            after_midnight = datetime(2026, 2, 26, 5, 30, 0, tzinfo=timezone.utc)
            decision = store.evaluate_and_record(
                now_utc=after_midnight,
                timezone_name="America/New_York",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            self.assertEqual(decision.decision, "allow")
            self.assertEqual(decision.noncritical_day_count, 1)
            self.assertEqual(decision.noncritical_hour_count, 1)
            self.assertEqual(decision.day_bucket, "2026-02-26")

    def test_hour_rollover_resets_hour_counter_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RiskBudgetCounterStore(pathlib.Path(temp_dir) / "risk-budget.json")
            first_hour = datetime(2026, 2, 26, 13, 10, 0, tzinfo=timezone.utc)
            store.evaluate_and_record(
                now_utc=first_hour,
                timezone_name="UTC",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            second_hour = datetime(2026, 2, 26, 14, 10, 0, tzinfo=timezone.utc)
            decision = store.evaluate_and_record(
                now_utc=second_hour,
                timezone_name="UTC",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            self.assertEqual(decision.noncritical_day_count, 2)
            self.assertEqual(decision.noncritical_hour_count, 1)

    def test_critical_bypass_does_not_increment_noncritical(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RiskBudgetCounterStore(pathlib.Path(temp_dir) / "risk-budget.json")
            allow = store.evaluate_and_record(
                now_utc=datetime(2026, 2, 26, 1, 0, 0, tzinfo=timezone.utc),
                timezone_name="UTC",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            bypass = store.evaluate_and_record(
                now_utc=datetime(2026, 2, 26, 1, 10, 0, tzinfo=timezone.utc),
                timezone_name="UTC",
                is_critical=True,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            self.assertEqual(bypass.decision, "bypass-critical")
            self.assertEqual(bypass.noncritical_day_count, allow.noncritical_day_count)
            self.assertEqual(bypass.noncritical_hour_count, allow.noncritical_hour_count)

    def test_timezone_change_resets_counters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RiskBudgetCounterStore(pathlib.Path(temp_dir) / "risk-budget.json")
            store.evaluate_and_record(
                now_utc=datetime(2026, 2, 26, 1, 0, 0, tzinfo=timezone.utc),
                timezone_name="UTC",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            decision = store.evaluate_and_record(
                now_utc=datetime(2026, 2, 26, 1, 0, 0, tzinfo=timezone.utc),
                timezone_name="America/New_York",
                is_critical=False,
                max_noncritical_escalations_per_day=20,
                max_noncritical_pages_per_hour=5,
            )
            self.assertEqual(decision.noncritical_day_count, 1)
            self.assertEqual(decision.noncritical_hour_count, 1)

    def test_invalid_timezone_raises(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RiskBudgetCounterStore(pathlib.Path(temp_dir) / "risk-budget.json")
            with self.assertRaises(RiskBudgetStoreError):
                store.evaluate_and_record(
                    now_utc=datetime(2026, 2, 26, 1, 0, 0, tzinfo=timezone.utc),
                    timezone_name="Not/AZone",
                    is_critical=False,
                    max_noncritical_escalations_per_day=20,
                    max_noncritical_pages_per_hour=5,
                )


if __name__ == "__main__":
    unittest.main()
