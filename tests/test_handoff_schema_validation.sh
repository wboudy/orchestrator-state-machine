#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

VALID="tests/fixtures/handoff.valid.json"
INVALID="tests/fixtures/handoff.invalid.json"

valid_out="$(scripts/validate_handoff_schema.sh "$VALID")"
if [[ "$valid_out" != "SCHEMA_VALID" ]]; then
  echo "Expected valid payload to pass but got: $valid_out" >&2
  exit 1
fi

set +e
invalid_out="$(scripts/validate_handoff_schema.sh "$INVALID" 2>&1)"
invalid_rc=$?
set -e

if [[ $invalid_rc -eq 0 ]]; then
  echo "Expected invalid payload to fail validation" >&2
  exit 1
fi

echo "$invalid_out" | rg -q "origin_id invalid"
echo "$invalid_out" | rg -q "bug_id invalid"
echo "$invalid_out" | rg -q "error_signature invalid"
echo "$invalid_out" | rg -q "expected_minutes invalid"
echo "$invalid_out" | rg -q "estimated_loc invalid"
echo "$invalid_out" | rg -q "touches_api_or_schema invalid"

echo "PASS: handoff schema validation test"
