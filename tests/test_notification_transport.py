#!/usr/bin/env python3
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from watcher.notification_transport import (
    BeadNativeTransport,
    FanoutTransport,
    NotificationMessage,
    NotificationTransportError,
    TransportReceipt,
)


class _FakeTransport:
    name = "fake"

    def send(self, message: NotificationMessage) -> TransportReceipt:
        return TransportReceipt(
            transport=self.name,
            delivered=True,
            destination="fake://endpoint",
            labels=("fake",),
            note=f"fake note for {message.bug_id}",
        )


class NotificationTransportTests(unittest.TestCase):
    def test_bead_native_immediate(self) -> None:
        transport = BeadNativeTransport()
        receipt = transport.send(
            NotificationMessage(
                handoff_key="a1b2c3d4e5f6a7b8",
                bug_id="osm-11i.10",
                priority=1,
                error_class="schema_invalid",
                summary="Schema validation failed",
                queued=False,
                metadata={"attempt": 1},
            )
        )
        self.assertTrue(receipt.delivered)
        self.assertIn("needs:human", receipt.labels)
        self.assertIn("notify:immediate", receipt.labels)
        self.assertIn("Schema validation failed", receipt.note)

    def test_bead_native_queued(self) -> None:
        transport = BeadNativeTransport()
        receipt = transport.send(
            NotificationMessage(
                handoff_key="a1b2c3d4e5f6a7b8",
                bug_id="osm-11i.10",
                priority=2,
                error_class="timeout",
                summary="Off-hours deferred escalation",
                queued=True,
                metadata={},
            )
        )
        self.assertIn("notify:queued", receipt.labels)
        self.assertNotIn("notify:immediate", receipt.labels)

    def test_invalid_message_raises(self) -> None:
        transport = BeadNativeTransport()
        with self.assertRaises(NotificationTransportError):
            transport.send(
                NotificationMessage(
                    handoff_key="",
                    bug_id="osm-x",
                    priority=2,
                    error_class="timeout",
                    summary="missing handoff",
                    queued=False,
                    metadata={},
                )
            )

    def test_fanout_transport_returns_all_receipts(self) -> None:
        fanout = FanoutTransport([BeadNativeTransport(), _FakeTransport()])
        receipts = fanout.send_all(
            NotificationMessage(
                handoff_key="a1b2c3d4e5f6a7b8",
                bug_id="osm-1",
                priority=2,
                error_class="timeout",
                summary="fanout case",
                queued=False,
                metadata={},
            )
        )
        self.assertEqual(len(receipts), 2)
        self.assertEqual(receipts[0].transport, "bead-native")
        self.assertEqual(receipts[1].transport, "fake")


if __name__ == "__main__":
    unittest.main()
