#!/usr/bin/env python3
from dataclasses import replace
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.state_store import HandoffStateStore, StateRecord


class StateStoreTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStateStore(pathlib.Path(tmp) / "orchestrator-handoff-state.json")
            initial = StateRecord(
                state="RUNNING",
                attempt=1,
                last_transition_at="2026-02-25T12:00:00Z",
                next_retry_at=None,
                last_error_class=None,
                owner_id="worker-a",
            )

            result = store.save("k1", initial, expected_version=0)
            self.assertTrue(result.saved)
            self.assertEqual(result.version, 1)

            loaded = store.load("k1")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.state, "RUNNING")
            self.assertEqual(loaded.version, 1)

    def test_conflict_on_wrong_expected_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStateStore(pathlib.Path(tmp) / "orchestrator-handoff-state.json")
            base = StateRecord(
                state="RUNNING",
                attempt=1,
                last_transition_at="2026-02-25T12:00:00Z",
                next_retry_at=None,
                last_error_class=None,
                owner_id="worker-a",
            )
            store.save("k1", base, expected_version=0)

            conflict = store.save("k1", replace(base, attempt=2), expected_version=0)
            self.assertFalse(conflict.saved)
            self.assertTrue(conflict.conflict)
            self.assertEqual(conflict.version, 1)
            self.assertIsNotNone(conflict.current)
            self.assertEqual(conflict.current.attempt, 1)

    def test_update_atomic_updates_using_existing_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStateStore(pathlib.Path(tmp) / "orchestrator-handoff-state.json")
            base = StateRecord(
                state="RETRY_WAIT",
                attempt=1,
                last_transition_at="2026-02-25T12:00:00Z",
                next_retry_at="2026-02-25T12:05:00Z",
                last_error_class="timeout",
                owner_id=None,
            )
            store.save("k1", base, expected_version=0)

            result = store.update_atomic(
                "k1",
                expected_version=1,
                update_fn=lambda current: replace(
                    current,
                    state="RUNNING",
                    attempt=current.attempt + 1,
                    last_transition_at="2026-02-25T12:05:00Z",
                    next_retry_at=None,
                    owner_id="worker-a",
                ),
            )

            self.assertTrue(result.saved)
            self.assertEqual(result.version, 2)
            loaded = store.load("k1")
            self.assertEqual(loaded.state, "RUNNING")
            self.assertEqual(loaded.attempt, 2)
            self.assertEqual(loaded.version, 2)

    def test_update_atomic_can_initialize_missing_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = HandoffStateStore(pathlib.Path(tmp) / "orchestrator-handoff-state.json")

            result = store.update_atomic(
                "k-new",
                expected_version=0,
                update_fn=lambda current: StateRecord(
                    state="QUEUED",
                    attempt=0,
                    last_transition_at="2026-02-25T12:00:00Z",
                    next_retry_at=None,
                    last_error_class=None,
                    owner_id=None,
                ),
            )

            self.assertTrue(result.saved)
            self.assertEqual(result.version, 1)
            self.assertEqual(store.load("k-new").state, "QUEUED")


if __name__ == "__main__":
    unittest.main()

