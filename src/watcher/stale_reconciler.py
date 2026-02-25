from datetime import datetime, timedelta, timezone

from watcher.fsm import FSMEvent, FSMState, TransitionResult, execute_transition
from watcher.state_store import StateRecord


def is_stale_running(
    record: StateRecord,
    now_utc: datetime,
    stale_after_seconds: int,
) -> bool:
    if stale_after_seconds <= 0:
        raise ValueError("stale_after_seconds must be > 0")
    if record.state != FSMState.RUNNING.value:
        return False

    last_transition = _from_rfc3339(record.last_transition_at)
    return (now_utc - last_transition) >= timedelta(seconds=stale_after_seconds)


def reconcile_stale_running(
    record: StateRecord,
    now_utc: datetime,
    stale_after_seconds: int,
    retry_count: int,
    max_retries: int,
    retry_backoff_seconds: int = 60,
) -> TransitionResult | None:
    if record.state != FSMState.RUNNING.value:
        raise ValueError("reconcile_stale_running requires RUNNING state")

    if not is_stale_running(record, now_utc, stale_after_seconds):
        return None

    next_retry_at = _to_rfc3339(now_utc + timedelta(seconds=retry_backoff_seconds))
    return execute_transition(
        FSMState.RUNNING,
        FSMEvent.COMMAND_FAILED,
        error_class="stale_run",
        retry_count=retry_count,
        max_retries=max_retries,
        next_retry_at=next_retry_at,
    )


def _to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _from_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

