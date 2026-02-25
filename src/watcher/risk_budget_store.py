from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Dict
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class RiskBudgetState:
    timezone: str
    day_bucket: str
    hour_bucket: str
    noncritical_day_count: int
    noncritical_hour_count: int


@dataclass(frozen=True)
class RiskBudgetDecision:
    decision: str  # allow | defer | bypass-critical
    reason: str
    day_bucket: str
    hour_bucket: str
    noncritical_day_count: int
    noncritical_hour_count: int


class RiskBudgetStoreError(ValueError):
    pass


class RiskBudgetCounterStore:
    def __init__(self, store_path: str | Path):
        self.store_path = Path(store_path)
        self.lock_path = Path(f"{self.store_path}.lock")

    def load(self) -> RiskBudgetState | None:
        with self._locked():
            payload = self._read_payload()
            if payload is None:
                return None
            return _state_from_payload(payload)

    def evaluate_and_record(
        self,
        *,
        now_utc: datetime,
        timezone_name: str,
        is_critical: bool,
        max_noncritical_escalations_per_day: int,
        max_noncritical_pages_per_hour: int,
    ) -> RiskBudgetDecision:
        if max_noncritical_escalations_per_day < 0 or max_noncritical_pages_per_hour < 0:
            raise RiskBudgetStoreError("risk budget limits must be non-negative")
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise RiskBudgetStoreError("now_utc must be timezone-aware")

        try:
            tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise RiskBudgetStoreError(f"invalid timezone: {timezone_name}") from exc

        local_now = now_utc.astimezone(tz)
        day_bucket = local_now.strftime("%Y-%m-%d")
        hour_bucket = local_now.strftime("%Y-%m-%dT%H")

        with self._locked():
            current_payload = self._read_payload()
            current = _state_from_payload(current_payload) if current_payload else None
            state = _roll_forward_state(
                current=current,
                timezone_name=timezone_name,
                day_bucket=day_bucket,
                hour_bucket=hour_bucket,
            )

            if is_critical:
                self._write_payload(_payload_from_state(state))
                return RiskBudgetDecision(
                    decision="bypass-critical",
                    reason="critical_incident_bypass",
                    day_bucket=state.day_bucket,
                    hour_bucket=state.hour_bucket,
                    noncritical_day_count=state.noncritical_day_count,
                    noncritical_hour_count=state.noncritical_hour_count,
                )

            if state.noncritical_day_count >= max_noncritical_escalations_per_day:
                self._write_payload(_payload_from_state(state))
                return RiskBudgetDecision(
                    decision="defer",
                    reason="daily_noncritical_budget_exhausted",
                    day_bucket=state.day_bucket,
                    hour_bucket=state.hour_bucket,
                    noncritical_day_count=state.noncritical_day_count,
                    noncritical_hour_count=state.noncritical_hour_count,
                )

            if state.noncritical_hour_count >= max_noncritical_pages_per_hour:
                self._write_payload(_payload_from_state(state))
                return RiskBudgetDecision(
                    decision="defer",
                    reason="hourly_noncritical_budget_exhausted",
                    day_bucket=state.day_bucket,
                    hour_bucket=state.hour_bucket,
                    noncritical_day_count=state.noncritical_day_count,
                    noncritical_hour_count=state.noncritical_hour_count,
                )

            updated = RiskBudgetState(
                timezone=state.timezone,
                day_bucket=state.day_bucket,
                hour_bucket=state.hour_bucket,
                noncritical_day_count=state.noncritical_day_count + 1,
                noncritical_hour_count=state.noncritical_hour_count + 1,
            )
            self._write_payload(_payload_from_state(updated))
            return RiskBudgetDecision(
                decision="allow",
                reason="within_budget",
                day_bucket=updated.day_bucket,
                hour_bucket=updated.hour_bucket,
                noncritical_day_count=updated.noncritical_day_count,
                noncritical_hour_count=updated.noncritical_hour_count,
            )

    def _read_payload(self) -> Dict | None:
        if not self.store_path.exists():
            return None
        content = self.store_path.read_text(encoding="utf-8").strip()
        if not content:
            return None
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise RiskBudgetStoreError("store payload must be an object")
        return payload

    def _write_payload(self, payload: Dict) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(self.store_path.parent),
                prefix=f"{self.store_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp_file:
                temp_path = temp_file.name
                json.dump(payload, temp_file, sort_keys=True, indent=2)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, self.store_path)
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _locked(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_path.open("a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

        class _LockContext:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, exc_type, exc, tb):
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()

        return _LockContext()


def _roll_forward_state(
    *,
    current: RiskBudgetState | None,
    timezone_name: str,
    day_bucket: str,
    hour_bucket: str,
) -> RiskBudgetState:
    if current is None or current.timezone != timezone_name:
        return RiskBudgetState(
            timezone=timezone_name,
            day_bucket=day_bucket,
            hour_bucket=hour_bucket,
            noncritical_day_count=0,
            noncritical_hour_count=0,
        )

    day_count = current.noncritical_day_count
    hour_count = current.noncritical_hour_count

    if current.day_bucket != day_bucket:
        day_count = 0
        hour_count = 0
    elif current.hour_bucket != hour_bucket:
        hour_count = 0

    return RiskBudgetState(
        timezone=timezone_name,
        day_bucket=day_bucket,
        hour_bucket=hour_bucket,
        noncritical_day_count=day_count,
        noncritical_hour_count=hour_count,
    )


def _state_from_payload(payload: Dict) -> RiskBudgetState:
    return RiskBudgetState(
        timezone=payload["timezone"],
        day_bucket=payload["day_bucket"],
        hour_bucket=payload["hour_bucket"],
        noncritical_day_count=payload["noncritical_day_count"],
        noncritical_hour_count=payload["noncritical_hour_count"],
    )


def _payload_from_state(state: RiskBudgetState) -> Dict:
    return {
        "timezone": state.timezone,
        "day_bucket": state.day_bucket,
        "hour_bucket": state.hour_bucket,
        "noncritical_day_count": state.noncritical_day_count,
        "noncritical_hour_count": state.noncritical_hour_count,
    }
