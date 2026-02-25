from __future__ import annotations

from pathlib import Path
import re
from typing import Any


REDACTED = "<REDACTED>"
SENSITIVE_KEY_RE = re.compile(r"(token|secret|password|api[_-]?key|authorization|cookie)", re.IGNORECASE)
BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
BASIC_RE = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{6,}")


class RedactionError(ValueError):
    pass


def redact_capsule_payload(
    payload: Any,
    *,
    project_root: str | Path,
    home_dir: str | Path | None = None,
) -> Any:
    project_root_path = Path(project_root).expanduser().resolve()
    if home_dir is None:
        home_dir_path = Path.home().resolve()
    else:
        home_dir_path = Path(home_dir).expanduser().resolve()

    return _redact_value(payload, project_root_path, home_dir_path)


def _redact_value(value: Any, project_root: Path, home_dir: Path) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _redact_string(value, project_root, home_dir)

    if isinstance(value, list):
        return [_redact_value(item, project_root, home_dir) for item in value]

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise RedactionError("dictionary keys must be strings for redaction")
            if SENSITIVE_KEY_RE.search(key):
                redacted[key] = REDACTED
                continue
            redacted[key] = _redact_value(item, project_root, home_dir)
        return redacted

    raise RedactionError(f"unsupported payload type for redaction: {type(value).__name__}")


def _redact_string(text: str, project_root: Path, home_dir: Path) -> str:
    redacted = BEARER_RE.sub("Bearer <REDACTED>", text)
    redacted = BASIC_RE.sub("Basic <REDACTED>", redacted)
    redacted = _redact_home_paths(redacted, project_root, home_dir)
    return redacted


def _redact_home_paths(text: str, project_root: Path, home_dir: Path) -> str:
    home_prefix = str(home_dir)
    if home_prefix not in text:
        return text

    pattern = re.compile(re.escape(home_prefix) + r"[^\s\"'`]*")

    def replace(match: re.Match[str]) -> str:
        matched_path = match.group(0)
        if matched_path.startswith(str(project_root)):
            return matched_path
        return "<HOME>" + matched_path[len(home_prefix) :]

    return pattern.sub(replace, text)
