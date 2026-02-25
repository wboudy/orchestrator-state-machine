#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.handoff_parser import HandoffValidationError, parse_handoff_block


class HandoffParserTests(unittest.TestCase):
    def test_parse_valid_handoff_block(self) -> None:
        notes = """
Some lead-in text.

handoff:
  origin_id: osm-4x3
  bug_id: osm-4x3.3
  error_signature: schema_invalid_case
  expected_minutes: 25
  estimated_loc: 120
  touches_api_or_schema: false
  touches_security_or_auth: true
  quick_test_available: true

Tail content after handoff.
"""
        payload = parse_handoff_block(notes)

        self.assertEqual(payload.origin_id, "osm-4x3")
        self.assertEqual(payload.bug_id, "osm-4x3.3")
        self.assertEqual(payload.expected_minutes, 25)
        self.assertEqual(payload.estimated_loc, 120)
        self.assertFalse(payload.touches_api_or_schema)
        self.assertTrue(payload.touches_security_or_auth)
        self.assertTrue(payload.quick_test_available)

    def test_missing_handoff_block_raises(self) -> None:
        with self.assertRaises(HandoffValidationError) as exc:
            parse_handoff_block("notes without a handoff block")
        self.assertIn("handoff block missing", exc.exception.errors)

    def test_invalid_schema_values_raise(self) -> None:
        notes = """
handoff:
  origin_id: BAD_ID
  bug_id: OSM 4x3.4
  error_signature: short
  expected_minutes: 999
  estimated_loc: -1
  touches_api_or_schema: maybe
  touches_security_or_auth: false
  quick_test_available: true
"""
        with self.assertRaises(HandoffValidationError) as exc:
            parse_handoff_block(notes)

        errors = exc.exception.errors
        self.assertIn("origin_id invalid", errors)
        self.assertIn("bug_id invalid", errors)
        self.assertIn("error_signature invalid", errors)
        self.assertIn("expected_minutes invalid", errors)
        self.assertIn("estimated_loc invalid", errors)
        self.assertIn("touches_api_or_schema invalid", errors)


if __name__ == "__main__":
    unittest.main()

