#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: scripts/validate_handoff_schema.sh <handoff-json-file>" >&2
  exit 2
fi

input_file="$1"
if [[ ! -f "$input_file" ]]; then
  echo "Input file not found: $input_file" >&2
  exit 2
fi

errors="$(
  jq -r '
    def is_str_re($re): (type == "string") and test($re);
    def is_int_range($min; $max): (type == "number") and (floor == .) and (. >= $min) and (. <= $max);
    def is_bool: type == "boolean";

    [
      (if (.origin_id | is_str_re("^[a-z0-9][a-z0-9.-]{1,63}$") | not) then "origin_id invalid" else empty end),
      (if (.bug_id | is_str_re("^[a-z0-9][a-z0-9.-]{1,63}$") | not) then "bug_id invalid" else empty end),
      (if (.error_signature | is_str_re("^[a-z0-9:_-]{8,128}$") | not) then "error_signature invalid" else empty end),
      (if (.expected_minutes | is_int_range(1; 480) | not) then "expected_minutes invalid" else empty end),
      (if (.estimated_loc | is_int_range(1; 5000) | not) then "estimated_loc invalid" else empty end),
      (if (.touches_api_or_schema | is_bool | not) then "touches_api_or_schema invalid" else empty end),
      (if (.touches_security_or_auth | is_bool | not) then "touches_security_or_auth invalid" else empty end),
      (if (.quick_test_available | is_bool | not) then "quick_test_available invalid" else empty end)
    ] | .[]
  ' "$input_file"
)"

if [[ -n "$errors" ]]; then
  echo "SCHEMA_INVALID"
  printf '%s\n' "$errors"
  exit 1
fi

echo "SCHEMA_VALID"
