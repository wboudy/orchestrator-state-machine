# Retry Error Classifier Contract

This contract defines normalization and retry taxonomy for command failures.

## Canonical Classes

### Retriable

- `timeout`
- `rate_limited`
- `upstream_unavailable`
- `network_error`
- `state_conflict`
- `stale_run`
- `unknown_error`

### Non-Retriable

- `schema_invalid`
- `auth_failed`
- `permission_denied`
- `bad_input`
- `policy_invalid`

## Behavior

1. Normalize input to lowercase snake_case.
2. Apply alias mapping (for example `rate-limit -> rate_limited`).
3. Return canonical class and retryability flag.
4. Unknown values map to `unknown_error` (retriable).
5. Non-string non-null values are invalid and raise classifier error.
