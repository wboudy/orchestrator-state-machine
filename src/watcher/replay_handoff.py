from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Dict, List

from watcher.run_artifact_emitter import RunArtifactValidationError, validate_run_artifact


@dataclass(frozen=True)
class ReplayOutcome:
    dry_run: bool
    run_file: str
    handoff_key: str
    attempt: int
    replay_result: str
    expected_result: str
    parity_match: bool
    checks: List[str]


class ReplayHandoffError(ValueError):
    pass


def replay_handoff_run(*, run_file: str | Path, dry_run: bool) -> ReplayOutcome:
    if not dry_run:
        raise ReplayHandoffError("only --dry-run is supported")

    record = load_run_artifact(run_file)
    expected_result, checks = _evaluate_expected_result(record)
    replay_result = record["transition"]["result"]

    return ReplayOutcome(
        dry_run=True,
        run_file=str(run_file),
        handoff_key=record["handoff_key"],
        attempt=record["attempt"],
        replay_result=replay_result,
        expected_result=expected_result,
        parity_match=(expected_result == replay_result),
        checks=checks,
    )


def replay_outcome_json(outcome: ReplayOutcome) -> str:
    return json.dumps(asdict(outcome), sort_keys=True, separators=(",", ":"))


def load_run_artifact(run_file: str | Path) -> Dict[str, Any]:
    path = Path(run_file)
    if not path.exists():
        raise ReplayHandoffError(f"run file not found: {run_file}")

    raw_lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(raw_lines) != 1:
        raise ReplayHandoffError("run artifact file must contain exactly one JSONL record")

    try:
        parsed = json.loads(raw_lines[0])
    except json.JSONDecodeError as exc:
        raise ReplayHandoffError("run artifact is not valid JSON") from exc

    try:
        return validate_run_artifact(parsed)
    except RunArtifactValidationError as exc:
        raise ReplayHandoffError(str(exc)) from exc


def _evaluate_expected_result(record: Dict[str, Any]) -> tuple[str, List[str]]:
    checks: List[str] = []

    command_status = record["command_envelope"]["status"]
    checks.append(f"command_status={command_status}")

    transition_to = record["transition"]["to"]
    checks.append(f"transition_to={transition_to}")

    if command_status == "success":
        checks.append("success status maps to success result")
        return "success", checks

    if transition_to == "HUMAN_REQUIRED":
        checks.append("failure/partial with HUMAN_REQUIRED maps to human_required result")
        return "human_required", checks

    checks.append("failure/partial with non-terminal transition maps to retry result")
    return "retry", checks
