from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

from watcher.error_classifier import ErrorClassifierError, classify_error


PRECEDENCE_ORDER: Tuple[str, ...] = (
    "policy_load_parse",
    "schema_validity",
    "fsm_invariants",
    "dead_letter_guard",
    "failure_class_retryable",
    "criticality_bypass",
    "risk_budget",
    "time_window_routing",
    "dedupe_suppression",
    "signature_trust_routing",
)

class DecisionResult(str, Enum):
    RETRY = "retry"
    HUMAN_REQUIRED = "human_required"
    HUMAN_REQUIRED_QUEUED = "human_required_queued"
    HUMAN_REQUIRED_SUPPRESSED = "human_required_suppressed"


class ModelRoute(str, Enum):
    SHALLOW = "shallow"
    NORMAL = "normal"
    DEEP = "deep"


@dataclass(frozen=True)
class PrecedenceContext:
    policy_loaded: bool | None
    schema_valid: bool | None
    fsm_valid: bool | None
    retry_count: int | None
    max_retries: int | None
    error_class: str | None
    is_critical: bool | None
    risk_budget_allows: bool | None
    in_business_hours: bool | None
    dedupe_hit: bool | None
    signature_trust_score: float | None
    signature_samples: int | None = None
    signature_min_samples: int | None = None


@dataclass(frozen=True)
class DecisionStep:
    step: str
    outcome: str
    detail: str


@dataclass(frozen=True)
class PrecedenceDecision:
    result: DecisionResult
    error_class: str | None
    model_route: ModelRoute | None
    decision_path: Tuple[DecisionStep, ...]


def evaluate_policy_precedence(context: PrecedenceContext) -> PrecedenceDecision:
    path: List[DecisionStep] = []

    if context.policy_loaded is None:
        return _fail_closed(path, "policy_load_parse", "missing policy_loaded input")
    if context.policy_loaded is False:
        path.append(DecisionStep("policy_load_parse", "fail", "policy invalid"))
        return PrecedenceDecision(
            result=DecisionResult.HUMAN_REQUIRED,
            error_class="policy_invalid",
            model_route=None,
            decision_path=tuple(path),
        )
    path.append(DecisionStep("policy_load_parse", "pass", "policy loaded"))

    if context.schema_valid is None:
        return _fail_closed(path, "schema_validity", "missing schema_valid input")
    if context.schema_valid is False:
        path.append(DecisionStep("schema_validity", "fail", "handoff/state schema invalid"))
        return PrecedenceDecision(
            result=DecisionResult.HUMAN_REQUIRED,
            error_class="schema_invalid",
            model_route=None,
            decision_path=tuple(path),
        )
    path.append(DecisionStep("schema_validity", "pass", "schema valid"))

    if context.fsm_valid is None:
        return _fail_closed(path, "fsm_invariants", "missing fsm_valid input")
    if context.fsm_valid is False:
        path.append(DecisionStep("fsm_invariants", "fail", "fsm invariant violation"))
        return _policy_ambiguous(path)
    path.append(DecisionStep("fsm_invariants", "pass", "fsm valid"))

    dead_letter, dead_letter_error = _evaluate_dead_letter(context.retry_count, context.max_retries)
    if dead_letter_error is not None:
        return _fail_closed(path, "dead_letter_guard", dead_letter_error)
    path.append(
        DecisionStep(
            "dead_letter_guard",
            "pass" if not dead_letter else "triggered",
            "retry cap reached" if dead_letter else "retry budget remaining",
        )
    )

    failure_result, normalized_error_class = _evaluate_failure_class(context.error_class)
    if failure_result == "ambiguous":
        return _fail_closed(path, "failure_class_retryable", "invalid error_class value")

    if failure_result == "retriable":
        if normalized_error_class is None:
            return _fail_closed(path, "failure_class_retryable", "missing normalized error class")
        path.append(
            DecisionStep(
                "failure_class_retryable",
                "retriable",
                f"error class retriable ({normalized_error_class})",
            )
        )
        if dead_letter:
            path.append(DecisionStep("failure_class_retryable", "escalate", "retry exhausted"))
        else:
            return PrecedenceDecision(
                result=DecisionResult.RETRY,
                error_class=normalized_error_class,
                model_route=None,
                decision_path=tuple(path),
            )
    elif failure_result == "non_retriable":
        if normalized_error_class is None:
            return _fail_closed(path, "failure_class_retryable", "missing normalized error class")
        path.append(
            DecisionStep(
                "failure_class_retryable",
                "non_retriable",
                f"error class requires human escalation ({normalized_error_class})",
            )
        )
    else:
        return _fail_closed(path, "failure_class_retryable", "missing error_class")

    if context.is_critical is None:
        return _fail_closed(path, "criticality_bypass", "missing criticality input")
    if context.is_critical:
        path.append(DecisionStep("criticality_bypass", "bypass", "critical incident immediate"))
        return PrecedenceDecision(
            result=DecisionResult.HUMAN_REQUIRED,
            error_class=normalized_error_class,
            model_route=None,
            decision_path=tuple(path),
        )
    path.append(DecisionStep("criticality_bypass", "pass", "non-critical incident"))

    if context.risk_budget_allows is None:
        return _fail_closed(path, "risk_budget", "missing risk_budget decision")
    if not context.risk_budget_allows:
        path.append(DecisionStep("risk_budget", "defer", "over noncritical budget"))
        return PrecedenceDecision(
            result=DecisionResult.HUMAN_REQUIRED_QUEUED,
            error_class=normalized_error_class,
            model_route=None,
            decision_path=tuple(path),
        )
    path.append(DecisionStep("risk_budget", "pass", "within budget"))

    if context.in_business_hours is None:
        return _fail_closed(path, "time_window_routing", "missing business-hours evaluation")
    if not context.in_business_hours:
        path.append(DecisionStep("time_window_routing", "queue", "off-hours non-critical"))
        return PrecedenceDecision(
            result=DecisionResult.HUMAN_REQUIRED_QUEUED,
            error_class=normalized_error_class,
            model_route=None,
            decision_path=tuple(path),
        )
    path.append(DecisionStep("time_window_routing", "pass", "business hours active"))

    if context.dedupe_hit is None:
        return _fail_closed(path, "dedupe_suppression", "missing dedupe evaluation")
    if context.dedupe_hit:
        path.append(DecisionStep("dedupe_suppression", "suppress", "duplicate within dedupe window"))
        return PrecedenceDecision(
            result=DecisionResult.HUMAN_REQUIRED_SUPPRESSED,
            error_class=normalized_error_class,
            model_route=None,
            decision_path=tuple(path),
        )
    path.append(DecisionStep("dedupe_suppression", "pass", "no dedupe suppression"))

    route, route_error = _route_from_trust(
        trust_score=context.signature_trust_score,
        sample_count=context.signature_samples,
        min_samples=context.signature_min_samples,
    )
    if route_error is not None:
        return _fail_closed(path, "signature_trust_routing", route_error)

    path.append(DecisionStep("signature_trust_routing", "route", f"selected {route.value}"))
    return PrecedenceDecision(
        result=DecisionResult.HUMAN_REQUIRED,
        error_class=normalized_error_class,
        model_route=route,
        decision_path=tuple(path),
    )


