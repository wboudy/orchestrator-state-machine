from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Set


RETRIABLE_ERROR_CLASSES: Set[str] = {
    "timeout",
    "rate_limited",
    "upstream_unavailable",
    "network_error",
    "state_conflict",
    "stale_run",
    "unknown_error",
}

NON_RETRIABLE_ERROR_CLASSES: Set[str] = {
    "schema_invalid",
    "auth_failed",
    "permission_denied",
    "bad_input",
    "policy_invalid",
}

ALIAS_MAP: Dict[str, str] = {
    "timed_out": "timeout",
    "timeout_error": "timeout",
    "too_many_requests": "rate_limited",
    "rate_limit": "rate_limited",
    "rate-limit": "rate_limited",
    "service_unavailable": "upstream_unavailable",
    "upstream_failure": "upstream_unavailable",
    "connection_error": "network_error",
    "network_timeout": "network_error",
    "conflict": "state_conflict",
    "schema_error": "schema_invalid",
    "unauthorized": "auth_failed",
    "forbidden": "permission_denied",
    "invalid_input": "bad_input",
    "invalid_request": "bad_input",
}


@dataclass(frozen=True)
class ErrorClassification:
    original: str | None
    normalized_error_class: str
    retryable: bool
    known: bool


class ErrorClassifierError(ValueError):
    pass


def classify_error(raw_error_class: str | None) -> ErrorClassification:
    if raw_error_class is None:
        return ErrorClassification(
            original=None,
            normalized_error_class="unknown_error",
            retryable=True,
            known=False,
        )

    if not isinstance(raw_error_class, str):
        raise ErrorClassifierError("raw_error_class must be a string or None")

    normalized = _normalize(raw_error_class)
    if not normalized:
        return ErrorClassification(
            original=raw_error_class,
            normalized_error_class="unknown_error",
            retryable=True,
            known=False,
        )

    normalized = ALIAS_MAP.get(normalized, normalized)
    if normalized in RETRIABLE_ERROR_CLASSES:
        return ErrorClassification(
            original=raw_error_class,
            normalized_error_class=normalized,
            retryable=True,
            known=True,
        )

    if normalized in NON_RETRIABLE_ERROR_CLASSES:
        return ErrorClassification(
            original=raw_error_class,
            normalized_error_class=normalized,
            retryable=False,
            known=True,
        )

    return ErrorClassification(
        original=raw_error_class,
        normalized_error_class="unknown_error",
        retryable=True,
        known=False,
    )


def _normalize(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace("-", "_")
    normalized = re.sub(r"\s+", "_", normalized)
    normalized = re.sub(r"[^a-z0-9_]+", "", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized
