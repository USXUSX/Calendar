#!/bin/sh

set -eu

invalid_json=$(mktemp "${TMPDIR:-/tmp}/calendar-invalid-json.XXXXXX")
trap 'rm -f "$invalid_json"' EXIT HUP INT TERM

printf '%s\n' '{"invalid": true,}' >"$invalid_json"

if python3 -m json.tool "$invalid_json" >/dev/null 2>&1; then
  printf '%s\n' 'JSON parser accepted a trailing comma.' >&2
  exit 1
fi

printf '%s\n' 'Invalid JSON rejection check passed.'
