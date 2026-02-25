#!/usr/bin/env python3
from datetime import datetime, timezone
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.digest_builder import DigestBuilderError, IncidentRecord, build_daily_digest


def _incident(
    *,
    incident_id: str,
    signature: str,
    origin: str,
    priority: int,
    created_at: datetime,
    unresolved: bool = True,
    dead_letter: bool = False,
    suppressed: bool = False,
    deferred: bool = False,
) -> IncidentRecord:
    return IncidentRecord(
        incident_id=incident_id,
        error_signature=signature,
        origin_id=origin,
        priority=priority,
        created_at_utc=created_at,
        unresolved_needs_human=unresolved,
        dead_letter=dead_letter,
        suppressed_by_dedupe=suppressed,
        deferred_by_budget=deferred,
    )


class DigestBuilderTests(unittest.TestCase):
    def test_build_daily_digest_scores_and_sorts_clusters(self) -> None:
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc)
        incidents = [
            _incident(
                incident_id="i-1",
                signature="auth_failed_case",
                origin="osm-a",
                priority=1,
                created_at=datetime(2026, 2, 25, 12, 0, 0, tzinfo=timezone.utc),
                unresolved=True,
                dead_letter=True,
            ),
            _incident(
                incident_id="i-2",
                signature="auth_failed_case",
                origin="osm-b",
                priority=2,
                created_at=datetime(2026, 2, 24, 12, 0, 0, tzinfo=timezone.utc),
                unresolved=True,
                suppressed=True,
            ),
            _incident(
                incident_id="i-3",
                signature="timeout_case",
                origin="osm-c",
                priority=3,
                created_at=datetime(2026, 2, 26, 10, 0, 0, tzinfo=timezone.utc),
                unresolved=False,
                deferred=True,
            ),
        ]
        digest = build_daily_digest(incidents=incidents, now_utc=now, timezone_name="America/New_York")

        self.assertEqual(digest.date_local, "2026-02-26")
        self.assertEqual(digest.timezone, "America/New_York")
        self.assertEqual(digest.new_escalations, 2)
        self.assertEqual(digest.dead_letter_count, 1)
        self.assertEqual(digest.suppressed_by_dedupe, 1)
        self.assertEqual(digest.deferred_by_budget, 1)
        self.assertEqual(len(digest.clusters), 2)
        self.assertEqual(digest.clusters[0].error_signature, "auth_failed_case")
        self.assertGreater(digest.clusters[0].score, digest.clusters[1].score)

    def test_age_weight_capped_at_seven(self) -> None:
        now = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
        incidents = [
            _incident(
                incident_id="i-1",
                signature="old_case",
                origin="osm-a",
                priority=2,
                created_at=datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc),
                unresolved=True,
            )
        ]
        digest = build_daily_digest(incidents=incidents, now_utc=now, timezone_name="UTC")
        self.assertEqual(digest.clusters[0].cluster_age_days, 28)
        self.assertEqual(digest.clusters[0].age_weight, 7)

    def test_invalid_priority_raises(self) -> None:
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc)
        incidents = [
            _incident(
                incident_id="i-1",
                signature="case",
                origin="osm-a",
                priority=9,
                created_at=datetime(2026, 2, 26, 11, 0, 0, tzinfo=timezone.utc),
            )
        ]
        with self.assertRaises(DigestBuilderError):
            build_daily_digest(incidents=incidents, now_utc=now, timezone_name="UTC")

    def test_invalid_timezone_raises(self) -> None:
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=timezone.utc)
        with self.assertRaises(DigestBuilderError):
            build_daily_digest(incidents=[], now_utc=now, timezone_name="Not/AZone")


if __name__ == "__main__":
    unittest.main()
