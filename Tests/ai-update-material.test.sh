#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_file="$repo_root/Sources/web/app.js"
sample_file="$repo_root/Samples/synthetic-trip.json"

grep -Fq 'function updateMaterials(trip, placesById)' "$app_file"
grep -Fq 'type: "Preparation item"' "$app_file"
grep -Fq 'type: "RioPlan packing item"' "$app_file"
grep -Fq 'type: "PlaceSelection"' "$app_file"
grep -Fq 'AIへの指示：${value.trim()}' "$app_file"
grep -Fq '対象種別: ${material.type}' "$app_file"
grep -Fq '安定ID: ${material.id}' "$app_file"
grep -Fq 'data-copy-update' "$app_file"
grep -Fq 'navigator.clipboard.writeText' "$app_file"
grep -Fq '一時状態は保持されています' "$app_file"
grep -Fq 'Bookingの正式な予約メモ' "$app_file"
grep -Fq 'materials.length ? "" : "disabled"' "$app_file"

python3 - "$sample_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    trip = json.load(handle)

assert "draftState" not in trip
assert "updateMaterials" not in trip
assert all("aiInstructions" not in booking for booking in trip["bookings"])
PY

if grep -Eq 'localStorage|sessionStorage|method:[[:space:]]*"(POST|PUT|PATCH|DELETE)|WebSocket' "$app_file"; then
  printf '%s\n' 'AI update-material UI unexpectedly contains persistence or an external-send path.' >&2
  exit 1
fi

printf '%s\n' 'AI update-material UI check passed.'
