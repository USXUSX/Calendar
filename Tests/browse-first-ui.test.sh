#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_file="$repo_root/Sources/web/app.js"
style_file="$repo_root/Sources/web/styles.css"
spec_file="$repo_root/docs/calendar-specification.md"
sample_file="$repo_root/Samples/synthetic-trip.json"

grep -Fq 'data-ai-target-type=' "$app_file"
grep -Fq 'data-ai-target-id=' "$app_file"
grep -Fq 'data-ai-target-name=' "$app_file"
grep -Fq 'data-open-ai-all' "$app_file"
grep -Fq 'function renderAiPanel(trip)' "$app_file"
grep -Fq '対象: ${escapeHtml(target.name)}' "$app_file"
grep -Fq '所要${entry.time.durationMinutes}分' "$app_file"
grep -Fq 'class="tabs bottom-nav"' "$app_file"
grep -Fq 'class="booking-table"' "$app_file"
grep -Fq 'trip.preparation.tasks' "$app_file"
grep -Fq 'type="checkbox" data-rio-packing-id=' "$app_file"
grep -Fq '.bottom-nav { position: fixed;' "$style_file"
grep -Fq '.itinerary-grid { display: grid;' "$style_file"
grep -Fq '.check-list li.completed { color: var(--ink-soft); text-decoration: none;' "$style_file"
grep -Fq 'Calendar は旅行計画の閲覧を主目的とする' "$spec_file"

if grep -Eq '候補件数|件選択中|あと[0-9]+件選択してください|変更メモ' "$app_file"; then
  printf '%s\n' 'Browse-first UI still exposes verbose selection or instruction labels.' >&2
  exit 1
fi

python3 - "$sample_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    trip = json.load(handle)

preparation = trip["preparation"]
assert "packingDueDate" not in preparation
assert "items" not in preparation
assert "specialPreparations" not in preparation
assert len(preparation["tasks"]) >= 3
assert all(task["dueDate"] for task in preparation["tasks"])
assert len({task["id"] for task in preparation["tasks"]}) == len(preparation["tasks"])
PY

printf '%s\n' 'Browse-first UI check passed.'
