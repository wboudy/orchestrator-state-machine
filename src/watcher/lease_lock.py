from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path


@dataclass(frozen=True)
class LeaseRecord:
    owner_id: str
    acquired_at: str
    heartbeat_at: str
    expires_at: str


class LeaseLockError(ValueError):
    pass


class LeaseBusyError(LeaseLockError):
    pass


class LeaseOwnershipError(LeaseLockError):
    pass


class LeaseExpiredError(LeaseLockError):
    pass


class LeaseLockManager:
    def __init__(self, lock_path: str | Path, lease_seconds: int = 30):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be > 0")
        self.lock_path = Path(lock_path)
        self.lease_seconds = lease_seconds

    def acquire(self, owner_id: str, now_utc: datetime) -> LeaseRecord:
        existing = self.load()
        if existing:
            if existing.owner_id == owner_id:
                return self.heartbeat(owner_id, now_utc)
            if not self.is_stale(existing, now_utc):
                raise LeaseBusyError("lease already held by another owner")

        record = self._new_record(owner_id, now_utc)
        self._write(record)
        return record

    def heartbeat(self, owner_id: str, now_utc: datetime) -> LeaseRecord:
        existing = self.load()
        if existing is None:
            raise LeaseLockError("lease not found")
        if existing.owner_id != owner_id:
            raise LeaseOwnershipError("cannot heartbeat lease owned by another owner")
        if self.is_stale(existing, now_utc):
            raise LeaseExpiredError("cannot heartbeat expired lease")

        refreshed = LeaseRecord(
            owner_id=owner_id,
            acquired_at=existing.acquired_at,
            heartbeat_at=_to_rfc3339(now_utc),
            expires_at=_to_rfc3339(now_utc + timedelta(seconds=self.lease_seconds)),
        )
        self._write(refreshed)
        return refreshed

    def release(self, owner_id: str) -> bool:
        existing = self.load()
        if existing is None:
            return False
        if existing.owner_id != owner_id:
            raise LeaseOwnershipError("cannot release lease owned by another owner")
        self.lock_path.unlink(missing_ok=False)
        return True

    def load(self) -> LeaseRecord | None:
        if not self.lock_path.exists():
            return None

        payload = json.loads(self.lock_path.read_text())
        return LeaseRecord(
            owner_id=payload["owner_id"],
            acquired_at=payload["acquired_at"],
            heartbeat_at=payload["heartbeat_at"],
            expires_at=payload["expires_at"],
        )

    def is_stale(self, record: LeaseRecord, now_utc: datetime) -> bool:
        return _from_rfc3339(record.expires_at) <= now_utc

    def _new_record(self, owner_id: str, now_utc: datetime) -> LeaseRecord:
        stamp = _to_rfc3339(now_utc)
        return LeaseRecord(
            owner_id=owner_id,
            acquired_at=stamp,
            heartbeat_at=stamp,
            expires_at=_to_rfc3339(now_utc + timedelta(seconds=self.lease_seconds)),
        )

    def _write(self, record: LeaseRecord) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.write_text(
            json.dumps(
                {
                    "owner_id": record.owner_id,
                    "acquired_at": record.acquired_at,
                    "heartbeat_at": record.heartbeat_at,
                    "expires_at": record.expires_at,
                },
                sort_keys=True,
            )
            + "\n"
        )


def _to_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _from_rfc3339(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)

