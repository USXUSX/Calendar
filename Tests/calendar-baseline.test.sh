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
  'authoritativeな完全旅程base' \
  'effective Trip' \
  'Trip由来Event' \
  '通常のSQLite `Event`として正本複製しない' \
  '`trip_id`とsource item' \
  'AI Instruction' \
  'Direct Override' \
  'AI Instruction + CAL-owned base Trip/version/hash' \
  'AI / WorkがJSON Patch生成' \
  'stale version/hashはPatch非適用' \
  '統一Event read modelと更新command境界' \
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
grep -F 'AI / Work returns only the supported `add / remove / replace` JSON Patch subset' "$decisions" >/dev/null
grep -F 'Successful adoption alone increments Trip version' "$decisions" >/dev/null
grep -F 'Trip itinerary changes have two distinct input paths' "$decisions" >/dev/null
grep -F 'Trip itinerary items such as `scheduleItem` and `transport` remain authoritative in formal Trip JSON' "$decisions" >/dev/null
grep -F 'A Direct Override targets a Trip item by stable ID' "$decisions" >/dev/null
grep -F 'AI or validation failure preserves current Trip JSON' "$decisions" >/dev/null
grep -F 'Update commands preserve source authority even in a unified Schedule' "$decisions" >/dev/null
grep -F 'Participant access must use a read-only model derived from the effective Trip' "$decisions" >/dev/null

printf '%s\n' 'Calendar baseline documentation check passed.'
