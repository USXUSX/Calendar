#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
baseline="$repo_root/docs/calendar-baseline.md"
decisions="$repo_root/docs/decisions.md"

for required in \
  'Trip / Event / Todo' \
  'CALのドメイン用語には`Task`を使用しない' \
  'Calendar_Local/db/calendar.sqlite3' \
  'JSONは正本ではない' \
  'participant向けread model' \
  'Supersedeする内容' \
  '後続Issueへの分割'
do
  grep -F "$required" "$baseline" >/dev/null
done

for boundary in '| FRM |' '| TSK |' '| ENT |'; do
  grep -F "$boundary" "$baseline" >/dev/null
done

grep -F '## Active baseline' "$decisions" >/dev/null
grep -F '## Superseded' "$decisions" >/dev/null
grep -F 'one private JSON file per trip' "$decisions" >/dev/null
grep -F 'Participant access must use a read-only model derived from owner data' "$decisions" >/dev/null

printf '%s\n' 'Calendar baseline documentation check passed.'
