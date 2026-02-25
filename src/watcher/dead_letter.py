from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from watcher.error_classifier import ErrorClassifierError, classify_error
from watcher.fsm import FSMEvent, FSMState, FSMTransitionError, TransitionResult, execute_transition
from watcher.retry_scheduler import format_rfc3339_utc
from watcher.state_store import StateRecord


@dataclass(frozen=True)
class DeadLetterDecision:
    should_dead_letter: bool
    reason: str
    normalized_error_class: str


class DeadLetterError(ValueError):
    pass


def evaluate_dead_letter(
    *,
    error_class: str,
    retry_count: int,
    max_retries: int,
) -> DeadLetterDecision:
    if isinstance(retry_count, bool) or not isinstance(retry_count, int) or retry_count < 0:
        raise DeadLetterError("retry_count must be a non-negative integer")
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
        raise DeadLetterError("max_retries must be a non-negative integer")

    try:
        classified = classify_error(error_class)
    except ErrorClassifierError as exc:
        raise DeadLetterError(str(exc)) from exc

    if retry_count >= max_retries:
        return DeadLetterDecision(
            should_dead_letter=True,
            reason="retry_exhausted",
            normalized_error_class=classified.normalized_error_class,
        )
    if not classified.retryable:
        return DeadLetterDecision(
            should_dead_letter=True,
            reason="non_retriable_error",
            normalized_error_class=classified.normalized_error_class,
        )
    return DeadLetterDecision(
        should_dead_letter=False,
        reason="retry_budget_remaining",
        normalized_error_class=classified.normalized_error_class,
    )


def build_dead_letter_transition(
    *,
    current_state: FSMState,
    error_class: str,
    retry_count: int,
    max_retries: int,
) -> TransitionResult | None:
    decision = evaluate_dead_letter(
        error_class=error_class,
        retry_count=retry_count,
        max_retries=max_retries,
    )
    if not decision.should_dead_letter:
        return None

    try:
        result = execute_transition(
            current_state,
            FSMEvent.COMMAND_FAILED,
            error_class=decision.normalized_error_class,
            retry_count=retry_count,
            max_retries=max_retries,
        )
    except FSMTransitionError as exc:
        raise DeadLetterError(str(exc)) from exc

    if result.to_state != FSMState.HUMAN_REQUIRED:
        raise DeadLetterError("dead-letter transition must end in HUMAN_REQUIRED")
    if "orchestrator:dead" not in result.add_labels or "needs:human" not in result.add_labels:
        raise DeadLetterError("dead-letter transition must add orchestrator:dead and needs:human")
    return result


def build_dead_letter_record(
    *,
    current_record: StateRecord,
    now_utc: datetime,
    error_class: str,
    owner_id: str | None,
) -> StateRecord:
    try:
        classified = classify_error(error_class)
    except ErrorClassifierError as exc:
        raise DeadLetterError(str(exc)) from exc

    return StateRecord(
        state="HUMAN_REQUIRED",
        attempt=current_record.attempt,
        last_transition_at=format_rfc3339_utc(now_utc),
        next_retry_at=None,
        last_error_class=classified.normalized_error_class,
        owner_id=owner_id,
        version=current_record.version,
    )
