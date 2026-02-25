from dataclasses import dataclass
from enum import Enum
from typing import List


class FSMState(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRY_WAIT = "RETRY_WAIT"
    DONE = "DONE"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class FSMEvent(str, Enum):
    CLAIM_READY = "CLAIM_READY"
    COMMAND_SUCCEEDED = "COMMAND_SUCCEEDED"
    COMMAND_FAILED = "COMMAND_FAILED"
    COOLDOWN_EXPIRED = "COOLDOWN_EXPIRED"
    FORCE_HUMAN = "FORCE_HUMAN"


NON_RETRIABLE_ERROR_CLASSES = {
    "schema_invalid",
    "auth_failed",
    "permission_denied",
    "bad_input",
    "policy_invalid",
}


@dataclass(frozen=True)
class TransitionResult:
    from_state: FSMState
    to_state: FSMState
    add_labels: List[str]
    remove_labels: List[str]
    reason: str
    error_class: str | None = None
    next_retry_at: str | None = None


class FSMTransitionError(ValueError):
    pass


def execute_transition(
    current_state: FSMState,
    event: FSMEvent,
    *,
    lock_acquired: bool = True,
    claim_succeeded: bool = True,
    error_class: str | None = None,
    retry_count: int = 0,
    max_retries: int = 3,
    next_retry_at: str | None = None,
) -> TransitionResult:
    if event == FSMEvent.CLAIM_READY:
        if current_state != FSMState.QUEUED:
            raise FSMTransitionError("CLAIM_READY valid only from QUEUED")
        if not lock_acquired or not claim_succeeded:
            raise FSMTransitionError("CLAIM_READY requires lock acquisition and claim success")
        return TransitionResult(
            from_state=current_state,
            to_state=FSMState.RUNNING,
            add_labels=["orchestrator:running"],
            remove_labels=["needs:orchestrator", "orchestrator:failed", "orchestrator:dead"],
            reason="queued_claimed",
        )

    if event == FSMEvent.COMMAND_SUCCEEDED:
        if current_state != FSMState.RUNNING:
            raise FSMTransitionError("COMMAND_SUCCEEDED valid only from RUNNING")
        return TransitionResult(
            from_state=current_state,
            to_state=FSMState.DONE,
            add_labels=["orchestrator:done"],
            remove_labels=[
                "orchestrator:running",
                "orchestrator:failed",
                "orchestrator:dead",
                "needs:human",
            ],
            reason="command_success",
        )

    if event == FSMEvent.COMMAND_FAILED:
        if current_state not in (FSMState.RUNNING, FSMState.RETRY_WAIT):
            raise FSMTransitionError("COMMAND_FAILED valid only from RUNNING or RETRY_WAIT")
        if not error_class:
            raise FSMTransitionError("COMMAND_FAILED requires error_class")

        exhausted = retry_count >= max_retries
        non_retriable = error_class in NON_RETRIABLE_ERROR_CLASSES
        if exhausted or non_retriable:
            return TransitionResult(
                from_state=current_state,
                to_state=FSMState.HUMAN_REQUIRED,
                add_labels=["needs:human", "orchestrator:dead"],
                remove_labels=["needs:orchestrator", "orchestrator:running"],
                reason="retry_exhausted_or_non_retriable",
                error_class=error_class,
            )

        if current_state != FSMState.RUNNING:
            raise FSMTransitionError("Retriable failure transition requires RUNNING state")
        if not next_retry_at:
            raise FSMTransitionError("Retriable failure requires next_retry_at")

        return TransitionResult(
            from_state=current_state,
            to_state=FSMState.RETRY_WAIT,
            add_labels=["orchestrator:failed"],
            remove_labels=["orchestrator:running"],
            reason="command_failure_retriable",
            error_class=error_class,
            next_retry_at=next_retry_at,
        )

    if event == FSMEvent.COOLDOWN_EXPIRED:
        if current_state != FSMState.RETRY_WAIT:
            raise FSMTransitionError("COOLDOWN_EXPIRED valid only from RETRY_WAIT")
        if not lock_acquired or not claim_succeeded:
            raise FSMTransitionError("COOLDOWN_EXPIRED requires lock acquisition and claim success")
        return TransitionResult(
            from_state=current_state,
            to_state=FSMState.RUNNING,
            add_labels=["orchestrator:running"],
            remove_labels=["orchestrator:failed", "needs:orchestrator"],
            reason="retry_cooldown_elapsed",
        )

    if event == FSMEvent.FORCE_HUMAN:
        if current_state == FSMState.DONE:
            raise FSMTransitionError("FORCE_HUMAN invalid from DONE")
        return TransitionResult(
            from_state=current_state,
            to_state=FSMState.HUMAN_REQUIRED,
            add_labels=["needs:human"],
            remove_labels=["needs:orchestrator", "orchestrator:running"],
            reason="forced_human_escalation",
            error_class=error_class,
        )

    raise FSMTransitionError(f"Unsupported event: {event}")

