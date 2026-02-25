from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
from typing import Any, Dict


HANDOFF_KEY_RE = re.compile(r"^[a-f0-9]{8,64}$")
ERROR_CLASS_RE = re.compile(r"^[a-z0-9_:-]{3,64}$")
STATE_VALUES = {"QUEUED", "RUNNING", "RETRY_WAIT", "DONE", "HUMAN_REQUIRED"}
RESULT_VALUES = {"success", "retry", "human_required"}
RISK_BUDGET_VALUES = {"allow", "defer", "bypass-critical"}

REQUIRED_FIELDS = {
    "handoff_key",
    "state_from",
    "state_to",
    "attempt",
    "result",
    "timestamp",
}

OPTIONAL_FIELDS = {
    "error_class",
    "policy_version",
    "replay_artifact",
    "capsule_artifact",
    "risk_budget_decision",
    "signature_trust_score",
}


@dataclass(frozen=True)
class WatcherRunAppendResult:
    offset_bytes: int
    bytes_written: int
    record: Dict[str, Any]


class WatcherRunValidationError(ValueError):
    pass


def validate_watcher_run(record: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(record, dict):
        raise WatcherRunValidationError("watcher_run record must be an object")

    unknown_fields = [field for field in record.keys() if field not in REQUIRED_FIELDS and field not in OPTIONAL_FIELDS]
    if unknown_fields:
        raise WatcherRunValidationError(f"unknown fields: {','.join(sorted(unknown_fields))}")

    missing_fields = [field for field in REQUIRED_FIELDS if field not in record]
    if missing_fields:
        raise WatcherRunValidationError(f"missing fields: {','.join(sorted(missing_fields))}")

    handoff_key = record["handoff_key"]
    if not isinstance(handoff_key, str) or not HANDOFF_KEY_RE.match(handoff_key):
        raise WatcherRunValidationError("handoff_key invalid")

    state_from = record["state_from"]
    state_to = record["state_to"]
    if state_from not in STATE_VALUES:
        raise WatcherRunValidationError("state_from invalid")
    if state_to not in STATE_VALUES:
        raise WatcherRunValidationError("state_to invalid")

    attempt = record["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise WatcherRunValidationError("attempt invalid")

    result = record["result"]
    if result not in RESULT_VALUES:
        raise WatcherRunValidationError("result invalid")

    timestamp = record["timestamp"]
    timestamp_utc = _parse_rfc3339_utc(timestamp)

    normalized: Dict[str, Any] = {
        "handoff_key": handoff_key,
        "state_from": state_from,
        "state_to": state_to,
        "attempt": attempt,
        "result": result,
        "timestamp": timestamp_utc.isoformat().replace("+00:00", "Z"),
    }

    if "error_class" in record and record["error_class"] is not None:
        error_class = record["error_class"]
        if not isinstance(error_class, str) or not ERROR_CLASS_RE.match(error_class):
            raise WatcherRunValidationError("error_class invalid")
        normalized["error_class"] = error_class

    if "policy_version" in record and record["policy_version"] is not None:
        policy_version = record["policy_version"]
        if not isinstance(policy_version, str) or not policy_version.strip():
            raise WatcherRunValidationError("policy_version invalid")
        normalized["policy_version"] = policy_version

    if "replay_artifact" in record and record["replay_artifact"] is not None:
        replay_artifact = record["replay_artifact"]
        if not isinstance(replay_artifact, str) or not replay_artifact.strip():
            raise WatcherRunValidationError("replay_artifact invalid")
        normalized["replay_artifact"] = replay_artifact

    if "capsule_artifact" in record and record["capsule_artifact"] is not None:
        capsule_artifact = record["capsule_artifact"]
        if not isinstance(capsule_artifact, str) or not capsule_artifact.strip():
            raise WatcherRunValidationError("capsule_artifact invalid")
        normalized["capsule_artifact"] = capsule_artifact

    if "risk_budget_decision" in record and record["risk_budget_decision"] is not None:
        decision = record["risk_budget_decision"]
        if decision not in RISK_BUDGET_VALUES:
            raise WatcherRunValidationError("risk_budget_decision invalid")
        normalized["risk_budget_decision"] = decision

    if "signature_trust_score" in record and record["signature_trust_score"] is not None:
        score = record["signature_trust_score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise WatcherRunValidationError("signature_trust_score invalid")
        score_value = float(score)
        if score_value < 0 or score_value > 1:
            raise WatcherRunValidationError("signature_trust_score invalid")
        normalized["signature_trust_score"] = score_value

    return normalized


def append_watcher_run(log_path: str | Path, record: Dict[str, Any]) -> WatcherRunAppendResult:
    normalized = validate_watcher_run(record)

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = Path(f"{path}.lock")

    with lock_path.open("a+") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            _ensure_attempt_not_already_recorded(path, normalized["handoff_key"], normalized["attempt"])
            payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n"
            encoded = payload.encode("utf-8")

            fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o644)
            try:
                offset = os.lseek(fd, 0, os.SEEK_END)
                os.write(fd, encoded)
                os.fsync(fd)
            finally:
                os.close(fd)

            return WatcherRunAppendResult(
                offset_bytes=offset,
                bytes_written=len(encoded),
                record=normalized,
            )
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _ensure_attempt_not_already_recorded(path: Path, handoff_key: str, attempt: int) -> None:
    if not path.exists():
        return

    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if (
                isinstance(payload, dict)
                and payload.get("handoff_key") == handoff_key
                and payload.get("attempt") == attempt
            ):
                raise WatcherRunValidationError("duplicate handoff_key+attempt entry")


def _parse_rfc3339_utc(raw_value: Any) -> datetime:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise WatcherRunValidationError("timestamp invalid")

    raw = raw_value.strip()
    try:
        if raw.endswith("Z"):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise WatcherRunValidationError("timestamp invalid") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WatcherRunValidationError("timestamp invalid")
    return parsed.astimezone(timezone.utc)
