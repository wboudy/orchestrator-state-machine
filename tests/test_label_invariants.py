#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.label_invariants import (
    ERROR_CLASS_FSM_INVALID,
    validate_and_normalize_labels,
)


class LabelInvariantTests(unittest.TestCase):
    def test_valid_state_unchanged(self) -> None:
        result = validate_and_normalize_labels(["needs:orchestrator", "model:deep"])
        self.assertTrue(result.valid)
        self.assertEqual(result.action, "unchanged")
        self.assertEqual(result.normalized_labels, ["needs:orchestrator", "model:deep"])

    def test_missing_primary_is_normalized_to_queued(self) -> None:
        result = validate_and_normalize_labels(["model:deep"])
        self.assertFalse(result.valid)
        self.assertEqual(result.action, "normalized")
        self.assertIn("missing primary state label", result.violations)
        self.assertIn("needs:orchestrator", result.normalized_labels)

    def test_partial_claim_combo_normalizes_to_running(self) -> None:
        result = validate_and_normalize_labels(["needs:orchestrator", "orchestrator:running"])
        self.assertFalse(result.valid)
        self.assertEqual(result.action, "normalized")
        self.assertEqual(result.normalized_labels, ["orchestrator:running"])

    def test_ambiguous_multi_state_escalates(self) -> None:
        result = validate_and_normalize_labels(["orchestrator:running", "orchestrator:done", "model:deep"])
        self.assertFalse(result.valid)
        self.assertEqual(result.action, "escalated")
        self.assertEqual(result.error_class, ERROR_CLASS_FSM_INVALID)
        self.assertIn("orchestrator:dead", result.normalized_labels)
        self.assertIn("needs:human", result.normalized_labels)
        self.assertNotIn("orchestrator:running", result.normalized_labels)
        self.assertNotIn("orchestrator:done", result.normalized_labels)

    def test_needs_human_invalid_coexistence_escalates(self) -> None:
        result = validate_and_normalize_labels(["orchestrator:running", "needs:human"])
        self.assertFalse(result.valid)
        self.assertEqual(result.action, "escalated")
        self.assertEqual(result.error_class, ERROR_CLASS_FSM_INVALID)
        self.assertEqual(result.normalized_labels[:2], ["orchestrator:dead", "needs:human"])


if __name__ == "__main__":
    unittest.main()

