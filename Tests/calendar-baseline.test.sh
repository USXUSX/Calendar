#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
baseline="$repo_root/docs/calendar-baseline.md"
decisions="$repo_root/docs/decisions.md"

for required in \
  'Trip / Event / Todo' \
  'CALのドメイン用語には`Task`を使用しない' \
  'Calendar_Local/db/calendar.sqlite3' \
  'SQLiteとformal Trip JSONのハイブリッド構成' \
  '現在の完全旅程' \
  'AI Instruction' \
  'Direct Override' \
  '現在のTrip JSON + AI Instructions + Direct Overrides' \
  'participant向けread model' \
  'Supersedeする内容' \
  '各旅行をformalな完全Trip JSONで表す基本方式' \
  '後続Issueへの分割'
do
  grep -F "$required" "$baseline" >/dev/null
done

for boundary in '| FRM |' '| TSK |' '| ENT |'; do
  grep -F "$boundary" "$baseline" >/dev/null
done

grep -F '## Active baseline' "$decisions" >/dev/null
grep -F '## Superseded' "$decisions" >/dev/null
grep -F 'One formal complete JSON per Trip remains the current itinerary representation' "$decisions" >/dev/null
grep -F 'Trip itinerary changes have two distinct input paths' "$decisions" >/dev/null
grep -F 'Participant access must use a read-only model derived from owner data' "$decisions" >/dev/null

printf '%s\n' 'Calendar baseline documentation check passed.'
