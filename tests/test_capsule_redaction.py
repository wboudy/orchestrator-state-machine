#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.capsule_redaction import REDACTED, RedactionError, redact_capsule_payload


class CapsuleRedactionTests(unittest.TestCase):
    def test_sensitive_keys_are_redacted(self) -> None:
        payload = {
            "api_key": "abc123",
            "nested": {"authToken": "secret-value", "safe": "ok"},
            "list": [{"password": "p@ss"}, {"note": "safe"}],
        }
        redacted = redact_capsule_payload(
            payload,
            project_root="/Users/testuser/Desktop/project",
            home_dir="/Users/testuser",
        )
        self.assertEqual(redacted["api_key"], REDACTED)
        self.assertEqual(redacted["nested"]["authToken"], REDACTED)
        self.assertEqual(redacted["list"][0]["password"], REDACTED)
        self.assertEqual(redacted["nested"]["safe"], "ok")

    def test_bearer_and_basic_tokens_are_redacted(self) -> None:
        payload = {
            "log": "Authorization: Bearer abc.def.ghi and proxy Basic QWxhZGRpbjpPcGVuU2VzYW1l",
        }
        redacted = redact_capsule_payload(
            payload,
            project_root="/Users/testuser/Desktop/project",
            home_dir="/Users/testuser",
        )
        self.assertIn("Bearer <REDACTED>", redacted["log"])
        self.assertIn("Basic <REDACTED>", redacted["log"])
        self.assertNotIn("abc.def.ghi", redacted["log"])

    def test_home_prefix_outside_project_is_masked(self) -> None:
        payload = {
            "log": (
                "outside /Users/testuser/private/token.txt "
                "inside /Users/testuser/Desktop/project/tmp/output.log"
            )
        }
        redacted = redact_capsule_payload(
            payload,
            project_root="/Users/testuser/Desktop/project",
            home_dir="/Users/testuser",
        )
        self.assertIn("<HOME>/private/token.txt", redacted["log"])
        self.assertIn("/Users/testuser/Desktop/project/tmp/output.log", redacted["log"])

    def test_non_string_dict_key_raises(self) -> None:
        payload = {123: "bad"}
        with self.assertRaises(RedactionError):
            redact_capsule_payload(
                payload,
                project_root="/Users/testuser/Desktop/project",
                home_dir="/Users/testuser",
            )

    def test_unsupported_type_raises(self) -> None:
        payload = {"bad": {"set_value": {1, 2, 3}}}
        with self.assertRaises(RedactionError):
            redact_capsule_payload(
                payload,
                project_root="/Users/testuser/Desktop/project",
                home_dir="/Users/testuser",
            )


if __name__ == "__main__":
    unittest.main()
