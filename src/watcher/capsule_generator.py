from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List

from watcher.capsule_redaction import RedactionError, redact_capsule_payload


HANDOFF_KEY_RE = re.compile(r"^[a-f0-9]{8,64}$")


class CapsuleGenerationError(ValueError):
    pass


def generate_reproducibility_capsule(
    *,
    artifacts_root: str | Path,
    capsule_payload: Dict[str, Any],
    project_root: str | Path,
    home_dir: str | Path | None = None,
) -> Path:
    normalized = _validate_capsule_payload(capsule_payload)

    try:
        redacted = redact_capsule_payload(
            normalized,
            project_root=project_root,
            home_dir=home_dir,
        )
    except RedactionError as exc:
        raise CapsuleGenerationError(f"redaction_failed: {exc}") from exc

    markdown = _render_capsule_markdown(redacted)
    root = Path(artifacts_root)
    target_dir = root / redacted["handoff_key"]
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{redacted['attempt']}.md"

    fd = os.open(target_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        os.write(fd, markdown.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)

    return target_path


def _validate_capsule_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise CapsuleGenerationError("capsule payload must be an object")

    required = {
        "handoff_key",
        "attempt",
        "timestamp",
        "reproduction_steps",
        "observed",
        "expected",
        "command_envelope",
        "logs",
        "metadata",
    }
    missing = sorted(field for field in required if field not in payload)
    if missing:
        raise CapsuleGenerationError("missing fields: " + ",".join(missing))

    handoff_key = payload["handoff_key"]
    if not isinstance(handoff_key, str) or not HANDOFF_KEY_RE.match(handoff_key):
        raise CapsuleGenerationError("handoff_key invalid")

    attempt = payload["attempt"]
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
        raise CapsuleGenerationError("attempt invalid")

    timestamp = payload["timestamp"]
    normalized_timestamp = _normalize_timestamp(timestamp)

    steps = payload["reproduction_steps"]
    if not isinstance(steps, list) or not steps or any(not isinstance(step, str) or not step.strip() for step in steps):
        raise CapsuleGenerationError("reproduction_steps invalid")

    observed = payload["observed"]
    expected = payload["expected"]
    if not isinstance(observed, str) or not observed.strip():
        raise CapsuleGenerationError("observed invalid")
    if not isinstance(expected, str) or not expected.strip():
        raise CapsuleGenerationError("expected invalid")

    command_envelope = payload["command_envelope"]
    logs = payload["logs"]
    metadata = payload["metadata"]
    if not isinstance(command_envelope, dict):
        raise CapsuleGenerationError("command_envelope invalid")
    if not isinstance(logs, (list, str)):
        raise CapsuleGenerationError("logs invalid")
    if isinstance(logs, list) and any(not isinstance(item, str) for item in logs):
        raise CapsuleGenerationError("logs invalid")
    if not isinstance(metadata, dict):
        raise CapsuleGenerationError("metadata invalid")

    return {
        "handoff_key": handoff_key,
        "attempt": attempt,
        "timestamp": normalized_timestamp,
        "reproduction_steps": list(steps),
        "observed": observed,
        "expected": expected,
        "command_envelope": dict(command_envelope),
        "logs": logs if isinstance(logs, str) else list(logs),
        "metadata": dict(metadata),
    }


def _render_capsule_markdown(payload: Dict[str, Any]) -> str:
    logs = payload["logs"]
    if isinstance(logs, list):
        log_text = "\n".join(logs)
    else:
        log_text = logs

    steps_block = "\n".join(f"{index}. {step}" for index, step in enumerate(payload["reproduction_steps"], start=1))
    command_json = json.dumps(payload["command_envelope"], indent=2, sort_keys=True)
    metadata_json = json.dumps(payload["metadata"], indent=2, sort_keys=True)

    return (
        f"# Reproducibility Capsule\n\n"
        f"- `handoff_key`: `{payload['handoff_key']}`\n"
        f"- `attempt`: `{payload['attempt']}`\n"
        f"- `timestamp`: `{payload['timestamp']}`\n\n"
        f"## Reproduction Steps\n\n"
        f"{steps_block}\n\n"
        f"## Observed\n\n"
        f"{payload['observed']}\n\n"
        f"## Expected\n\n"
        f"{payload['expected']}\n\n"
        f"## Command Envelope (Redacted)\n\n"
        f"```json\n{command_json}\n```\n\n"
        f"## Logs (Redacted)\n\n"
        f"```\n{log_text}\n```\n\n"
        f"## Metadata (Redacted)\n\n"
        f"```json\n{metadata_json}\n```\n"
    )


def _normalize_timestamp(raw_value: Any) -> str:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise CapsuleGenerationError("timestamp invalid")
    raw = raw_value.strip()
    try:
        if raw.endswith("Z"):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CapsuleGenerationError("timestamp invalid") from exc

    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CapsuleGenerationError("timestamp invalid")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
