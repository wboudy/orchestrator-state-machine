#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.policy_defaults import (
    CANONICAL_POLICY_DEFAULTS,
    PolicyDefaultsError,
    inject_canonical_defaults,
    render_snapshot_json,
)


class PolicyDefaultsTests(unittest.TestCase):
    def test_empty_policy_gets_canonical_defaults(self) -> None:
        snapshot = inject_canonical_defaults({})

        self.assertEqual(snapshot.effective_policy, CANONICAL_POLICY_DEFAULTS)
        self.assertIn("timezone", snapshot.defaults_applied)
        self.assertIn("retry.max_retries", snapshot.defaults_applied)
        self.assertIn("risk_budget.max_noncritical_pages_per_hour", snapshot.defaults_applied)
        self.assertEqual(len(snapshot.policy_hash), 64)

    def test_partial_policy_overrides_and_applies_nested_defaults(self) -> None:
        raw_policy = {
            "timezone": "America/Los_Angeles",
            "retry": {"max_retries": 5},
            "trust": {"initial_score": 0.8},
        }
        snapshot = inject_canonical_defaults(raw_policy)

        self.assertEqual(snapshot.effective_policy["timezone"], "America/Los_Angeles")
        self.assertEqual(snapshot.effective_policy["retry"]["max_retries"], 5)
        self.assertEqual(snapshot.effective_policy["retry"]["jitter_pct"], 15)
        self.assertEqual(snapshot.effective_policy["trust"]["initial_score"], 0.8)
        self.assertEqual(snapshot.effective_policy["trust"]["min_samples"], 5)
        self.assertIn("retry.jitter_pct", snapshot.defaults_applied)
        self.assertIn("trust.min_samples", snapshot.defaults_applied)

    def test_unknown_key_fails_closed(self) -> None:
        with self.assertRaises(PolicyDefaultsError) as exc:
            inject_canonical_defaults({"retry": {"unknown_field": 1}})
        self.assertIn("retry.unknown_field unknown", exc.exception.errors)

    def test_non_object_root_rejected(self) -> None:
        with self.assertRaises(PolicyDefaultsError) as exc:
            inject_canonical_defaults("nope")  # type: ignore[arg-type]
        self.assertIn("policy root must be an object", exc.exception.errors)

    def test_snapshot_json_is_deterministic(self) -> None:
        snapshot = inject_canonical_defaults({})
        rendered_one = render_snapshot_json(snapshot)
        rendered_two = render_snapshot_json(snapshot)
        self.assertEqual(rendered_one, rendered_two)
        self.assertIn("\"effective_policy\"", rendered_one)
        self.assertIn("\"policy_hash\"", rendered_one)


if __name__ == "__main__":
    unittest.main()
