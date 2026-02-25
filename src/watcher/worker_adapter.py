from __future__ import annotations

from dataclasses import dataclass
from typing import List

from watcher.handoff_parser import HandoffPayload


@dataclass(frozen=True)
class OriginResumeContext:
    origin_id: str
    bug_id: str
    bug_closed: bool
    dependency_present: bool
    origin_blocked: bool
    origin_in_progress: bool


@dataclass(frozen=True)
class OriginResumeDecision:
    can_resume: bool
    reason: str
    actions: List[str]


class WorkerAdapterError(ValueError):
    pass


def emit_worker_handoff_block(payload: HandoffPayload) -> str:
    if not isinstance(payload, HandoffPayload):
        raise WorkerAdapterError("payload must be a HandoffPayload")

    return (
        "handoff:\n"
        f"  origin_id: {payload.origin_id}\n"
        f"  bug_id: {payload.bug_id}\n"
        f"  error_signature: {payload.error_signature}\n"
        f"  expected_minutes: {payload.expected_minutes}\n"
        f"  estimated_loc: {payload.estimated_loc}\n"
        f"  touches_api_or_schema: {'true' if payload.touches_api_or_schema else 'false'}\n"
        f"  touches_security_or_auth: {'true' if payload.touches_security_or_auth else 'false'}\n"
        f"  quick_test_available: {'true' if payload.quick_test_available else 'false'}\n"
    )


def evaluate_origin_resume(context: OriginResumeContext) -> OriginResumeDecision:
    if not context.origin_id or not context.bug_id:
        raise WorkerAdapterError("origin_id and bug_id are required")

    if not context.bug_closed:
        return OriginResumeDecision(
            can_resume=False,
            reason="bug_not_closed",
            actions=[],
        )

    if context.dependency_present:
        return OriginResumeDecision(
            can_resume=False,
            reason="origin_dependency_still_present",
            actions=["remove_origin_bug_dependency"],
        )

    if context.origin_in_progress:
        return OriginResumeDecision(
            can_resume=False,
            reason="origin_already_in_progress",
            actions=[],
        )

    actions: List[str] = []
    if context.origin_blocked:
        actions.append("set_origin_in_progress")
    else:
        actions.append("ensure_origin_active")

    return OriginResumeDecision(
        can_resume=True,
        reason="resume_ready",
        actions=actions,
    )
