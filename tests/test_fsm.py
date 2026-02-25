#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.fsm import FSMEvent, FSMState, FSMTransitionError, execute_transition


class FSMTests(unittest.TestCase):
    def test_queued_to_running_claim(self) -> None:
        result = execute_transition(FSMState.QUEUED, FSMEvent.CLAIM_READY)
        self.assertEqual(result.to_state, FSMState.RUNNING)
        self.assertIn("orchestrator:running", result.add_labels)
        self.assertIn("needs:orchestrator", result.remove_labels)

    def test_running_to_done_on_success(self) -> None:
        result = execute_transition(FSMState.RUNNING, FSMEvent.COMMAND_SUCCEEDED)
        self.assertEqual(result.to_state, FSMState.DONE)
        self.assertIn("orchestrator:done", result.add_labels)
        self.assertIn("orchestrator:running", result.remove_labels)

    def test_running_to_retry_wait_on_retriable_failure(self) -> None:
        result = execute_transition(
            FSMState.RUNNING,
            FSMEvent.COMMAND_FAILED,
            error_class="timeout",
            retry_count=1,
            max_retries=3,
            next_retry_at="2026-02-25T12:05:00Z",
        )
        self.assertEqual(result.to_state, FSMState.RETRY_WAIT)
        self.assertEqual(result.error_class, "timeout")
        self.assertEqual(result.next_retry_at, "2026-02-25T12:05:00Z")

    def test_failure_to_human_required_when_non_retriable(self) -> None:
        result = execute_transition(
            FSMState.RUNNING,
            FSMEvent.COMMAND_FAILED,
            error_class="schema_invalid",
            retry_count=0,
            max_retries=3,
        )
        self.assertEqual(result.to_state, FSMState.HUMAN_REQUIRED)
        self.assertIn("needs:human", result.add_labels)
        self.assertIn("orchestrator:dead", result.add_labels)

    def test_retry_wait_to_running_on_cooldown(self) -> None:
        result = execute_transition(FSMState.RETRY_WAIT, FSMEvent.COOLDOWN_EXPIRED)
        self.assertEqual(result.to_state, FSMState.RUNNING)
        self.assertIn("orchestrator:failed", result.remove_labels)

    def test_retriable_failure_requires_next_retry(self) -> None:
        with self.assertRaises(FSMTransitionError):
            execute_transition(
                FSMState.RUNNING,
                FSMEvent.COMMAND_FAILED,
                error_class="timeout",
                retry_count=1,
                max_retries=3,
            )

    def test_invalid_transition_from_done(self) -> None:
        with self.assertRaises(FSMTransitionError):
            execute_transition(FSMState.DONE, FSMEvent.CLAIM_READY)


if __name__ == "__main__":
    unittest.main()

