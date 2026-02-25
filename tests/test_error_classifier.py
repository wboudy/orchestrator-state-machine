#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.error_classifier import ErrorClassifierError, classify_error


class ErrorClassifierTests(unittest.TestCase):
    def test_known_retriable_class(self) -> None:
        classification = classify_error("timeout")
        self.assertEqual(classification.normalized_error_class, "timeout")
        self.assertTrue(classification.retryable)
        self.assertTrue(classification.known)

    def test_known_non_retriable_class(self) -> None:
        classification = classify_error("policy_invalid")
        self.assertEqual(classification.normalized_error_class, "policy_invalid")
        self.assertFalse(classification.retryable)
        self.assertTrue(classification.known)

    def test_alias_normalization(self) -> None:
        classification = classify_error("Rate-Limit")
        self.assertEqual(classification.normalized_error_class, "rate_limited")
        self.assertTrue(classification.retryable)
        self.assertTrue(classification.known)

    def test_unknown_maps_to_unknown_error(self) -> None:
        classification = classify_error("something-totally-new")
        self.assertEqual(classification.normalized_error_class, "unknown_error")
        self.assertTrue(classification.retryable)
        self.assertFalse(classification.known)

    def test_none_maps_to_unknown_error(self) -> None:
        classification = classify_error(None)
        self.assertEqual(classification.normalized_error_class, "unknown_error")
        self.assertTrue(classification.retryable)
        self.assertFalse(classification.known)

    def test_non_string_raises(self) -> None:
        with self.assertRaises(ErrorClassifierError):
            classify_error(123)  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
