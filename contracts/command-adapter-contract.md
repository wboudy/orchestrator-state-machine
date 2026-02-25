# Orchestrator Command Adapter Contract

Normalizes orchestrator command envelope and reconciles `partial` semantics.

## Envelope Input

Required:
- `run_id`
- `exit_code`
- `status` (`success|failure|partial`)

Optional:
- `error_class`

Normalization and validation:

- `run_id` must be a non-empty string after trimming.
- `status` is trimmed/lowercased and must resolve to `success|failure|partial`.
- `exit_code` accepts integer-like values (`int`, integral `float`, numeric string) and is coerced to `int`.
- Fractional, non-finite, boolean, or empty `exit_code` values are invalid.
- `error_class` is optional; blank strings normalize to `null`.

## Reconciliation Rules

1. `status=success` with `exit_code=0` -> `watcher_result=success`
2. `status=partial` -> treated as failure path by default
3. `status=partial` -> may become `success_with_exit_mismatch` only when terminal success is externally observed
4. `status=failure` -> failure path unless terminal success is externally observed
5. Failure path maps through retry classifier:
   - retriable => `watcher_result=retry`
   - non-retriable => `watcher_result=human_required`

This enforces: partial is never considered success without reconciliation evidence.
