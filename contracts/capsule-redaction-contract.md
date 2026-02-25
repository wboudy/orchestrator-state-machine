# Capsule Redaction Engine Contract

Implements Section 18 redaction rules before capsule write.

## Rules

1. Redact values for keys matching case-insensitive patterns:
   - `token`, `secret`, `password`, `api_key`, `authorization`, `cookie`
2. Redact bearer/basic auth values in strings:
   - `Bearer <REDACTED>`
   - `Basic <REDACTED>`
3. Replace home-directory prefixes with `<HOME>` when paths are outside project root.

## Fail-Closed

- Unsupported payload types or invalid map keys raise `RedactionError`.
- Caller must treat `RedactionError` as `error_class=redaction_failed` and avoid writing raw capsule output.
