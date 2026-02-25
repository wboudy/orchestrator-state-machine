#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.handoff_parser import HandoffPayload, parse_handoff_block
from watcher.worker_adapter import OriginResumeContext, evaluate_origin_resume, emit_worker_handoff_block


class WorkerAdapterTests(unittest.TestCase):
    def test_emit_worker_handoff_block_contains_full_schema(self) -> None:
        payload = HandoffPayload(
            origin_id="osm-11i",
            bug_id="osm-11i.11",
            error_signature="timeout_case_sig",
            expected_minutes=15,
            estimated_loc=42,
            touches_api_or_schema=True,
            touches_security_or_auth=False,
            quick_test_available=True,
        )
        block = emit_worker_handoff_block(payload)
        self.assertIn("handoff:", block)
        self.assertIn("origin_id: osm-11i", block)
        self.assertIn("quick_test_available: true", block)

        parsed = parse_handoff_block(block)
        self.assertEqual(parsed.origin_id, payload.origin_id)
        self.assertEqual(parsed.bug_id, payload.bug_id)
        self.assertEqual(parsed.error_signature, payload.error_signature)

    def test_resume_ready_when_bug_closed_and_dependency_cleared(self) -> None:
        decision = evaluate_origin_resume(
            OriginResumeContext(
                origin_id="osm-11i",
                bug_id="osm-11i.11",
                bug_closed=True,
                dependency_present=False,
                origin_blocked=True,
                origin_in_progress=False,
            )
        )
        self.assertTrue(decision.can_resume)
        self.assertEqual(decision.reason, "resume_ready")
        self.assertIn("set_origin_in_progress", decision.actions)

    def test_resume_blocked_if_bug_not_closed(self) -> None:
        decision = evaluate_origin_resume(
            OriginResumeContext(
                origin_id="osm-11i",
                bug_id="osm-11i.11",
                bug_closed=False,
                dependency_present=True,
                origin_blocked=True,
                origin_in_progress=False,
            )
        )
        self.assertFalse(decision.can_resume)
        self.assertEqual(decision.reason, "bug_not_closed")

    def test_resume_blocked_if_dependency_still_present(self) -> None:
        decision = evaluate_origin_resume(
            OriginResumeContext(
                origin_id="osm-11i",
                bug_id="osm-11i.11",
                bug_closed=True,
                dependency_present=True,
                origin_blocked=True,
                origin_in_progress=False,
            )
        )
        self.assertFalse(decision.can_resume)
        self.assertEqual(decision.reason, "origin_dependency_still_present")
        self.assertIn("remove_origin_bug_dependency", decision.actions)

    def test_resume_noop_if_already_in_progress(self) -> None:
        decision = evaluate_origin_resume(
            OriginResumeContext(
                origin_id="osm-11i",
                bug_id="osm-11i.11",
                bug_closed=True,
                dependency_present=False,
                origin_blocked=False,
                origin_in_progress=True,
            )
        )
        self.assertFalse(decision.can_resume)
        self.assertEqual(decision.reason, "origin_already_in_progress")


if __name__ == "__main__":
    unittest.main()
