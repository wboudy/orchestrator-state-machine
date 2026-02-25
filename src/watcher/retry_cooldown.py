from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from watcher.retry_scheduler import format_rfc3339_utc
from watcher.state_store import StateRecord


@dataclass(frozen=True)
class CooldownGateDecision:
    ready: bool
    wait_seconds: int
    next_retry_at: datetime | None
    reason: str


class CooldownGateError(ValueError):
    pass


def evaluate_retry_cooldown(next_retry_at: str | None, now_utc: datetime) -> CooldownGateDecision:
    now = _validate_aware_utc(now_utc, "now_utc")
    if next_retry_at is None:
        return CooldownGateDecision(
            ready=True,
            wait_seconds=0,
            next_retry_at=None,
            reason="no_cooldown",
        )

    retry_at = parse_rfc3339_utc(next_retry_at)
    delta_seconds = int((retry_at - now).total_seconds())
    if delta_seconds <= 0:
        return CooldownGateDecision(
            ready=True,
            wait_seconds=0,
            next_retry_at=retry_at,
            reason="cooldown_elapsed",
        )
    return CooldownGateDecision(
        ready=False,
        wait_seconds=delta_seconds,
        next_retry_at=retry_at,
        reason="cooldown_active",
    )


def build_retry_wait_record(
    current_record: StateRecord | None,
    *,
    now_utc: datetime,
    next_retry_at: datetime,
    error_class: str,
    owner_id: str | None,
) -> StateRecord:
    now = _validate_aware_utc(now_utc, "now_utc")
    retry_at = _validate_aware_utc(next_retry_at, "next_retry_at")
    if not error_class or not isinstance(error_class, str):
        raise CooldownGateError("error_class must be a non-empty string")

    next_attempt = 1 if current_record is None else current_record.attempt + 1
    return StateRecord(
        state="RETRY_WAIT",
        attempt=next_attempt,
        last_transition_at=format_rfc3339_utc(now),
        next_retry_at=format_rfc3339_utc(retry_at),
        last_error_class=error_class,
        owner_id=owner_id,
        version=current_record.version if current_record else 0,
    )


def build_retry_resume_record(
    current_record: StateRecord,
    *,
    now_utc: datetime,
    owner_id: str | None,
) -> StateRecord:
    now = _validate_aware_utc(now_utc, "now_utc")
    if current_record.state != "RETRY_WAIT":
        raise CooldownGateError("resume record requires RETRY_WAIT state")

    return StateRecord(
        state="RUNNING",
        attempt=current_record.attempt,
        last_transition_at=format_rfc3339_utc(now),
        next_retry_at=None,
        last_error_class=current_record.last_error_class,
        owner_id=owner_id,
        version=current_record.version,
    )


def parse_rfc3339_utc(timestamp: str) -> datetime:
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise CooldownGateError("timestamp must be a non-empty string")

    raw = timestamp.strip()
    try:
        if raw.endswith("Z"):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CooldownGateError(f"invalid RFC3339 timestamp: {timestamp}") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CooldownGateError("timestamp must include UTC offset")
    return parsed.astimezone(timezone.utc)


def _validate_aware_utc(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime):
        raise CooldownGateError(f"{field_name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise CooldownGateError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)
