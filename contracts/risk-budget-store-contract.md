# Risk Budget Counter Store Contract

Tracks noncritical escalation counters with policy-timezone buckets.

## Counters

- `noncritical_day_count` bucketed by local date
- `noncritical_hour_count` bucketed by local hour

## Decision Output

- `allow` when within both limits
- `defer` when day/hour noncritical limit is exhausted
- `bypass-critical` for critical incidents

## Timezone Semantics

- Buckets are computed in policy IANA timezone.
- Day counter resets at local midnight.
- Hour counter resets when local hour changes.
- Timezone change resets counters to avoid mixed-bucket ambiguity.

## Persistence

- File-backed JSON store with lock + atomic replace write.
- Deterministic state payload fields:
  - `timezone`
  - `day_bucket`
  - `hour_bucket`
  - `noncritical_day_count`
  - `noncritical_hour_count`
