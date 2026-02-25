from dataclasses import dataclass
from typing import Iterable, List, Set


PRIMARY_STATE_LABELS = [
    "needs:orchestrator",
    "orchestrator:running",
    "orchestrator:failed",
    "orchestrator:done",
    "orchestrator:dead",
]
PRIMARY_STATE_SET = set(PRIMARY_STATE_LABELS)
HUMAN_LABEL = "needs:human"
ERROR_CLASS_FSM_INVALID = "fsm_invalid"


@dataclass(frozen=True)
class InvariantResult:
    normalized_labels: List[str]
    valid: bool
    action: str  # unchanged | normalized | escalated
    violations: List[str]
    error_class: str | None = None


def validate_and_normalize_labels(labels: Iterable[str]) -> InvariantResult:
    label_set: Set[str] = set(labels)
    violations: List[str] = []
    action = "unchanged"
    error_class = None

    state_labels = _active_state_labels(label_set)

    if len(state_labels) == 0:
        violations.append("missing primary state label")
        label_set.add("needs:orchestrator")
        action = "normalized"
    elif len(state_labels) > 1:
        state_set = set(state_labels)
        if state_set == {"needs:orchestrator", "orchestrator:running"}:
            violations.append("multiple state labels normalized: queued+running")
            label_set.discard("needs:orchestrator")
            action = "normalized"
        elif state_set == {"orchestrator:failed", "orchestrator:dead"}:
            violations.append("multiple state labels normalized: failed+dead")
            label_set.discard("orchestrator:failed")
            action = "normalized"
        else:
            violations.append("ambiguous multiple state labels")
            label_set = _escalate_to_human_required(label_set)
            action = "escalated"
            error_class = ERROR_CLASS_FSM_INVALID

    # Re-evaluate state labels after possible normalization/escalation.
    state_labels = _active_state_labels(label_set)
    state_label = state_labels[0] if state_labels else None

    if HUMAN_LABEL in label_set and state_label not in {"orchestrator:failed", "orchestrator:dead"}:
        violations.append("needs:human invalid coexistence")
        label_set = _escalate_to_human_required(label_set)
        action = "escalated"
        error_class = ERROR_CLASS_FSM_INVALID

    normalized_labels = _ordered_labels(label_set)
    valid = len(violations) == 0
    return InvariantResult(
        normalized_labels=normalized_labels,
        valid=valid,
        action=action,
        violations=violations,
        error_class=error_class,
    )


def _escalate_to_human_required(label_set: Set[str]) -> Set[str]:
    result = set(label_set)
    for state_label in PRIMARY_STATE_LABELS:
        result.discard(state_label)
    result.discard(HUMAN_LABEL)
    result.add("orchestrator:dead")
    result.add(HUMAN_LABEL)
    return result


def _active_state_labels(label_set: Set[str]) -> List[str]:
    return [label for label in PRIMARY_STATE_LABELS if label in label_set]


def _ordered_labels(label_set: Set[str]) -> List[str]:
    state_order = PRIMARY_STATE_LABELS + [HUMAN_LABEL]
    ordered: List[str] = []

    for label in state_order:
        if label in label_set:
            ordered.append(label)

    non_state = sorted(
        label
        for label in label_set
        if label not in PRIMARY_STATE_SET and label != HUMAN_LABEL
    )
    ordered.extend(non_state)
    return ordered

