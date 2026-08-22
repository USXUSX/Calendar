#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_file="$repo_root/Sources/web/app.js"
style_file="$repo_root/Sources/web/styles.css"
spec_file="$repo_root/docs/calendar-specification.md"
sample_file="$repo_root/Samples/synthetic-trip.json"

grep -Fq 'function renderAiPanel(trip)' "$app_file"
grep -Fq '<h3 id="ai-panel-title">コメント</h3>' "$app_file"
grep -Fq 'timeBlock(entry.time)' "$app_file"
grep -Fq 'class="tabs bottom-nav"' "$app_file"
grep -Fq 'class="booking-table"' "$app_file"
grep -Fq 'trip.preparation.tasks' "$app_file"
grep -Fq 'type="checkbox" data-rio-packing-id=' "$app_file"
grep -Fq '.bottom-nav { position: fixed;' "$style_file"
grep -Fq 'class="day-switcher"' "$app_file"
grep -Fq 'data-itinerary-day=' "$app_file"
grep -Fq 'itineraryDay: "all"' "$app_file"
grep -Fq 'data-toggle-day=' "$app_file"
grep -Fq 'class="all-days"' "$app_file"
grep -Fq 'class="itinerary-row' "$app_file"
grep -Fq 'data-map-day=' "$app_file"
grep -Fq 'data-toggle-map-day=' "$app_file"
grep -Fq 'class="map-day-heading" data-toggle-map-day=' "$app_file"
grep -Fq '<span class="day-date">${formatDate(day.date)}' "$app_file"
grep -Fq '<span class="day-copy"><strong>${escapeHtml(day.title)}</strong>' "$app_file"
if grep -Eq '^\.day-toggle strong .*Georgia' "$style_file"; then
  echo "Itinerary day themes must use the shared font family" >&2
  exit 1
fi
grep -Fq 'categoryFilter("map", draftState.mapCategory)' "$app_file"
grep -Fq 'カレンダー</a>' "$app_file"
grep -Fq 'data-comment-count' "$app_file"
grep -Fq 'function commentCount()' "$app_file"
grep -Fq 'formatDateRange' "$app_file"
grep -Fq '<header class="home-header"><h1>カレンダー</h1><time>2026/8/21（金）</time></header>' "$app_file"
grep -Fq 'class="trip-summary"><h1>${escapeHtml(trip.title)}<span>（' "$app_file"
grep -Fq 'data-new-trip-comment' "$app_file"
grep -Fq 'data-add-trip-comment' "$app_file"
grep -Fq '<h3>リオ　${trip.rioPlan.careMode' "$app_file"
grep -Fq '.bottom-nav { left: 0; bottom: 0; width: 100%;' "$style_file"
grep -Fq '.trip-summary { position: fixed;' "$style_file"
grep -Fq '.page-shell { width: calc(100vw - 24px); max-width: none;' "$style_file"
grep -Fq 'class="top-controls"' "$app_file"
grep -Fq '.trip-summary h1 { font-size: 27px; }' "$style_file"
grep -Fq '.itinerary-row { grid-template-columns: 98px 84px minmax(0,1fr);' "$style_file"
grep -Fq '.itinerary-row { grid-template-columns: 88px 72px minmax(0,1fr);' "$style_file"
grep -Fq 'class="candidate-check"' "$app_file"
grep -Fq '.entry-time { border-right: 0; }' "$style_file"
grep -Fq '.entry-classification { border: 0; }' "$style_file"
grep -Fq '.map-card { position: sticky;' "$style_file"
grep -Fq 'grid-template-columns: repeat(2, minmax(0, 1fr));' "$style_file"
grep -Fq 'class="candidate-copy"' "$app_file"
if grep -Fq 'class="cost-summary"' "$app_file"; then
  printf '%s\n' 'Preparation must not render the removed cost total block.' >&2
  exit 1
fi
grep -Fq '.page-shell, .page-shell * { font-family: inherit; }' "$style_file"
grep -Fq '.page-shell { width: calc(100% - 24px); }' "$style_file"
if grep -Fq 'class="row-action"' "$app_file"; then
  printf '%s\n' 'Per-row action buttons must not appear in the browse-first UI.' >&2
  exit 1
fi
grep -Fq '.check-list li.completed { color: var(--ink-soft); text-decoration: none;' "$style_file"
grep -Fq 'Calendar は旅行計画の閲覧を主目的とする' "$spec_file"

if grep -Eq '候補件数|件選択中|あと[0-9]+件選択してください|変更メモ|SYNTHETIC TRIP|AI UPDATE MATERIAL|PREPARATION|RIO PLAN|BOOKING' "$app_file"; then
  printf '%s\n' 'Browse-first UI still exposes verbose selection or instruction labels.' >&2
  exit 1
fi

if grep -Fq '更新材料をコピー</button>' "$app_file"; then
  printf '%s\n' 'Comment screen must not expose a persistent update-material copy button.' >&2
  exit 1
fi

if grep -Fq 'itinerary-grid' "$app_file" || grep -Fq '.itinerary-grid' "$style_file"; then
  printf '%s\n' 'Itinerary must show all days vertically instead of placing days in a grid.' >&2
  exit 1
fi

if grep -Fq 'data-day-anchor=' "$app_file"; then
  printf '%s\n' 'Itinerary date navigation must use the shared filter interaction.' >&2
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
assert all(day["routeSummary"] for day in trip["days"])
assert all(item["category"] in {"sightseeing", "food", "accommodation"} for day in trip["days"] for item in day["scheduleItems"])
assert trip["rioPlan"]["applicable"] is True
assert all({"targetDate", "reserved"} <= booking.keys() for booking in trip["bookings"])
PY

printf '%s\n' 'Browse-first UI check passed.'
