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
grep -Fq 'const daySwitcher = (scope, active, days)' "$app_file"
grep -Fq 'daySwitcher("itinerary", draftState.itineraryDay, trip.days)' "$app_file"
grep -Fq 'daySwitcher("map", draftState.mapDay, trip.days)' "$app_file"
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
grep -Fq 'formatCurrentDate = (date = new Date())' "$app_file"
grep -Fq '<time datetime="${formatIsoLocalDate()}">${formatCurrentDate()}</time>' "$app_file"
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
grep -Fq '.day-heading { grid-template-columns: minmax(0, 1fr); gap: 0; padding-right: 0; }' "$style_file"
grep -Fq '.day-toggle { width: 100%; }' "$style_file"
grep -Fq '.map-day-heading .day-label { font-size: 21px; white-space: nowrap; }' "$style_file"
grep -Fq '.map-day-heading { grid-template-columns: 180px minmax(0, 1fr) auto; gap: 8px; }' "$style_file"
grep -Fq '.map-day-heading .day-copy strong { color: var(--ink); }' "$style_file"
grep -Fq '.map-day-heading .day-date {' "$style_file"
grep -Fq 'font-size: 21px;' "$style_file"
grep -Fq 'font-weight: 600;' "$style_file"
grep -Fq 'font-variant-numeric: proportional-nums;' "$style_file"
grep -Fq 'font-feature-settings: "palt" 1, "pnum" 1;' "$style_file"
grep -Fq 'letter-spacing: normal;' "$style_file"
if grep -Fq '.map-day-heading { grid-template-columns: 112px' "$style_file"; then
  printf '%s\n' 'Itinerary and map day headings must share the same first-column width.' >&2
  exit 1
fi
grep -Fq 'grid-template-columns: repeat(2, minmax(0, 1fr));' "$style_file"
grep -Fq 'class="candidate-copy"' "$app_file"
grep -Fq 'draftState.itineraryDay === selectedDay ? "all" : selectedDay' "$app_file"
grep -Fq 'draftState.collapsedDays.delete(draftState.itineraryDay)' "$app_file"
grep -Fq 'draftState.itineraryCategory === selectedCategory ? "all" : selectedCategory' "$app_file"
grep -Fq 'formatDateWithWeekday(item.dueDate)' "$app_file"
grep -Fq 'formatDateWithWeekday(booking.targetDate)' "$app_file"
grep -Fq 'const reserved = booking.status === "booked"' "$app_file"
grep -Fq '.map-layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: 18px; }' "$style_file"
grep -Fq '.candidate-copy small { font-size: inherit;' "$style_file"
grep -Fq 'grid-template-columns: 30px 112px 132px minmax(0, 1fr) 88px;' "$style_file"
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
if grep -Eq 'modeLabels|function formatTime|function selectionLabel|data-reset-draft|data-ai-target-type|data-open-ai-all|data-update-count' "$app_file"; then
  printf '%s\n' 'Removed UI behavior must not leave unreachable JavaScript behind.' >&2
  exit 1
fi
if grep -Eq 'row-action|cost-summary|cost-breakdown' "$style_file"; then
  printf '%s\n' 'Removed UI controls must not leave obsolete CSS behind.' >&2
  exit 1
fi
grep -Fq '.check-list li.completed { color: var(--ink-soft); text-decoration: none;' "$style_file"
grep -Fq 'Calendar は旅行計画の閲覧を主目的とする' "$spec_file"
grep -Fq '`targetDate`: 予約・手配の対象日を表す必須の日付' "$spec_file"

if grep -Eq '候補件数|件選択中|あと[0-9]+件選択してください|変更メモ|SYNTHETIC TRIP|AI UPDATE MATERIAL|PREPARATION|RIO PLAN|BOOKING' "$app_file"; then
  printf '%s\n' 'Browse-first UI still exposes verbose selection or instruction labels.' >&2
  exit 1
fi

grep -Fq 'data-open-comment-target' "$app_file"
grep -Fq 'data-copy-update' "$app_file"

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
assert all({"targetDate", "status"} <= booking.keys() for booking in trip["bookings"])
assert all("reserved" not in booking for booking in trip["bookings"])
restaurants = [place for place in trip["places"] if place["category"] == "restaurant"]
assert any(place.get("summary") for place in restaurants)
PY

printf '%s\n' 'Browse-first UI check passed.'
