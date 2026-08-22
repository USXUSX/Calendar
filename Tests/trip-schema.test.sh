#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sample_file="$repo_root/Samples/synthetic-trip.json"
validator="$repo_root/scripts/validate_trip.py"
invalid_file=$(mktemp "${TMPDIR:-/tmp}/calendar-invalid-trip.XXXXXX")
trap 'rm -f "$invalid_file"' EXIT HUP INT TERM

python3 "$validator" "$sample_file" >/dev/null

python3 - "$sample_file" "$invalid_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    trip = json.load(handle)

selection = trip["days"][0]["scheduleItems"][0]["placeSelection"]
selection["candidatePlaceIds"] = ["unknown-place"]
selection["selection"] = ["unknown-place"]
with open(sys.argv[2], "w", encoding="utf-8") as handle:
    json.dump(trip, handle, ensure_ascii=False)
PY

if python3 "$validator" "$invalid_file" >/dev/null 2>&1; then
  printf '%s\n' 'Trip validator accepted an unknown Place reference.' >&2
  exit 1
fi

grep -Fq 'Schemas/trip.schema.json' "$repo_root/docs/calendar-specification.md"
grep -Fq '旧形式の変換や不足値の自動補正を行わない' "$repo_root/docs/calendar-specification.md"
grep -Fq 'Markdownや説明文は付けません' "$repo_root/docs/trip-json-generation.md"

printf '%s\n' 'Formal trip schema check passed.'
