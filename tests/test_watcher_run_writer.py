#!/usr/bin/env python3
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.watcher_run_writer import (
    WatcherRunValidationError,
    append_watcher_run,
    validate_watcher_run,
)


def _valid_record(*, attempt: int = 1) -> dict:
    return {
        "handoff_key": "a1b2c3d4e5f6a7b8",
        "state_from": "RUNNING",
        "state_to": "RETRY_WAIT",
        "attempt": attempt,
        "result": "retry",
        "timestamp": "2026-02-25T23:30:00Z",
        "error_class": "timeout",
        "policy_version": "sha256:abc123",
        "replay_artifact": ".beads/orchestrator-runs/a1/1.jsonl",
        "capsule_artifact": ".beads/orchestrator-capsules/a1/1.md",
        "risk_budget_decision": "allow",
        "signature_trust_score": 0.55,
    }


class WatcherRunWriterTests(unittest.TestCase):
    def test_validate_watcher_run_success(self) -> None:
        normalized = validate_watcher_run(_valid_record())
        self.assertEqual(normalized["attempt"], 1)
        self.assertEqual(normalized["result"], "retry")
        self.assertEqual(normalized["timestamp"], "2026-02-25T23:30:00Z")

    def test_validation_rejects_missing_and_unknown_fields(self) -> None:
        bad = _valid_record()
        del bad["handoff_key"]
        with self.assertRaises(WatcherRunValidationError):
            validate_watcher_run(bad)

        bad2 = _valid_record()
        bad2["extra_field"] = "unexpected"
        with self.assertRaises(WatcherRunValidationError):
            validate_watcher_run(bad2)

    def test_validation_rejects_invalid_risk_budget_decision(self) -> None:
        bad = _valid_record()
        bad["risk_budget_decision"] = "later"
        with self.assertRaises(WatcherRunValidationError):
            validate_watcher_run(bad)

    def test_append_is_immutable_and_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = pathlib.Path(temp_dir) / "watcher-runs.jsonl"
            first = append_watcher_run(log_path, _valid_record(attempt=1))
            second = append_watcher_run(log_path, _valid_record(attempt=2))

            self.assertEqual(first.offset_bytes, 0)
            self.assertGreater(second.offset_bytes, first.offset_bytes)
            lines = log_path.read_text().splitlines()
            self.assertEqual(len(lines), 2)

            first_record = json.loads(lines[0])
            second_record = json.loads(lines[1])
            self.assertEqual(first_record["attempt"], 1)
            self.assertEqual(second_record["attempt"], 2)

    def test_append_rejects_duplicate_handoff_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = pathlib.Path(temp_dir) / "watcher-runs.jsonl"
            append_watcher_run(log_path, _valid_record(attempt=1))
            with self.assertRaises(WatcherRunValidationError):
                append_watcher_run(log_path, _valid_record(attempt=1))


if __name__ == "__main__":
    unittest.main()
