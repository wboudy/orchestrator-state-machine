from dataclasses import dataclass
import re
from typing import Any, Dict, List, Tuple


WEEKDAY_VALUES = {"Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"}
TIME_RE = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")
TIMEZONE_RE = re.compile(r"^[A-Za-z_]+(?:/[A-Za-z0-9_+.-]+)+$")

REQUIRED_TOP_LEVEL_KEYS = [
    "timezone",
    "business_hours",
    "retry",
    "risk_budget",
    "dedupe",
    "trust",
]


@dataclass(frozen=True)
class BusinessHoursPolicy:
    weekdays: Tuple[str, ...]
    start: str
    end: str


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int
    backoff_seconds: Tuple[int, ...]
    jitter_pct: int


@dataclass(frozen=True)
class RiskBudgetPolicy:
    max_noncritical_escalations_per_day: int
    max_noncritical_pages_per_hour: int


@dataclass(frozen=True)
class DedupePolicy:
    window_minutes: int


@dataclass(frozen=True)
class TrustPolicy:
    initial_score: float
    min_samples: int


@dataclass(frozen=True)
class OrchestratorPolicy:
    timezone: str
    business_hours: BusinessHoursPolicy
    retry: RetryPolicy
    risk_budget: RiskBudgetPolicy
    dedupe: DedupePolicy
    trust: TrustPolicy


class PolicyValidationError(ValueError):
    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("POLICY_INVALID: " + "; ".join(self.errors))


def validate_policy_mapping(policy: Dict[str, Any]) -> OrchestratorPolicy:
    errors: List[str] = []

    if not isinstance(policy, dict):
        raise PolicyValidationError(["policy root must be an object"])

    _validate_required_keys(policy, errors)
    _validate_no_unknown_keys(policy, REQUIRED_TOP_LEVEL_KEYS, "policy", errors)

    timezone = _validate_timezone(policy.get("timezone"), errors)
    business_hours = _validate_business_hours(policy.get("business_hours"), errors)
    retry = _validate_retry(policy.get("retry"), errors)
    risk_budget = _validate_risk_budget(policy.get("risk_budget"), errors)
    dedupe = _validate_dedupe(policy.get("dedupe"), errors)
    trust = _validate_trust(policy.get("trust"), errors)

    if errors:
        raise PolicyValidationError(errors)

    return OrchestratorPolicy(
        timezone=timezone,
        business_hours=business_hours,
        retry=retry,
        risk_budget=risk_budget,
        dedupe=dedupe,
        trust=trust,
    )


def _validate_required_keys(mapping: Dict[str, Any], errors: List[str]) -> None:
    for key in REQUIRED_TOP_LEVEL_KEYS:
        if key not in mapping:
            errors.append(f"{key} missing")


def _validate_no_unknown_keys(
    mapping: Dict[str, Any],
    allowed_keys: List[str],
    path: str,
    errors: List[str],
) -> None:
    allowed = set(allowed_keys)
    for key in mapping:
        if key not in allowed:
            errors.append(f"{path}.{key} unknown")


def _validate_timezone(raw_value: Any, errors: List[str]) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        errors.append("timezone invalid")
        return ""

    value = raw_value.strip()
    if not TIMEZONE_RE.match(value):
        errors.append("timezone invalid")
        return ""
    return value


def _validate_business_hours(raw_value: Any, errors: List[str]) -> BusinessHoursPolicy:
    field_errors: List[str] = []
    if not isinstance(raw_value, dict):
        errors.append("business_hours invalid")
        return BusinessHoursPolicy(weekdays=(), start="", end="")

    required = ["weekdays", "start", "end"]
    for key in required:
        if key not in raw_value:
            field_errors.append(f"business_hours.{key} missing")
    _validate_no_unknown_keys(raw_value, required, "business_hours", field_errors)

    weekdays = _validate_weekdays(raw_value.get("weekdays"), field_errors)
    start = _validate_hhmm(raw_value.get("start"), "business_hours.start", field_errors)
    end = _validate_hhmm(raw_value.get("end"), "business_hours.end", field_errors)

    if start and end and _hhmm_to_minutes(start) >= _hhmm_to_minutes(end):
        field_errors.append("business_hours range invalid")

    errors.extend(field_errors)
    return BusinessHoursPolicy(weekdays=weekdays, start=start, end=end)


def _validate_weekdays(raw_value: Any, errors: List[str]) -> Tuple[str, ...]:
    if not isinstance(raw_value, list) or not raw_value:
        errors.append("business_hours.weekdays invalid")
        return ()

    parsed: List[str] = []
    seen = set()
    for value in raw_value:
        if not isinstance(value, str) or value not in WEEKDAY_VALUES:
            errors.append("business_hours.weekdays invalid")
            return ()
        if value in seen:
            errors.append("business_hours.weekdays duplicate")
            return ()
        seen.add(value)
        parsed.append(value)
    return tuple(parsed)


def _validate_hhmm(raw_value: Any, field_name: str, errors: List[str]) -> str:
    if not isinstance(raw_value, str):
        errors.append(f"{field_name} invalid")
        return ""
    value = raw_value.strip()
    if not TIME_RE.match(value):
        errors.append(f"{field_name} invalid")
        return ""
    return value


