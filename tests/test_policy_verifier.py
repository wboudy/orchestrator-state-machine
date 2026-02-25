#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.policy_verifier import (
    PolicyVerificationError,
    SPEC_PRECEDENCE_ORDER,
    verify_policy_or_raise,
    verify_policy_static,
)


class PolicyVerifierTests(unittest.TestCase):
    def test_verify_policy_static_success(self) -> None:
        result = verify_policy_static({})
        self.assertTrue(result.ok)
        self.assertIsNotNone(result.snapshot)
        self.assertEqual(result.errors, ())

    def test_retry_disabled_marks_unreachable_state(self) -> None:
        result = verify_policy_static({"retry": {"max_retries": 0}})
        self.assertFalse(result.ok)
        self.assertIn("unreachable_state", [entry.code for entry in result.errors])

    def test_conflicting_escalation_limits_are_rejected(self) -> None:
        result = verify_policy_static(
            {
                "risk_budget": {
                    "max_noncritical_escalations_per_day": 0,
                    "max_noncritical_pages_per_hour": 2,
                }
            }
        )
        self.assertFalse(result.ok)
        self.assertIn("escalation_conflict", [entry.code for entry in result.errors])

    def test_ambiguous_precedence_is_rejected(self) -> None:
        bad_precedence = (
            "policy_load_parse",
            "schema_validity",
            "schema_validity",
            "fsm_invariants",
            "dead_letter_guard",
            "failure_class_retryable",
            "criticality_bypass",
            "risk_budget",
            "time_window_routing",
            "dedupe_suppression",
        )
        result = verify_policy_static({}, precedence_order=bad_precedence)
        self.assertFalse(result.ok)
        self.assertIn("precedence_ambiguous", [entry.code for entry in result.errors])

    def test_verify_policy_or_raise_on_error(self) -> None:
        with self.assertRaises(PolicyVerificationError):
            verify_policy_or_raise({}, precedence_order=SPEC_PRECEDENCE_ORDER[:-1])

    def test_invalid_policy_surfaces_as_policy_invalid(self) -> None:
        result = verify_policy_static({"retry": "bad"})
        self.assertFalse(result.ok)
        self.assertIn("policy_invalid", [entry.code for entry in result.errors])


if __name__ == "__main__":
    unittest.main()
