from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Dict


@dataclass(frozen=True)
class DedupeDecision:
    dedupe_key: str
    suppressed: bool
    reason: str
    remaining_seconds: int


class DedupeStoreError(ValueError):
    pass


class DedupeSuppressionStore:
    def __init__(self, store_path: str | Path):
        self.store_path = Path(store_path)
        self.lock_path = Path(f"{self.store_path}.lock")

    def evaluate_and_record(
        self,
        *,
        origin_id: str,
        error_signature: str,
        error_class: str,
        now_utc: datetime,
        window_minutes: int,
    ) -> DedupeDecision:
        if window_minutes <= 0:
            raise DedupeStoreError("window_minutes must be > 0")
        if now_utc.tzinfo is None or now_utc.utcoffset() is None:
            raise DedupeStoreError("now_utc must be timezone-aware")

        now = now_utc.astimezone(timezone.utc)
        dedupe_key = build_dedupe_key(origin_id=origin_id, error_signature=error_signature, error_class=error_class)
        window = timedelta(minutes=window_minutes)

        with self._locked():
            entries = self._read_entries()
            _prune_expired(entries, now=now, window=window)

            previous = entries.get(dedupe_key)
            if previous is not None:
                delta = now - previous
                if delta < window:
                    remaining = int((window - delta).total_seconds())
                    self._write_entries(entries)
                    return DedupeDecision(
                        dedupe_key=dedupe_key,
                        suppressed=True,
                        reason="suppressed_within_window",
                        remaining_seconds=max(0, remaining),
                    )

            entries[dedupe_key] = now
            self._write_entries(entries)
            return DedupeDecision(
                dedupe_key=dedupe_key,
                suppressed=False,
                reason="outside_window_or_first_seen",
                remaining_seconds=0,
            )

    def _read_entries(self) -> Dict[str, datetime]:
        if not self.store_path.exists():
            return {}
        content = self.store_path.read_text(encoding="utf-8").strip()
        if not content:
            return {}

        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise DedupeStoreError("dedupe store payload must be an object")

        raw_entries = payload.get("entries", {})
        if not isinstance(raw_entries, dict):
            raise DedupeStoreError("dedupe store entries must be an object")

        entries: Dict[str, datetime] = {}
        for key, raw_value in raw_entries.items():
            if not isinstance(key, str):
                raise DedupeStoreError("dedupe key must be string")
            entries[key] = _parse_timestamp(raw_value)
        return entries

    def _write_entries(self, entries: Dict[str, datetime]) -> None:
        payload = {
            "entries": {
                key: value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
                for key, value in sorted(entries.items())
            }
        }
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


def build_dedupe_key(*, origin_id: str, error_signature: str, error_class: str) -> str:
    if not origin_id or not error_signature or not error_class:
        raise DedupeStoreError("origin_id, error_signature, and error_class are required")
    raw = f"{origin_id}:{error_signature}:{error_class}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _parse_timestamp(raw_value: object) -> datetime:
    if not isinstance(raw_value, str) or not raw_value.strip():
        raise DedupeStoreError("invalid timestamp in dedupe store")
    raw = raw_value.strip()
    try:
        if raw.endswith("Z"):
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        else:
            parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise DedupeStoreError("invalid timestamp in dedupe store") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise DedupeStoreError("invalid timestamp in dedupe store")
    return parsed.astimezone(timezone.utc)


def _prune_expired(entries: Dict[str, datetime], *, now: datetime, window: timedelta) -> None:
    expired = [key for key, ts in entries.items() if (now - ts) >= window]
    for key in expired:
        del entries[key]
