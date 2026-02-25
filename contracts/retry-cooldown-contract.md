# Retry Cooldown Gate Contract

This contract defines persistence and gating for `next_retry_at`.

## Persistence

- On retriable failure, system writes a `StateRecord` with:
  - `state=RETRY_WAIT`
  - incremented `attempt`
  - `next_retry_at` in RFC3339 UTC (`...Z`)
  - `last_error_class` set to normalized class

## Gate

- If `next_retry_at` is missing: ready immediately.
- If `now_utc < next_retry_at`: cooldown active; return remaining wait seconds.
- If `now_utc >= next_retry_at`: cooldown elapsed; allow retry transition.
- Invalid timestamp values fail closed with `CooldownGateError`.

## Resume

- Cooldown expiry transition requires current state `RETRY_WAIT`.
- Resume transition emits `RUNNING` record and clears `next_retry_at`.
