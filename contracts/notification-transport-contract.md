# Notification Transport Contract

Defines escalation transport abstraction with bead-native implementation.

## Interface

- `NotificationMessage` input with:
  - `handoff_key`
  - `bug_id`
  - `priority` (`0..4`)
  - `error_class`
  - `summary`
  - `queued`
  - `metadata`
- Transport returns `TransportReceipt`.

## Required Transport

- `BeadNativeTransport`
  - Emits labels: always `needs:human` plus `notify:immediate` or `notify:queued`
  - Emits structured escalation note payload suitable for bead notes.

## Optional Extension

- `FanoutTransport` supports dispatching to multiple transports (email/slack/pager adapters can plug in later).
