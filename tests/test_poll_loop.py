#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.poll_loop import BeadSnapshot, poll_loop, select_eligible_queued


def _valid_handoff_notes(bug_id: str) -> str:
    return f"""
handoff:
  origin_id: osm-4x3
  bug_id: {bug_id}
  error_signature: schema_invalid_case
  expected_minutes: 15
  estimated_loc: 80
  touches_api_or_schema: false
  touches_security_or_auth: false
  quick_test_available: true
"""


class PollLoopTests(unittest.TestCase):
    def test_select_eligible_filters_and_orders_deterministically(self) -> None:
        snapshots = [
            BeadSnapshot(
                bead_id="osm-a",
                priority=2,
                updated_at="2026-02-25T12:00:00Z",
                labels=["needs:orchestrator"],
                notes_text=_valid_handoff_notes("osm-a.1"),
            ),
            BeadSnapshot(
                bead_id="osm-b",
                priority=1,
                updated_at="2026-02-25T12:00:01Z",
                labels=["needs:orchestrator"],
                notes_text=_valid_handoff_notes("osm-b.1"),
            ),
            BeadSnapshot(
                bead_id="osm-c",
                priority=1,
                updated_at="2026-02-25T12:00:02Z",
                labels=["needs:orchestrator", "orchestrator:running"],
                notes_text=_valid_handoff_notes("osm-c.1"),
            ),
            BeadSnapshot(
                bead_id="osm-d",
                priority=1,
                updated_at="2026-02-25T12:00:03Z",
                labels=["needs:orchestrator"],
                notes_text="handoff:\n  origin_id: BAD\n",
            ),
            BeadSnapshot(
                bead_id="osm-e",
                priority=1,
                updated_at="2026-02-25T12:00:04Z",
                labels=["needs:orchestrator", "needs:human"],
                notes_text=_valid_handoff_notes("osm-e.1"),
            ),
        ]

        selected = select_eligible_queued(snapshots)
        self.assertEqual([item.bead_id for item in selected], ["osm-b", "osm-a"])

    def test_select_eligible_respects_limit(self) -> None:
        snapshots = [
            BeadSnapshot(
                bead_id=f"osm-{idx}",
                priority=1,
                updated_at=f"2026-02-25T12:00:0{idx}Z",
                labels=["needs:orchestrator"],
                notes_text=_valid_handoff_notes(f"osm-{idx}.1"),
            )
            for idx in range(3)
        ]
        selected = select_eligible_queued(snapshots, limit=2)
        self.assertEqual(len(selected), 2)

    def test_poll_loop_rejects_nonpositive_interval(self) -> None:
        with self.assertRaises(ValueError):
            list(poll_loop(lambda: [], poll_seconds=0, max_cycles=1))

    def test_poll_loop_runs_max_cycles_and_calls_sleep(self) -> None:
        sleep_calls = []

        def fake_sleep(seconds: float) -> None:
            sleep_calls.append(seconds)

        snapshots = [
            BeadSnapshot(
                bead_id="osm-run",
                priority=1,
                updated_at="2026-02-25T12:00:00Z",
                labels=["needs:orchestrator"],
                notes_text=_valid_handoff_notes("osm-run.1"),
            )
        ]

        cycles = list(
            poll_loop(
                lambda: snapshots,
                poll_seconds=3,
                max_cycles=2,
                sleep_fn=fake_sleep,
            )
        )

        self.assertEqual(len(cycles), 2)
        self.assertEqual([len(c) for c in cycles], [1, 1])
        self.assertEqual(sleep_calls, [3])


if __name__ == "__main__":
    unittest.main()

