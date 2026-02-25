# Worker Handoff Adapter Contract

Implements WP-7 worker integration boundaries.

## Handoff Emitter

- Emits full `handoff:` block with required schema keys:
  - `origin_id`
  - `bug_id`
  - `error_signature`
  - `expected_minutes`
  - `estimated_loc`
  - `touches_api_or_schema`
  - `touches_security_or_auth`
  - `quick_test_available`

## Origin Resume Checks

Resume is allowed only when:

1. Bug bead is closed
2. Origin->bug dependency is cleared
3. Origin is not already `in_progress`

Decision output includes:
- `can_resume`
- `reason`
- required `actions` (for example `set_origin_in_progress` or dependency cleanup)
