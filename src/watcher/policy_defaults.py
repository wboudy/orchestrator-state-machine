from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Dict, List, Tuple

from watcher.policy_contract import PolicyValidationError, validate_policy_mapping


CANONICAL_POLICY_DEFAULTS: Dict[str, Any] = {
    "timezone": "America/New_York",
    "business_hours": {
        "weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "start": "09:00",
        "end": "18:00",
    },
    "retry": {
        "max_retries": 3,
        "backoff_seconds": [60, 300, 900],
        "jitter_pct": 15,
    },
    "risk_budget": {
        "max_noncritical_escalations_per_day": 20,
        "max_noncritical_pages_per_hour": 5,
    },
    "dedupe": {"window_minutes": 60},
    "trust": {"initial_score": 0.5, "min_samples": 5},
}


@dataclass(frozen=True)
class EffectivePolicySnapshot:
    effective_policy: Dict[str, Any]
    defaults_applied: Tuple[str, ...]
    policy_hash: str


class PolicyDefaultsError(ValueError):
    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("POLICY_DEFAULTS_INVALID: " + "; ".join(self.errors))


def inject_canonical_defaults(raw_policy: Dict[str, Any] | None) -> EffectivePolicySnapshot:
    if raw_policy is None:
        raw_policy = {}
    if not isinstance(raw_policy, dict):
        raise PolicyDefaultsError(["policy root must be an object"])

    merge_errors: List[str] = []
    defaults_applied: List[str] = []
    merged = _merge_node(
        defaults=CANONICAL_POLICY_DEFAULTS,
        override=raw_policy,
        path="",
        merge_errors=merge_errors,
        defaults_applied=defaults_applied,
    )
    if merge_errors:
        raise PolicyDefaultsError(merge_errors)

    try:
        validate_policy_mapping(merged)
    except PolicyValidationError as exc:
        raise PolicyDefaultsError(exc.errors) from exc

    policy_hash = _stable_policy_hash(merged)
    return EffectivePolicySnapshot(
        effective_policy=merged,
        defaults_applied=tuple(defaults_applied),
        policy_hash=policy_hash,
    )


def render_snapshot_json(snapshot: EffectivePolicySnapshot) -> str:
    payload = {
        "policy_hash": snapshot.policy_hash,
        "defaults_applied": list(snapshot.defaults_applied),
        "effective_policy": snapshot.effective_policy,
    }
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _merge_node(
    *,
    defaults: Any,
    override: Any,
    path: str,
    merge_errors: List[str],
    defaults_applied: List[str],
) -> Any:
    if isinstance(defaults, dict):
        if override is None:
            override = {}
        if not isinstance(override, dict):
            path_name = path if path else "policy"
            merge_errors.append(f"{path_name} invalid")
            return _deep_clone(defaults)

        merged: Dict[str, Any] = {}
        for key in defaults.keys():
            child_path = _join_path(path, key)
            if key in override:
                merged[key] = _merge_node(
                    defaults=defaults[key],
                    override=override[key],
                    path=child_path,
                    merge_errors=merge_errors,
                    defaults_applied=defaults_applied,
                )
            else:
                merged[key] = _deep_clone(defaults[key])
                defaults_applied.extend(_leaf_paths(defaults[key], child_path))

        for key in override.keys():
            if key not in defaults:
                unknown_path = _join_path(path, key)
                merge_errors.append(f"{unknown_path} unknown")
        return merged

    if override is None:
        defaults_applied.append(path)
        return _deep_clone(defaults)

    return _deep_clone(override)


def _leaf_paths(value: Any, path: str) -> List[str]:
    if isinstance(value, dict):
        paths: List[str] = []
        for key in value.keys():
            paths.extend(_leaf_paths(value[key], _join_path(path, key)))
        return paths
    return [path]


def _deep_clone(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _deep_clone(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_clone(item) for item in value]
    return value


def _join_path(base: str, key: str) -> str:
    if not base:
        return key
    return f"{base}.{key}"


def _stable_policy_hash(policy: Dict[str, Any]) -> str:
    serialized = json.dumps(policy, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
