from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
from typing import Any, Dict

from watcher.error_classifier import classify_error


class CommandStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class WatcherResult(str, Enum):
    SUCCESS = "success"
    RETRY = "retry"
    HUMAN_REQUIRED = "human_required"
    SUCCESS_WITH_EXIT_MISMATCH = "success_with_exit_mismatch"


@dataclass(frozen=True)
class CommandEnvelope:
    run_id: str
    exit_code: int
    status: CommandStatus
    error_class: str | None


@dataclass(frozen=True)
class CommandReconciliation:
    watcher_result: WatcherResult
    normalized_error_class: str | None
    requires_reconciliation: bool
    reason: str


class CommandAdapterError(ValueError):
    pass


def parse_command_envelope(payload: Dict[str, Any]) -> CommandEnvelope:
    if not isinstance(payload, dict):
        raise CommandAdapterError("command envelope must be an object")

    required = {"run_id", "exit_code", "status"}
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise CommandAdapterError("missing command envelope fields: " + ",".join(missing))

    run_id_raw = payload["run_id"]
    if not isinstance(run_id_raw, str):
        raise CommandAdapterError("run_id invalid")
    run_id = run_id_raw.strip()
    if not run_id:
        raise CommandAdapterError("run_id invalid")

    exit_code = _coerce_exit_code(payload["exit_code"])

    raw_status = payload["status"]
    if not isinstance(raw_status, str):
        raise CommandAdapterError("status invalid")
    normalized_status = raw_status.strip().lower()
    try:
        status = CommandStatus(normalized_status)
    except ValueError as exc:
        raise CommandAdapterError("status invalid") from exc

    error_class = payload.get("error_class")
    if error_class is not None:
        if not isinstance(error_class, str):
            raise CommandAdapterError("error_class invalid")
        error_class = error_class.strip() or None

    return CommandEnvelope(
        run_id=run_id,
        exit_code=exit_code,
        status=status,
        error_class=error_class,
    )


def reconcile_command_envelope(
    envelope: CommandEnvelope,
    *,
    terminal_success_observed: bool,
) -> CommandReconciliation:
    if envelope.status == CommandStatus.SUCCESS:
        if envelope.exit_code == 0:
            return CommandReconciliation(
                watcher_result=WatcherResult.SUCCESS,
                normalized_error_class=None,
                requires_reconciliation=False,
                reason="command_reported_success",
            )
        if terminal_success_observed:
            return CommandReconciliation(
                watcher_result=WatcherResult.SUCCESS_WITH_EXIT_MISMATCH,
                normalized_error_class=None,
                requires_reconciliation=True,
                reason="success_observed_despite_exit_mismatch",
            )
        return _failure_reconciliation(
            error_class=envelope.error_class,
            reason="success_status_with_nonzero_exit_treated_as_failure",
            requires_reconciliation=True,
        )

    if envelope.status == CommandStatus.PARTIAL:
        if terminal_success_observed:
            return CommandReconciliation(
                watcher_result=WatcherResult.SUCCESS_WITH_EXIT_MISMATCH,
                normalized_error_class=None,
                requires_reconciliation=True,
                reason="partial_reconciled_to_success",
            )
        return _failure_reconciliation(
            error_class=envelope.error_class,
            reason="partial_requires_failure_path_without_success_reconciliation",
            requires_reconciliation=True,
        )

    # CommandStatus.FAILURE
    if terminal_success_observed:
        return CommandReconciliation(
            watcher_result=WatcherResult.SUCCESS_WITH_EXIT_MISMATCH,
            normalized_error_class=None,
            requires_reconciliation=True,
            reason="failure_reconciled_to_success",
        )
    return _failure_reconciliation(
        error_class=envelope.error_class,
        reason="command_reported_failure",
        requires_reconciliation=False,
    )


def _failure_reconciliation(
    *,
    error_class: str | None,
    reason: str,
    requires_reconciliation: bool,
) -> CommandReconciliation:
    classified = classify_error(error_class)
    if classified.retryable:
        return CommandReconciliation(
            watcher_result=WatcherResult.RETRY,
            normalized_error_class=classified.normalized_error_class,
            requires_reconciliation=requires_reconciliation,
            reason=reason,
        )
    return CommandReconciliation(
        watcher_result=WatcherResult.HUMAN_REQUIRED,
        normalized_error_class=classified.normalized_error_class,
        requires_reconciliation=requires_reconciliation,
        reason=reason,
    )


def _coerce_exit_code(raw_exit_code: Any) -> int:
    """Coerce exit_code payloads to integers while rejecting ambiguous values."""
    if isinstance(raw_exit_code, bool):
        raise CommandAdapterError("exit_code invalid")

    if isinstance(raw_exit_code, int):
        return raw_exit_code

    if isinstance(raw_exit_code, float):
        if not math.isfinite(raw_exit_code) or not raw_exit_code.is_integer():
            raise CommandAdapterError("exit_code invalid")
        return int(raw_exit_code)

    if isinstance(raw_exit_code, str):
        stripped = raw_exit_code.strip()
        if not stripped:
            raise CommandAdapterError("exit_code invalid")
        try:
            parsed = float(stripped)
        except ValueError as exc:
            raise CommandAdapterError("exit_code invalid") from exc
        if not math.isfinite(parsed) or not parsed.is_integer():
            raise CommandAdapterError("exit_code invalid")
        return int(parsed)

    raise CommandAdapterError("exit_code invalid")
