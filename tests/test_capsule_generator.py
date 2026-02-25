#!/usr/bin/env python3
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.capsule_generator import CapsuleGenerationError, generate_reproducibility_capsule


def _payload() -> dict:
    return {
        "handoff_key": "a1b2c3d4e5f6a7b8",
        "attempt": 1,
        "timestamp": "2026-02-26T00:00:00Z",
        "reproduction_steps": [
            "Run orchestrator command",
            "Observe failure in logs",
        ],
        "observed": "Authorization header leaked in envelope",
        "expected": "Sensitive values should be redacted",
        "command_envelope": {
            "run_id": "run-100",
            "authorization": "Bearer top.secret.value",
        },
        "logs": [
            "token=abcdef",
            "path=/Users/testuser/private/debug.log",
        ],
        "metadata": {
            "policy_hash": "sha256:policy1",
            "project_path": "/Users/testuser/Desktop/project/src",
        },
    }


class CapsuleGeneratorTests(unittest.TestCase):
    def test_generate_capsule_writes_redacted_markdown(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_root = pathlib.Path(temp_dir) / ".beads" / "orchestrator-capsules"
            path = generate_reproducibility_capsule(
                artifacts_root=artifacts_root,
                capsule_payload=_payload(),
                project_root="/Users/testuser/Desktop/project",
                home_dir="/Users/testuser",
            )
            self.assertEqual(path, artifacts_root / "a1b2c3d4e5f6a7b8" / "1.md")

            content = path.read_text(encoding="utf-8")
            self.assertIn("# Reproducibility Capsule", content)
            self.assertIn("<REDACTED>", content)
            self.assertIn("<HOME>/private/debug.log", content)
            self.assertNotIn("top.secret.value", content)

    def test_redaction_failure_fails_closed_without_writing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_root = pathlib.Path(temp_dir) / ".beads" / "orchestrator-capsules"
            payload = _payload()
            payload["metadata"] = {"bad": {1, 2, 3}}
            with self.assertRaises(CapsuleGenerationError):
                generate_reproducibility_capsule(
                    artifacts_root=artifacts_root,
                    capsule_payload=payload,
                    project_root="/Users/testuser/Desktop/project",
                    home_dir="/Users/testuser",
                )
            self.assertFalse((artifacts_root / "a1b2c3d4e5f6a7b8" / "1.md").exists())

    def test_capsule_file_is_immutable_per_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts_root = pathlib.Path(temp_dir) / ".beads" / "orchestrator-capsules"
            generate_reproducibility_capsule(
                artifacts_root=artifacts_root,
                capsule_payload=_payload(),
                project_root="/Users/testuser/Desktop/project",
                home_dir="/Users/testuser",
            )
            with self.assertRaises(FileExistsError):
                generate_reproducibility_capsule(
                    artifacts_root=artifacts_root,
                    capsule_payload=_payload(),
                    project_root="/Users/testuser/Desktop/project",
                    home_dir="/Users/testuser",
                )

    def test_invalid_payload_rejected(self) -> None:
        payload = _payload()
        del payload["reproduction_steps"]
        with self.assertRaises(CapsuleGenerationError):
            generate_reproducibility_capsule(
                artifacts_root="/tmp/unused",
                capsule_payload=payload,
                project_root="/Users/testuser/Desktop/project",
                home_dir="/Users/testuser",
            )


if __name__ == "__main__":
    unittest.main()