def _evaluate_dead_letter(retry_count: int | None, max_retries: int | None) -> Tuple[bool, str | None]:
    if retry_count is None or max_retries is None:
        return False, "missing retry counters"
    if retry_count < 0 or max_retries < 0:
        return False, "invalid retry counters"
    return retry_count >= max_retries, None


def _evaluate_failure_class(error_class: str | None) -> Tuple[str, str | None]:
    if error_class is None:
        return "missing", None
    try:
        classified = classify_error(error_class)
    except ErrorClassifierError:
        return "ambiguous", None
    if classified.retryable:
        return "retriable", classified.normalized_error_class
    return "non_retriable", classified.normalized_error_class


def _route_from_trust(
    *,
    trust_score: float | None,
    sample_count: int | None,
    min_samples: int | None,
) -> Tuple[ModelRoute | None, str | None]:
    if trust_score is None:
        return None, "missing signature trust score"
    if trust_score < 0 or trust_score > 1:
        return None, "invalid signature trust score"

    if sample_count is not None and min_samples is not None and sample_count < min_samples:
        return ModelRoute.NORMAL, None

    if trust_score >= 0.75:
        return ModelRoute.SHALLOW, None
    if trust_score >= 0.45:
        return ModelRoute.NORMAL, None
    return ModelRoute.DEEP, None


def _fail_closed(path: List[DecisionStep], step: str, detail: str) -> PrecedenceDecision:
    path.append(DecisionStep(step, "ambiguous", detail))
    return _policy_ambiguous(path)


def _policy_ambiguous(path: List[DecisionStep]) -> PrecedenceDecision:
    return PrecedenceDecision(
        result=DecisionResult.HUMAN_REQUIRED,
        error_class="policy_ambiguous",
        model_route=None,
        decision_path=tuple(path),
    )
