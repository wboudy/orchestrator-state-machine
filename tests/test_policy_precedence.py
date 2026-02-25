#!/usr/bin/env python3
from dataclasses import replace
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.policy_precedence import (
    DecisionResult,
    ModelRoute,
    PRECEDENCE_ORDER,
    PrecedenceContext,
    evaluate_policy_precedence,
)


def _base_context() -> PrecedenceContext:
    return PrecedenceContext(
        policy_loaded=True,
        schema_valid=True,
        fsm_valid=True,
        retry_count=0,
        max_retries=3,
        error_class="timeout",
        is_critical=False,
        risk_budget_allows=True,
        in_business_hours=True,
        dedupe_hit=False,
        signature_trust_score=0.6,
        signature_samples=10,
        signature_min_samples=5,
    )


class PolicyPrecedenceTests(unittest.TestCase):
    def test_retriable_error_returns_retry_before_escalation(self) -> None:
        decision = evaluate_policy_precedence(_base_context())
        self.assertEqual(decision.result, DecisionResult.RETRY)
        self.assertEqual(decision.error_class, "timeout")

    def test_retry_exhaustion_queues_noncritical_offhours(self) -> None:
        context = replace(_base_context(), retry_count=3, error_class="timeout", in_business_hours=False)
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.HUMAN_REQUIRED_QUEUED)
        self.assertEqual(decision.error_class, "timeout")

    def test_non_retriable_critical_bypasses_budget(self) -> None:
        context = replace(_base_context(), error_class="auth_failed", is_critical=True, risk_budget_allows=False)
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.HUMAN_REQUIRED)
        self.assertEqual(decision.error_class, "auth_failed")

    def test_dedupe_suppression_path(self) -> None:
        context = replace(_base_context(), retry_count=3, error_class="timeout", dedupe_hit=True)
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.HUMAN_REQUIRED_SUPPRESSED)

    def test_signature_trust_route_selected(self) -> None:
        context = replace(_base_context(), retry_count=3, error_class="timeout", signature_trust_score=0.82)
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.HUMAN_REQUIRED)
        self.assertEqual(decision.model_route, ModelRoute.SHALLOW)

    def test_missing_input_fails_closed_with_policy_ambiguous(self) -> None:
        context = replace(_base_context(), schema_valid=None)
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.HUMAN_REQUIRED)
        self.assertEqual(decision.error_class, "policy_ambiguous")

    def test_unknown_error_class_normalizes_to_unknown_error_retry(self) -> None:
        context = replace(_base_context(), error_class="totally_new_error")
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.RETRY)
        self.assertEqual(decision.error_class, "unknown_error")

    def test_missing_budget_decision_fails_closed(self) -> None:
        context = replace(_base_context(), retry_count=3, error_class="timeout", risk_budget_allows=None)
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.HUMAN_REQUIRED)
        self.assertEqual(decision.error_class, "policy_ambiguous")
        self.assertEqual(decision.decision_path[-1].step, "risk_budget")

    def test_invalid_retry_counters_fail_closed(self) -> None:
        context = replace(_base_context(), retry_count=-1)
        decision = evaluate_policy_precedence(context)
        self.assertEqual(decision.result, DecisionResult.HUMAN_REQUIRED)
        self.assertEqual(decision.error_class, "policy_ambiguous")
        self.assertEqual(decision.decision_path[-1].step, "dead_letter_guard")

    def test_decision_path_order_matches_spec_prefix(self) -> None:
        context = replace(_base_context(), retry_count=3, error_class="auth_failed", is_critical=True)
        decision = evaluate_policy_precedence(context)
        executed_steps = tuple(step.step for step in decision.decision_path)
        self.assertEqual(executed_steps, PRECEDENCE_ORDER[: len(executed_steps)])


if __name__ == "__main__":
    unittest.main()
