#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
sample_file="$repo_root/Samples/synthetic-trip.json"
web_dir="$repo_root/Sources/web"

test -f "$sample_file"
test -f "$web_dir/index.html"
test -f "$web_dir/trip.html"
test -f "$web_dir/app.js"
test -f "$web_dir/styles.css"

python3 - "$sample_file" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    trip = json.load(handle)

required_trip = {"id", "title", "dateRange", "days", "places", "transports", "preparation", "rioPlan", "bookings"}
assert required_trip <= trip.keys()
assert len(trip["days"]) >= 3

place_by_id = {place["id"]: place for place in trip["places"]}
transport_by_id = {transport["id"]: transport for transport in trip["transports"]}
assert len(place_by_id) == len(trip["places"])
assert len(transport_by_id) == len(trip["transports"])

time_modes = set()
selection_shapes = set()
for day in trip["days"]:
    entries = list(day["scheduleItems"]) + [transport_by_id[item_id] for item_id in day["transportIds"]]
    orders = [entry["order"] for entry in entries]
    assert len(orders) == len(set(orders)), f"duplicate order in {day['id']}"
    for item in day["scheduleItems"]:
        assert item["dayId"] == day["id"]
        assert {"action", "time", "placeSelection"} <= item.keys()
        time_modes.add(item["time"]["mode"])
        selection = item["placeSelection"]
        assert {"candidatePlaceIds", "selection", "minSelections", "maxSelections"} <= selection.keys()
        assert all(place_id in place_by_id for place_id in selection["candidatePlaceIds"])
        selection_shapes.add((selection["minSelections"], selection["maxSelections"]))

assert time_modes == {"fixed", "range", "undecided"}
assert {(1, 1), (1, 2), (1, None), (None, None)} <= selection_shapes

for transport in trip["transports"]:
    assert transport["fromPlaceId"] in place_by_id
    assert transport["toPlaceId"] in place_by_id

for place in trip["places"]:
    rating = place["rating"]
    if place["category"] == "restaurant":
        assert rating and rating["source"] == "食べログ"
    if place["category"] == "hotel":
        assert rating and rating["source"] == "楽天トラベル"

preparation = trip["preparation"]
assert preparation["tasks"]
assert all({"id", "label", "dueDate", "completed", "order"} <= task.keys() for task in preparation["tasks"])
assert any(item["completed"] for item in preparation["tasks"])

rio_plan = trip["rioPlan"]
assert rio_plan["careMode"] in {"accompany", "leave", "undecided"}
assert rio_plan["careDecisionDueDate"]
assert any(item["notNeeded"] for item in rio_plan["packingItems"])

assert {booking["category"] for booking in trip["bookings"]} == {"accommodation", "transport", "activity", "other"}
assert all("aiInstructions" not in booking for booking in trip["bookings"])
PY

grep -Fq 'data-page="home"' "$web_dir/index.html"
grep -Fq 'data-page="trip"' "$web_dir/trip.html"
grep -Fq 'data-tab="itinerary"' "$web_dir/app.js"
grep -Fq 'data-tab="map"' "$web_dir/app.js"
grep -Fq 'data-tab="preparation"' "$web_dir/app.js"
grep -Fq 'data-tab="notes"' "$web_dir/app.js"
grep -Fq 'fetch(SAMPLE_URL' "$web_dir/app.js"
grep -Fq 'editingCommentKey' "$web_dir/app.js"
grep -Fq 'data-edit-comment' "$web_dir/app.js"
grep -Fq 'class="booking-content"' "$web_dir/app.js"
grep -Fq 'body { font-size: 17px; }' "$web_dir/styles.css"
grep -Fq 'const formatShortDateRange = ({ start, end }) => `${formatDate(start)}〜${formatDate(end)}`;' "$web_dir/app.js"
grep -Fq 'formatShortDateRange(trip.dateRange)' "$web_dir/app.js"
grep -Fq 'body[data-page="home"] .calendar-cell { min-height: 103px; padding: 4px; }' "$web_dir/styles.css"
grep -Fq 'body[data-page="home"] .calendar-cell { min-height: 86px; }' "$web_dir/styles.css"
grep -Fq 'body[data-page="home"] .page-shell * { font-family: inherit; }' "$web_dir/styles.css"
grep -Fq -- '-webkit-line-clamp: 2;' "$web_dir/styles.css"
grep -Fq 'body[data-page="home"] .home-columns h2 { color: #4f8060; font-weight: 800; }' "$web_dir/styles.css"
grep -Fq 'body[data-page="home"] .trip-line span { color: #365452; font-weight: 700; }' "$web_dir/styles.css"
if grep -Fq '<textarea data-instruction-key="${escapeHtml(key)}" aria-label="コメントを編集">' "$web_dir/app.js"; then
  printf '%s\n' 'Comment textarea is still always visible.' >&2
  exit 1
fi

if grep -Eq 'method:[[:space:]]*"(POST|PUT|PATCH|DELETE)|XMLHttpRequest|WebSocket|localStorage|sessionStorage|https?://' "$web_dir/app.js"; then
  printf '%s\n' 'Read-only UI contains a write, persistence, or external-service path.' >&2
  exit 1
fi

printf '%s\n' 'Read-only synthetic UI check passed.'
