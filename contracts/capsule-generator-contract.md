# Reproducibility Capsule Generator Contract

This contract defines sanitized capsule artifact generation.

## Output Path

- `.beads/orchestrator-capsules/<handoff_key>/<attempt>.md`

## Required Inputs

- `handoff_key`, `attempt`, `timestamp`
- `reproduction_steps`
- `observed`, `expected`
- `command_envelope`
- `logs`
- `metadata`

## Behavior

1. Validate payload completeness/types.
2. Apply redaction engine to all capsule sections.
3. Render markdown capsule with redacted command envelope/logs/metadata.
4. Write with exclusive create (`O_EXCL`) to keep attempt artifacts immutable.

## Fail-Closed

- If redaction fails, raise `CapsuleGenerationError` with `redaction_failed` prefix.
- No capsule file may be written on redaction failure.
