from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List


HANDOFF_KEY_RE = re.compile(r"^[a-f0-9]{8,64}$")
STATE_VALUES = {"QUEUED", "RUNNING", "RETRY_WAIT", "DONE", "HUMAN_REQUIRED"}
RESULT_VALUES = {"success", "retry", "human_required"}
COMMAND_STATUS_VALUES = {"success", "failure", "partial"}


class RunArtifactValidationError(ValueError):
    pass


def validate_run_artifact(record: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(record, dict):
        raise RunArtifactValidationError("run artifact must be an object")

    required = {
        "timestamp",
        "handoff_key",
        "attempt",
        "inputs",
        "decision_path",
        "command_envelope",
        "transition",
    }
    missing = sorted(field for field in required if field not in record)
    if missing:
        raise RunArtifactValidationError("missing fields: " + ",".join(missing))

    timestamp = _normalize_timestamp(record["timestamp"])
    handoff_key = _validate_handoff_key(record["handoff_key"])
    attempt = _validate_attempt(record["attempt"])
    inputs = _validate_inputs(record["inputs"])
    decision_path = _validate_decision_path(record["decision_path"])
    command_envelope = _validate_command_envelope(record["command_envelope"])
    transition = _validate_transition(record["transition"])

    return {
        "timestamp": timestamp,
        "handoff_key": handoff_key,
        "attempt": attempt,
        "inputs": inputs,
        "decision_path": decision_path,
        "command_envelope": command_envelope,
        "transition": transition,
    }


def emit_run_artifact(
    *,
    artifacts_root: str | Path,
    record: Dict[str, Any],
) -> Path:
    normalized = validate_run_artifact(record)

    root = Path(artifacts_root)
    target_dir = root / normalized["handoff_key"]
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / f"{normalized['attempt']}.jsonl"
    payload = json.dumps(normalized, sort_keys=True, separators=(",", ":")) + "\n"
    encoded = payload.encode("utf-8")

    fd = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, encoded)
        os.fsync(fd)
    finally:
        os.close(fd)

    return target_path


def _normalize_timestamp(raw_value: Any) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise RunArtifactValidationError("timestamp invalid")
    raw = raw_value.strip()
    try:
        if raw.endswith("Z"):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise RunArtifactValidationError("timestamp invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RunArtifactValidationError("timestamp invalid")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _validate_handoff_key(raw_value: Any) -> str:
    if not isinstance(raw_value, str) or not HANDOFF_KEY_RE.match(raw_value):
        raise RunArtifactValidationError("handoff_key invalid")
    return raw_value


def _validate_attempt(raw_value: Any) -> int:
    if isinstance(raw_value, bool) or not isinstance(raw_value, int) or raw_value < 1:
        raise RunArtifactValidationError("attempt invalid")
    return raw_value


def _validate_inputs(raw_value: Any) -> Dict[str, Any]:
    if not isinstance(raw_value, dict):
        raise RunArtifactValidationError("inputs invalid")

    required = {"labels", "notes_snapshot_hash", "policy_hash", "local_time_eval"}
    missing = sorted(field for field in required if field not in raw_value)
    if missing:
        raise RunArtifactValidationError("inputs missing: " + ",".join(missing))

    labels = raw_value["labels"]
    if not isinstance(labels, list) or any(not isinstance(item, str) or not item.strip() for item in labels):
        raise RunArtifactValidationError("inputs.labels invalid")

    notes_snapshot_hash = raw_value["notes_snapshot_hash"]
    if not isinstance(notes_snapshot_hash, str) or not notes_snapshot_hash.strip():
        raise RunArtifactValidationError("inputs.notes_snapshot_hash invalid")

    policy_hash = raw_value["policy_hash"]
    if not isinstance(policy_hash, str) or not policy_hash.strip():
        raise RunArtifactValidationError("inputs.policy_hash invalid")

    local_time_eval = raw_value["local_time_eval"]
    if not isinstance(local_time_eval, dict):
        raise RunArtifactValidationError("inputs.local_time_eval invalid")

    return {
        "labels": list(labels),
        "notes_snapshot_hash": notes_snapshot_hash,
        "policy_hash": policy_hash,
        "local_time_eval": dict(local_time_eval),
    }


def _validate_decision_path(raw_value: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_value, list) or not raw_value:
        raise RunArtifactValidationError("decision_path invalid")

    normalized: List[Dict[str, Any]] = []
    for entry in raw_value:
        if not isinstance(entry, dict):
            raise RunArtifactValidationError("decision_path invalid")
        if "step" not in entry or "outcome" not in entry:
            raise RunArtifactValidationError("decision_path invalid")
        step = entry["step"]
        outcome = entry["outcome"]
        if not isinstance(step, str) or not step.strip():
            raise RunArtifactValidationError("decision_path invalid")
        if not isinstance(outcome, str) or not outcome.strip():
            raise RunArtifactValidationError("decision_path invalid")

        normalized_entry = {"step": step, "outcome": outcome}
        if "detail" in entry and entry["detail"] is not None:
            detail = entry["detail"]
            if not isinstance(detail, str):
                raise RunArtifactValidationError("decision_path invalid")
            normalized_entry["detail"] = detail
        normalized.append(normalized_entry)
    return normalized


def _validate_command_envelope(raw_value: Any) -> Dict[str, Any]:
    if not isinstance(raw_value, dict):
        raise RunArtifactValidationError("command_envelope invalid")

    required = {"run_id", "exit_code", "status"}
    missing = sorted(field for field in required if field not in raw_value)
    if missing:
        raise RunArtifactValidationError("command_envelope missing: " + ",".join(missing))

    run_id = raw_value["run_id"]
    if not isinstance(run_id, str) or not run_id.strip():
        raise RunArtifactValidationError("command_envelope.run_id invalid")

    exit_code = raw_value["exit_code"]
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise RunArtifactValidationError("command_envelope.exit_code invalid")

    status = raw_value["status"]
    if status not in COMMAND_STATUS_VALUES:
        raise RunArtifactValidationError("command_envelope.status invalid")

    normalized = {
        "run_id": run_id,
        "exit_code": exit_code,
        "status": status,
    }
    if "error_class" in raw_value and raw_value["error_class"] is not None:
        error_class = raw_value["error_class"]
        if not isinstance(error_class, str) or not error_class.strip():
            raise RunArtifactValidationError("command_envelope.error_class invalid")
        normalized["error_class"] = error_class
    return normalized


def _validate_transition(raw_value: Any) -> Dict[str, Any]:
    if not isinstance(raw_value, dict):
        raise RunArtifactValidationError("transition invalid")

    required = {"from", "to", "result"}
    missing = sorted(field for field in required if field not in raw_value)
    if missing:
        raise RunArtifactValidationError("transition missing: " + ",".join(missing))

    state_from = raw_value["from"]
    state_to = raw_value["to"]
    result = raw_value["result"]

    if state_from not in STATE_VALUES:
        raise RunArtifactValidationError("transition.from invalid")
    if state_to not in STATE_VALUES:
        raise RunArtifactValidationError("transition.to invalid")
    if result not in RESULT_VALUES:
        raise RunArtifactValidationError("transition.result invalid")

    normalized = {
        "from": state_from,
        "to": state_to,
        "result": result,
    }
    if "error_class" in raw_value and raw_value["error_class"] is not None:
        error_class = raw_value["error_class"]
        if not isinstance(error_class, str) or not error_class.strip():
            raise RunArtifactValidationError("transition.error_class invalid")
        normalized["error_class"] = error_class
    return normalized
