#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.command_adapter import (
    CommandAdapterError,
    CommandStatus,
    WatcherResult,
    parse_command_envelope,
    reconcile_command_envelope,
)


class CommandAdapterTests(unittest.TestCase):
    def test_parse_command_envelope_success(self) -> None:
        envelope = parse_command_envelope(
            {
                "run_id": "run-1",
                "exit_code": 0,
                "status": "success",
            }
        )
        self.assertEqual(envelope.run_id, "run-1")
        self.assertEqual(envelope.exit_code, 0)
        self.assertEqual(envelope.status, CommandStatus.SUCCESS)

    def test_parse_command_envelope_rejects_invalid(self) -> None:
        with self.assertRaises(CommandAdapterError):
            parse_command_envelope({"run_id": "run-1", "status": "success"})
        with self.assertRaises(CommandAdapterError):
            parse_command_envelope({"run_id": "run-1", "exit_code": 0, "status": "ok"})

    def test_parse_command_envelope_normalizes_string_fields(self) -> None:
        envelope = parse_command_envelope(
            {
                "run_id": "  run-1  ",
                "exit_code": " 1 ",
                "status": " FAILURE ",
                "error_class": " timeout ",
            }
        )
        self.assertEqual(envelope.run_id, "run-1")
        self.assertEqual(envelope.exit_code, 1)
        self.assertEqual(envelope.status, CommandStatus.FAILURE)
        self.assertEqual(envelope.error_class, "timeout")

    def test_parse_command_envelope_blank_error_class_maps_to_none(self) -> None:
        envelope = parse_command_envelope(
            {
                "run_id": "run-1",
                "exit_code": 0,
                "status": "success",
                "error_class": "   ",
            }
        )
        self.assertIsNone(envelope.error_class)

    def test_parse_command_envelope_rejects_fractional_exit_codes(self) -> None:
        with self.assertRaises(CommandAdapterError):
            parse_command_envelope({"run_id": "run-1", "exit_code": "1.5", "status": "success"})

    def test_success_status_zero_exit_is_success(self) -> None:
        envelope = parse_command_envelope({"run_id": "run-1", "exit_code": 0, "status": "success"})
        outcome = reconcile_command_envelope(envelope, terminal_success_observed=False)
        self.assertEqual(outcome.watcher_result, WatcherResult.SUCCESS)

    def test_partial_without_reconciliation_is_failure_path(self) -> None:
        envelope = parse_command_envelope(
            {
                "run_id": "run-1",
                "exit_code": 1,
                "status": "partial",
                "error_class": "timeout",
            }
        )
        outcome = reconcile_command_envelope(envelope, terminal_success_observed=False)
        self.assertEqual(outcome.watcher_result, WatcherResult.RETRY)
        self.assertEqual(outcome.normalized_error_class, "timeout")
        self.assertTrue(outcome.requires_reconciliation)

    def test_partial_with_terminal_success_reconciles(self) -> None:
        envelope = parse_command_envelope(
            {
                "run_id": "run-1",
                "exit_code": 1,
                "status": "partial",
                "error_class": "timeout",
            }
        )
        outcome = reconcile_command_envelope(envelope, terminal_success_observed=True)
        self.assertEqual(outcome.watcher_result, WatcherResult.SUCCESS_WITH_EXIT_MISMATCH)
        self.assertIsNone(outcome.normalized_error_class)

    def test_failure_non_retriable_maps_to_human_required(self) -> None:
        envelope = parse_command_envelope(
            {
                "run_id": "run-1",
                "exit_code": 1,
                "status": "failure",
                "error_class": "auth_failed",
            }
        )
        outcome = reconcile_command_envelope(envelope, terminal_success_observed=False)
        self.assertEqual(outcome.watcher_result, WatcherResult.HUMAN_REQUIRED)
        self.assertEqual(outcome.normalized_error_class, "auth_failed")

    def test_success_nonzero_exit_without_reconciliation_treated_as_failure(self) -> None:
        envelope = parse_command_envelope(
            {
                "run_id": "run-1",
                "exit_code": 2,
                "status": "success",
                "error_class": "timeout",
            }
        )
        outcome = reconcile_command_envelope(envelope, terminal_success_observed=False)
        self.assertEqual(outcome.watcher_result, WatcherResult.RETRY)
        self.assertEqual(outcome.normalized_error_class, "timeout")


if __name__ == "__main__":
    unittest.main()
