#!/usr/bin/env python3
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.replay_handoff import ReplayHandoffError, replay_handoff_run
from watcher.run_artifact_emitter import emit_run_artifact


def _artifact_record(*, status: str, transition_result: str, transition_to: str) -> dict:
    return {
        "timestamp": "2026-02-25T23:50:00Z",
        "handoff_key": "a1b2c3d4e5f6a7b8",
        "attempt": 1,
        "inputs": {
            "labels": ["needs:orchestrator"],
            "notes_snapshot_hash": "sha256:notes",
            "policy_hash": "sha256:policy",
            "local_time_eval": {"tz": "America/New_York", "local_time": "2026-02-25T18:50:00-05:00"},
        },
        "decision_path": [{"step": "policy_load_parse", "outcome": "pass"}],
        "command_envelope": {
            "run_id": "run-1",
            "exit_code": 0,
            "status": status,
        },
        "transition": {
            "from": "RUNNING",
            "to": transition_to,
            "result": transition_result,
        },
    }


class ReplayHandoffTests(unittest.TestCase):
    def test_replay_success_parity_match(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = emit_run_artifact(
                artifacts_root=pathlib.Path(temp_dir) / ".beads" / "orchestrator-runs",
                record=_artifact_record(status="success", transition_result="success", transition_to="DONE"),
            )
            outcome = replay_handoff_run(run_file=artifact_path, dry_run=True)
            self.assertTrue(outcome.parity_match)
            self.assertEqual(outcome.expected_result, "success")

    def test_partial_status_treated_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = emit_run_artifact(
                artifacts_root=pathlib.Path(temp_dir) / ".beads" / "orchestrator-runs",
                record=_artifact_record(status="partial", transition_result="success", transition_to="DONE"),
            )
            outcome = replay_handoff_run(run_file=artifact_path, dry_run=True)
            self.assertFalse(outcome.parity_match)
            self.assertEqual(outcome.expected_result, "retry")

    def test_invalid_multiline_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            run_file = pathlib.Path(temp_dir) / "bad.jsonl"
            run_file.write_text("{}\n{}\n", encoding="utf-8")
            with self.assertRaises(ReplayHandoffError):
                replay_handoff_run(run_file=run_file, dry_run=True)

    def test_cli_dry_run_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_path = emit_run_artifact(
                artifacts_root=pathlib.Path(temp_dir) / ".beads" / "orchestrator-runs",
                record=_artifact_record(status="failure", transition_result="human_required", transition_to="HUMAN_REQUIRED"),
            )
            cmd = [sys.executable, str(ROOT / "scripts" / "replay_handoff.py"), "--run-file", str(artifact_path), "--dry-run"]
            completed = subprocess.run(cmd, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            payload = json.loads(completed.stdout.strip())
            self.assertEqual(payload["expected_result"], "human_required")
            self.assertTrue(payload["dry_run"])


if __name__ == "__main__":
    unittest.main()
