from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Dict


@dataclass(frozen=True)
class StateRecord:
    state: str
    attempt: int
    last_transition_at: str
    next_retry_at: str | None
    last_error_class: str | None
    owner_id: str | None
    version: int = 0


@dataclass(frozen=True)
class SaveResult:
    saved: bool
    conflict: bool
    version: int
    record: StateRecord | None
    current: StateRecord | None


class HandoffStateStore:
    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)
        self.lock_path = Path(f"{self.state_path}.lock")

    def load(self, handoff_key: str) -> StateRecord | None:
        with self._locked():
            data = self._read_all()
            payload = data.get(handoff_key)
            if payload is None:
                return None
            return _record_from_payload(payload)

    def save(self, handoff_key: str, record: StateRecord, expected_version: int | None) -> SaveResult:
        with self._locked():
            data = self._read_all()
            existing_payload = data.get(handoff_key)
            existing_record = _record_from_payload(existing_payload) if existing_payload else None
            existing_version = existing_record.version if existing_record else 0

            if expected_version is not None and expected_version != existing_version:
                return SaveResult(
                    saved=False,
                    conflict=True,
                    version=existing_version,
                    record=None,
                    current=existing_record,
                )

            next_version = existing_version + 1
            next_record = StateRecord(
                state=record.state,
                attempt=record.attempt,
                last_transition_at=record.last_transition_at,
                next_retry_at=record.next_retry_at,
                last_error_class=record.last_error_class,
                owner_id=record.owner_id,
                version=next_version,
            )
            data[handoff_key] = _payload_from_record(next_record)
            self._write_all(data)

            return SaveResult(
                saved=True,
                conflict=False,
                version=next_version,
                record=next_record,
                current=existing_record,
            )

    def update_atomic(
        self,
        handoff_key: str,
        expected_version: int | None,
        update_fn: Callable[[StateRecord | None], StateRecord],
    ) -> SaveResult:
        with self._locked():
            data = self._read_all()
            existing_payload = data.get(handoff_key)
            existing_record = _record_from_payload(existing_payload) if existing_payload else None
            existing_version = existing_record.version if existing_record else 0

            if expected_version is not None and expected_version != existing_version:
                return SaveResult(
                    saved=False,
                    conflict=True,
                    version=existing_version,
                    record=None,
                    current=existing_record,
                )

            candidate = update_fn(existing_record)
            next_version = existing_version + 1
            next_record = StateRecord(
                state=candidate.state,
                attempt=candidate.attempt,
                last_transition_at=candidate.last_transition_at,
                next_retry_at=candidate.next_retry_at,
                last_error_class=candidate.last_error_class,
                owner_id=candidate.owner_id,
                version=next_version,
            )

            data[handoff_key] = _payload_from_record(next_record)
            self._write_all(data)
            return SaveResult(
                saved=True,
                conflict=False,
                version=next_version,
                record=next_record,
                current=existing_record,
            )

    def _read_all(self) -> Dict[str, Dict]:
        if not self.state_path.exists():
            return {}
        content = self.state_path.read_text().strip()
        if not content:
            return {}
        payload = json.loads(content)
        if not isinstance(payload, dict):
            raise ValueError("state store root must be an object keyed by handoff_key")
        return payload

    def _write_all(self, data: Dict[str, Dict]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=f"{self.state_path.name}.",
                suffix=".tmp",
                dir=str(self.state_path.parent),
                delete=False,
            ) as temp_file:
                temp_path = temp_file.name
                json.dump(data, temp_file, indent=2, sort_keys=True)
                temp_file.write("\n")
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, self.state_path)
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


def _record_from_payload(payload: Dict) -> StateRecord:
    return StateRecord(
        state=payload["state"],
        attempt=payload["attempt"],
        last_transition_at=payload["last_transition_at"],
        next_retry_at=payload.get("next_retry_at"),
        last_error_class=payload.get("last_error_class"),
        owner_id=payload.get("owner_id"),
        version=payload.get("version", 0),
    )


def _payload_from_record(record: StateRecord) -> Dict:
    return {
        "state": record.state,
        "attempt": record.attempt,
        "last_transition_at": record.last_transition_at,
        "next_retry_at": record.next_retry_at,
        "last_error_class": record.last_error_class,
        "owner_id": record.owner_id,
        "version": record.version,
    }
