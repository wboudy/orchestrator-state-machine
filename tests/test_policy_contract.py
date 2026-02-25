#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.policy_contract import PolicyValidationError, validate_policy_mapping


class PolicyContractTests(unittest.TestCase):
    def test_validate_policy_mapping_valid(self) -> None:
        policy = {
            "timezone": "America/New_York",
            "business_hours": {
                "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri"],
                "start": "09:00",
                "end": "18:00",
            },
            "retry": {
                "max_retries": 3,
                "backoff_seconds": [60, 300, 900],
                "jitter_pct": 15,
            },
            "risk_budget": {
                "max_noncritical_escalations_per_day": 20,
                "max_noncritical_pages_per_hour": 5,
            },
            "dedupe": {"window_minutes": 60},
            "trust": {"initial_score": 0.5, "min_samples": 5},
        }

        parsed = validate_policy_mapping(policy)
        self.assertEqual(parsed.timezone, "America/New_York")
        self.assertEqual(parsed.business_hours.weekdays, ("Mon", "Tue", "Wed", "Thu", "Fri"))
        self.assertEqual(parsed.retry.backoff_seconds, (60, 300, 900))
        self.assertEqual(parsed.risk_budget.max_noncritical_pages_per_hour, 5)
        self.assertEqual(parsed.dedupe.window_minutes, 60)
        self.assertEqual(parsed.trust.initial_score, 0.5)

    def test_validate_policy_mapping_aggregates_errors(self) -> None:
        policy = {
            "timezone": "bad timezone",
            "business_hours": {
                "weekdays": [],
                "start": "18:00",
                "end": "09:00",
                "extra": "nope",
            },
            "retry": {
                "max_retries": -1,
                "backoff_seconds": [60, 0],
                "jitter_pct": 101,
            },
            "risk_budget": {
                "max_noncritical_escalations_per_day": -2,
                "max_noncritical_pages_per_hour": 2,
            },
            "dedupe": {"window_minutes": 0},
            "trust": {"initial_score": 2.0, "min_samples": 0},
            "unknown_top": True,
        }

        with self.assertRaises(PolicyValidationError) as exc:
            validate_policy_mapping(policy)

        errors = exc.exception.errors
        self.assertIn("timezone invalid", errors)
        self.assertIn("policy.unknown_top unknown", errors)
        self.assertIn("business_hours.weekdays invalid", errors)
        self.assertIn("business_hours.extra unknown", errors)
        self.assertIn("business_hours range invalid", errors)
        self.assertIn("retry.max_retries invalid", errors)
        self.assertIn("retry.backoff_seconds invalid", errors)
        self.assertIn("retry.jitter_pct invalid", errors)
        self.assertIn("risk_budget.max_noncritical_escalations_per_day invalid", errors)
        self.assertIn("dedupe.window_minutes invalid", errors)
        self.assertIn("trust.initial_score invalid", errors)
        self.assertIn("trust.min_samples invalid", errors)

    def test_missing_required_top_level_keys(self) -> None:
        with self.assertRaises(PolicyValidationError) as exc:
            validate_policy_mapping({})

        self.assertIn("timezone missing", exc.exception.errors)
        self.assertIn("business_hours missing", exc.exception.errors)
        self.assertIn("retry missing", exc.exception.errors)
        self.assertIn("risk_budget missing", exc.exception.errors)
        self.assertIn("dedupe missing", exc.exception.errors)
        self.assertIn("trust missing", exc.exception.errors)


if __name__ == "__main__":
    unittest.main()
