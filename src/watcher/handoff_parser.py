from dataclasses import dataclass
import re
from typing import Dict, List


ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")
ERROR_SIGNATURE_RE = re.compile(r"^[a-z0-9:_-]{8,128}$")
FIELD_LINE_RE = re.compile(r"^\s{2,}([a-z0-9_]+):\s*(.*?)\s*$")

REQUIRED_FIELDS = [
    "origin_id",
    "bug_id",
    "error_signature",
    "expected_minutes",
    "estimated_loc",
    "touches_api_or_schema",
    "touches_security_or_auth",
    "quick_test_available",
]


@dataclass(frozen=True)
class HandoffPayload:
    origin_id: str
    bug_id: str
    error_signature: str
    expected_minutes: int
    estimated_loc: int
    touches_api_or_schema: bool
    touches_security_or_auth: bool
    quick_test_available: bool


class HandoffValidationError(ValueError):
    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("SCHEMA_INVALID: " + "; ".join(self.errors))


def parse_handoff_block(notes_text: str) -> HandoffPayload:
    mapping = _extract_handoff_mapping(notes_text)
    return _validate_mapping(mapping)


def _extract_handoff_mapping(notes_text: str) -> Dict[str, str]:
    lines = notes_text.splitlines()
    start_index = -1
    for idx, line in enumerate(lines):
        if line.strip() == "handoff:":
            start_index = idx
            break

    if start_index < 0:
        raise HandoffValidationError(["handoff block missing"])

    mapping: Dict[str, str] = {}
    errors: List[str] = []
    consumed = False

    for line in lines[start_index + 1 :]:
        if not line.strip():
            if consumed:
                continue
            continue

        if not line.startswith(" "):
            if consumed:
                break
            continue

        match = FIELD_LINE_RE.match(line)
        if match is None:
            errors.append(f"malformed handoff field line: {line.strip()}")
            continue

        key = match.group(1)
        raw_value = _strip_quotes(match.group(2).strip())
        if not raw_value:
            errors.append(f"{key} missing value")
            continue

        mapping[key] = raw_value
        consumed = True

    if errors:
        raise HandoffValidationError(errors)

    if not mapping:
        raise HandoffValidationError(["handoff block empty"])

    return mapping


def _validate_mapping(mapping: Dict[str, str]) -> HandoffPayload:
    errors: List[str] = []

    for field in REQUIRED_FIELDS:
        if field not in mapping:
            errors.append(f"{field} missing")

    origin_id = mapping.get("origin_id", "")
    if origin_id and not ID_RE.match(origin_id):
        errors.append("origin_id invalid")

    bug_id = mapping.get("bug_id", "")
    if bug_id and not ID_RE.match(bug_id):
        errors.append("bug_id invalid")

    error_signature = mapping.get("error_signature", "")
    if error_signature and not ERROR_SIGNATURE_RE.match(error_signature):
        errors.append("error_signature invalid")

    expected_minutes = _parse_int_range(
        mapping.get("expected_minutes"),
        "expected_minutes",
        1,
        480,
        errors,
    )
    estimated_loc = _parse_int_range(
        mapping.get("estimated_loc"),
        "estimated_loc",
        1,
        5000,
        errors,
    )
    touches_api_or_schema = _parse_bool(
        mapping.get("touches_api_or_schema"),
        "touches_api_or_schema",
        errors,
    )
    touches_security_or_auth = _parse_bool(
        mapping.get("touches_security_or_auth"),
        "touches_security_or_auth",
        errors,
    )
    quick_test_available = _parse_bool(
        mapping.get("quick_test_available"),
        "quick_test_available",
        errors,
    )

    if errors:
        raise HandoffValidationError(errors)

    return HandoffPayload(
        origin_id=origin_id,
        bug_id=bug_id,
        error_signature=error_signature,
        expected_minutes=expected_minutes,
        estimated_loc=estimated_loc,
        touches_api_or_schema=touches_api_or_schema,
        touches_security_or_auth=touches_security_or_auth,
        quick_test_available=quick_test_available,
    )


def _parse_int_range(
    raw_value: str,
    field_name: str,
    min_value: int,
    max_value: int,
    errors: List[str],
) -> int:
    if raw_value is None:
        return 0

    try:
        value = int(raw_value)
    except ValueError:
        errors.append(f"{field_name} invalid")
        return 0

    if value < min_value or value > max_value:
        errors.append(f"{field_name} invalid")
        return 0

    return value


def _parse_bool(raw_value: str, field_name: str, errors: List[str]) -> bool:
    if raw_value is None:
        return False

    lowered = raw_value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    errors.append(f"{field_name} invalid")
    return False


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].strip()
    return value

