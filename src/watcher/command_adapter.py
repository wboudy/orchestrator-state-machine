from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
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

    run_id = payload["run_id"]
    if not isinstance(run_id, str) or not run_id.strip():
        raise CommandAdapterError("run_id invalid")

    exit_code = payload["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise CommandAdapterError("exit_code invalid")

    raw_status = payload["status"]
    try:
        status = CommandStatus(raw_status)
    except ValueError as exc:
        raise CommandAdapterError("status invalid") from exc

    error_class = payload.get("error_class")
    if error_class is not None and (not isinstance(error_class, str) or not error_class.strip()):
        raise CommandAdapterError("error_class invalid")

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
