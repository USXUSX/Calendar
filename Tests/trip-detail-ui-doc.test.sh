#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ui="$root/docs/trip-detail-ui.md"
roadmap="$root/docs/development-roadmap.md"
spec="$root/docs/calendar-specification.md"

test -f "$ui"
grep -F 'iPad miniでは下sheet、iPadでは右side' "$ui" >/dev/null
grep -F 'hoverだけでは編集iconを表示しない' "$ui" >/dev/null
grep -F '候補名の右側' "$ui" >/dev/null
grep -F '日単位では折りたたまない' "$ui" >/dev/null
grep -F '現在のPhase 3' "$roadmap" >/dev/null
grep -F 'trip-detail-ui.md' "$spec" >/dev/null

if grep -F '現在のPhase 1' "$roadmap" >/dev/null; then
  printf '%s\n' 'Roadmap still marks Phase 1 as current.' >&2
  exit 1
fi

printf '%s\n' 'Trip detail UI documentation check passed.'
