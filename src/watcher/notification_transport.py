from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any, List, Protocol, Sequence


@dataclass(frozen=True)
class NotificationMessage:
    handoff_key: str
    bug_id: str
    priority: int
    error_class: str
    summary: str
    queued: bool
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TransportReceipt:
    transport: str
    delivered: bool
    destination: str
    labels: tuple[str, ...]
    note: str


class NotificationTransportError(ValueError):
    pass


class NotificationTransport(Protocol):
    name: str

    def send(self, message: NotificationMessage) -> TransportReceipt:
        ...


class BeadNativeTransport:
    name = "bead-native"

    def send(self, message: NotificationMessage) -> TransportReceipt:
        _validate_message(message)
        labels = ["needs:human", "notify:queued" if message.queued else "notify:immediate"]
        note = _render_bead_note(message)
        return TransportReceipt(
            transport=self.name,
            delivered=True,
            destination="bead:labels+notes",
            labels=tuple(labels),
            note=note,
        )


class FanoutTransport:
    name = "fanout"

    def __init__(self, transports: Sequence[NotificationTransport]):
        self.transports = list(transports)
        if not self.transports:
            raise NotificationTransportError("fanout transport requires at least one transport")

    def send_all(self, message: NotificationMessage) -> List[TransportReceipt]:
        receipts: List[TransportReceipt] = []
        for transport in self.transports:
            receipts.append(transport.send(message))
        return receipts


def _validate_message(message: NotificationMessage) -> None:
    if not message.handoff_key:
        raise NotificationTransportError("handoff_key is required")
    if not message.bug_id:
        raise NotificationTransportError("bug_id is required")
    if message.priority < 0 or message.priority > 4:
        raise NotificationTransportError("priority must be in range 0..4")
    if not message.error_class:
        raise NotificationTransportError("error_class is required")
    if not message.summary:
        raise NotificationTransportError("summary is required")
    if not isinstance(message.metadata, dict):
        raise NotificationTransportError("metadata must be an object")


def _render_bead_note(message: NotificationMessage) -> str:
    metadata_json = json.dumps(message.metadata, sort_keys=True)
    return (
        "escalation:\n"
        f"  handoff_key: {message.handoff_key}\n"
        f"  bug_id: {message.bug_id}\n"
        f"  priority: P{message.priority}\n"
        f"  error_class: {message.error_class}\n"
        f"  queued: {'true' if message.queued else 'false'}\n"
        f"  summary: \"{message.summary}\"\n"
        f"  metadata: {metadata_json}\n"
    )
