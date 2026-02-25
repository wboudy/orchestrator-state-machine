# Dedupe Suppression Store Contract

Tracks notification dedupe windows using key:

- `origin_id + error_signature + error_class`

## Behavior

1. Compute deterministic dedupe key (`sha1` of the triplet).
2. If prior event for key is within `window_minutes`, decision is `suppressed`.
3. Otherwise decision is `allow` and timestamp is recorded.
4. Expired keys are pruned on access.

## Persistence

- File-backed JSON map with lock + atomic replace write.
- Timestamps stored in RFC3339 UTC.

## Errors

- Invalid window/time inputs raise `DedupeStoreError`.
- Malformed persisted timestamps raise `DedupeStoreError`.
