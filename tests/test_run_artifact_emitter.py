#!/usr/bin/env python3
import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.run_artifact_emitter import (
    RunArtifactValidationError,
    emit_run_artifact,
    validate_run_artifact,
)


def _valid_artifact(*, attempt: int = 1) -> dict:
    return {
        "timestamp": "2026-02-25T23:40:00Z",
        "handoff_key": "a1b2c3d4e5f6a7b8",
        "attempt": attempt,
        "inputs": {
            "labels": ["needs:orchestrator", "orchestrator:running"],
            "notes_snapshot_hash": "sha256:notes123",
            "policy_hash": "sha256:policy123",
            "local_time_eval": {"tz": "America/New_York", "local_time": "2026-02-25T18:40:00-05:00"},
        },
        "decision_path": [
            {"step": "policy_load_parse", "outcome": "pass"},
            {"step": "schema_validity", "outcome": "pass"},
        ],
        "command_envelope": {
            "run_id": "run-001",
            "exit_code": 0,
            "status": "success",
        },
        "transition": {
            "from": "RUNNING",
            "to": "DONE",
            "result": "success",
        },
    }


class RunArtifactEmitterTests(unittest.TestCase):
    def test_validate_run_artifact_success(self) -> None:
        normalized = validate_run_artifact(_valid_artifact())
        self.assertEqual(normalized["attempt"], 1)
        self.assertEqual(normalized["command_envelope"]["status"], "success")
        self.assertEqual(normalized["transition"]["result"], "success")

    def test_validation_rejects_missing_fields(self) -> None:
        bad = _valid_artifact()
        del bad["decision_path"]
        with self.assertRaises(RunArtifactValidationError):
            validate_run_artifact(bad)

    def test_validation_rejects_invalid_command_status(self) -> None:
        bad = _valid_artifact()
        bad["command_envelope"]["status"] = "ok"
        with self.assertRaises(RunArtifactValidationError):
            validate_run_artifact(bad)

    def test_emit_run_artifact_writes_expected_path_and_content(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir) / ".beads" / "orchestrator-runs"
            path = emit_run_artifact(artifacts_root=root, record=_valid_artifact(attempt=2))
            self.assertEqual(path, root / "a1b2c3d4e5f6a7b8" / "2.jsonl")
            payload = json.loads(path.read_text().strip())
            self.assertEqual(payload["attempt"], 2)
            self.assertEqual(payload["handoff_key"], "a1b2c3d4e5f6a7b8")

    def test_emit_run_artifact_is_immutable_per_attempt_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = pathlib.Path(temp_dir) / ".beads" / "orchestrator-runs"
            emit_run_artifact(artifacts_root=root, record=_valid_artifact(attempt=1))
            with self.assertRaises(FileExistsError):
                emit_run_artifact(artifacts_root=root, record=_valid_artifact(attempt=1))


if __name__ == "__main__":
    unittest.main()
