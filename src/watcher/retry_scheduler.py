from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import random
from typing import Iterable, List, Sequence


@dataclass(frozen=True)
class RetryScheduleResult:
    attempt: int
    base_delay_seconds: int
    jitter_factor: float
    delay_seconds: int
    next_retry_at: datetime


class RetryScheduleError(ValueError):
    pass


def compute_retry_schedule(
    *,
    now_utc: datetime,
    attempt: int,
    backoff_seconds: Sequence[int],
    jitter_pct: int,
    jitter_unit: float | None = None,
) -> RetryScheduleResult:
    validated_now = _validate_now(now_utc)
    validated_attempt = _validate_attempt(attempt)
    validated_backoff = _validate_backoff(backoff_seconds)
    validated_jitter_pct = _validate_jitter_pct(jitter_pct)

    index = min(validated_attempt - 1, len(validated_backoff) - 1)
    base_delay = validated_backoff[index]

    if jitter_unit is None:
        jitter_unit = random.uniform(-1.0, 1.0)
    if jitter_unit < -1.0 or jitter_unit > 1.0:
        raise RetryScheduleError("jitter_unit must be in [-1.0, 1.0]")

    jitter_factor = 1 + (jitter_unit * (validated_jitter_pct / 100.0))
    delay_seconds = max(1, round(base_delay * jitter_factor))
    next_retry_at = validated_now + timedelta(seconds=delay_seconds)

    return RetryScheduleResult(
        attempt=validated_attempt,
        base_delay_seconds=base_delay,
        jitter_factor=jitter_factor,
        delay_seconds=delay_seconds,
        next_retry_at=next_retry_at,
    )


def format_rfc3339_utc(timestamp: datetime) -> str:
    normalized = _validate_now(timestamp)
    return normalized.isoformat().replace("+00:00", "Z")


def _validate_now(now_utc: datetime) -> datetime:
    if not isinstance(now_utc, datetime):
        raise RetryScheduleError("now_utc must be a datetime")
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise RetryScheduleError("now_utc must be timezone-aware UTC")

    normalized = now_utc.astimezone(timezone.utc)
    return normalized


def _validate_attempt(attempt: int) -> int:
    if isinstance(attempt, bool) or not isinstance(attempt, int):
        raise RetryScheduleError("attempt must be an integer")
    if attempt < 1:
        raise RetryScheduleError("attempt must be >= 1")
    return attempt


def _validate_backoff(backoff_seconds: Sequence[int]) -> List[int]:
    if not isinstance(backoff_seconds, Iterable):
        raise RetryScheduleError("backoff_seconds must be a non-empty list of positive integers")
    values = list(backoff_seconds)
    if not values:
        raise RetryScheduleError("backoff_seconds must be a non-empty list of positive integers")
    for value in values:
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise RetryScheduleError("backoff_seconds must contain positive integers only")
    return values


def _validate_jitter_pct(jitter_pct: int) -> int:
    if isinstance(jitter_pct, bool) or not isinstance(jitter_pct, int):
        raise RetryScheduleError("jitter_pct must be an integer")
    if jitter_pct < 0 or jitter_pct > 100:
        raise RetryScheduleError("jitter_pct must be in [0, 100]")
    return jitter_pct
