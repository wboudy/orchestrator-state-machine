# Retry Scheduler Contract

This contract implements Section 17.1 retry-delay semantics.

## Inputs

- `attempt` (1-indexed)
- `backoff_seconds` (non-empty positive-int array)
- `jitter_pct` (integer 0..100)
- `now_utc` (timezone-aware UTC timestamp)

## Algorithm

1. `base = backoff_seconds[min(attempt-1, len(backoff_seconds)-1)]`
2. `jitter_factor = 1 + (jitter_unit * jitter_pct/100)` where `jitter_unit in [-1, 1]`
3. `delay = round(base * jitter_factor)` with floor clamp to `>= 1` second
4. `next_retry_at = now_utc + delay`

## Output

- `RetryScheduleResult` with:
  - `base_delay_seconds`
  - `jitter_factor`
  - `delay_seconds`
  - `next_retry_at`

## Failure Behavior

- Invalid attempt/backoff/jitter/clock input raises `RetryScheduleError`.
