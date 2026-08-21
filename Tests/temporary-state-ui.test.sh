#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_file="$repo_root/Sources/web/app.js"
sample_file="$repo_root/Samples/synthetic-trip.json"

# Issue #9 interactions must be represented by browser-memory state, not by
# fields added to the adopted sample or a persistence/external-send path.
grep -Fq 'preparation: new Map()' "$app_file"
grep -Fq 'rioPacking: new Map()' "$app_file"
grep -Fq 'placeSelections: new Map()' "$app_file"
grep -Fq 'instructions: new Map()' "$app_file"
grep -Fq 'data-preparation-id=' "$app_file"
grep -Fq 'data-rio-packing-id=' "$app_file"
grep -Fq 'data-place-selection=' "$app_file"
grep -Fq 'data-instruction-key=' "$app_file"
grep -Fq 'aiPanelOpen: false' "$app_file"
grep -Fq 'aiTarget: null' "$app_file"
grep -Fq '旅程 › ${item.action}' "$app_file"
grep -Fq '旅程 › ${placesById.get(transport.fromPlaceId)?.name' "$app_file"
grep -Fq '準備 › ${placesById.get(booking?.placeId)?.name' "$app_file"
grep -Fq 'data-draft-count' "$app_file"
grep -Fq 'class="official-note"' "$app_file"

if grep -Fq 'data-instruction-toggle=' "$app_file"; then
  printf '%s\n' 'Per-item instruction fields must not remain in the browse-first UI.' >&2
  exit 1
fi

python3 - "$sample_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    trip = json.load(handle)

assert "draftState" not in trip
assert "instructions" not in trip
assert all("aiInstructions" not in booking for booking in trip["bookings"])
PY

if grep -Eq 'localStorage|sessionStorage|method:[[:space:]]*"(POST|PUT|PATCH|DELETE)|WebSocket' "$app_file"; then
  printf '%s\n' 'Temporary UI unexpectedly contains persistence or an external-send path.' >&2
  exit 1
fi

printf '%s\n' 'Temporary change-state UI check passed.'