def _validate_retry(raw_value: Any, errors: List[str]) -> RetryPolicy:
    field_errors: List[str] = []
    if not isinstance(raw_value, dict):
        errors.append("retry invalid")
        return RetryPolicy(max_retries=0, backoff_seconds=(), jitter_pct=0)

    required = ["max_retries", "backoff_seconds", "jitter_pct"]
    for key in required:
        if key not in raw_value:
            field_errors.append(f"retry.{key} missing")
    _validate_no_unknown_keys(raw_value, required, "retry", field_errors)

    max_retries = _validate_int_min(raw_value.get("max_retries"), "retry.max_retries", 0, field_errors)
    backoff_seconds = _validate_int_list_min_one(raw_value.get("backoff_seconds"), "retry.backoff_seconds", field_errors)
    jitter_pct = _validate_int_range(raw_value.get("jitter_pct"), "retry.jitter_pct", 0, 100, field_errors)

    errors.extend(field_errors)
    return RetryPolicy(
        max_retries=max_retries,
        backoff_seconds=backoff_seconds,
        jitter_pct=jitter_pct,
    )


def _validate_risk_budget(raw_value: Any, errors: List[str]) -> RiskBudgetPolicy:
    field_errors: List[str] = []
    if not isinstance(raw_value, dict):
        errors.append("risk_budget invalid")
        return RiskBudgetPolicy(
            max_noncritical_escalations_per_day=0,
            max_noncritical_pages_per_hour=0,
        )

    required = ["max_noncritical_escalations_per_day", "max_noncritical_pages_per_hour"]
    for key in required:
        if key not in raw_value:
            field_errors.append(f"risk_budget.{key} missing")
    _validate_no_unknown_keys(raw_value, required, "risk_budget", field_errors)

    max_day = _validate_int_min(
        raw_value.get("max_noncritical_escalations_per_day"),
        "risk_budget.max_noncritical_escalations_per_day",
        0,
        field_errors,
    )
    max_hour = _validate_int_min(
        raw_value.get("max_noncritical_pages_per_hour"),
        "risk_budget.max_noncritical_pages_per_hour",
        0,
        field_errors,
    )

    errors.extend(field_errors)
    return RiskBudgetPolicy(
        max_noncritical_escalations_per_day=max_day,
        max_noncritical_pages_per_hour=max_hour,
    )


def _validate_dedupe(raw_value: Any, errors: List[str]) -> DedupePolicy:
    field_errors: List[str] = []
    if not isinstance(raw_value, dict):
        errors.append("dedupe invalid")
        return DedupePolicy(window_minutes=0)

    required = ["window_minutes"]
    for key in required:
        if key not in raw_value:
            field_errors.append(f"dedupe.{key} missing")
    _validate_no_unknown_keys(raw_value, required, "dedupe", field_errors)

    window_minutes = _validate_int_min(raw_value.get("window_minutes"), "dedupe.window_minutes", 1, field_errors)

    errors.extend(field_errors)
    return DedupePolicy(window_minutes=window_minutes)


def _validate_trust(raw_value: Any, errors: List[str]) -> TrustPolicy:
    field_errors: List[str] = []
    if not isinstance(raw_value, dict):
        errors.append("trust invalid")
        return TrustPolicy(initial_score=0.0, min_samples=0)

    required = ["initial_score", "min_samples"]
    for key in required:
        if key not in raw_value:
            field_errors.append(f"trust.{key} missing")
    _validate_no_unknown_keys(raw_value, required, "trust", field_errors)

    initial_score = _validate_numeric_range(
        raw_value.get("initial_score"),
        "trust.initial_score",
        0.0,
        1.0,
        field_errors,
    )
    min_samples = _validate_int_min(raw_value.get("min_samples"), "trust.min_samples", 1, field_errors)

    errors.extend(field_errors)
    return TrustPolicy(initial_score=initial_score, min_samples=min_samples)


def _validate_int_min(raw_value: Any, field_name: str, minimum: int, errors: List[str]) -> int:
    if not _is_plain_int(raw_value):
        errors.append(f"{field_name} invalid")
        return 0
    if raw_value < minimum:
        errors.append(f"{field_name} invalid")
        return 0
    return raw_value


def _validate_int_range(
    raw_value: Any,
    field_name: str,
    minimum: int,
    maximum: int,
    errors: List[str],
) -> int:
    if not _is_plain_int(raw_value):
        errors.append(f"{field_name} invalid")
        return 0
    if raw_value < minimum or raw_value > maximum:
        errors.append(f"{field_name} invalid")
        return 0
    return raw_value


def _validate_int_list_min_one(raw_value: Any, field_name: str, errors: List[str]) -> Tuple[int, ...]:
    if not isinstance(raw_value, list) or not raw_value:
        errors.append(f"{field_name} invalid")
        return ()

    values: List[int] = []
    for value in raw_value:
        if not _is_plain_int(value) or value < 1:
            errors.append(f"{field_name} invalid")
            return ()
        values.append(value)
    return tuple(values)


def _validate_numeric_range(
    raw_value: Any,
    field_name: str,
    minimum: float,
    maximum: float,
    errors: List[str],
) -> float:
    if isinstance(raw_value, bool):
        errors.append(f"{field_name} invalid")
        return 0.0
    if not isinstance(raw_value, (int, float)):
        errors.append(f"{field_name} invalid")
        return 0.0

    value = float(raw_value)
    if value < minimum or value > maximum:
        errors.append(f"{field_name} invalid")
        return 0.0
    return value


def _is_plain_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _hhmm_to_minutes(value: str) -> int:
    hours_str, minutes_str = value.split(":")
    return int(hours_str) * 60 + int(minutes_str)
