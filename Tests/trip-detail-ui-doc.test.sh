#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ui="$root/docs/trip-detail-ui.md"
roadmap="$root/docs/development-roadmap.md"
model="$root/docs/trip-detail-model.md"
spec="$root/docs/calendar-specification.md"

test -f "$ui"
grep -F 'iPad miniでは下sheet、iPadでは右side' "$ui" >/dev/null
grep -F 'hoverだけでは編集iconを表示しない' "$ui" >/dev/null
grep -F '候補名の右側' "$ui" >/dev/null
grep -F '日単位では折りたたまない' "$ui" >/dev/null
grep -F '現在のPhase 4' "$roadmap" >/dev/null
grep -F '**完了（us確認済み）**: Working Tripの保存・合成境界' "$roadmap" >/dev/null
grep -F '**完了（us確認済み）**: 既存予定の変更・削除予定化' "$roadmap" >/dev/null
grep -F '**現在**: 共通編集sheetを用いた新規予定仮追加' "$roadmap" >/dev/null
grep -F '`item_changes`: 既存予定の変更と削除予定' "$model" >/dev/null
grep -F '`temporary_items`: 新規仮追加' "$model" >/dev/null
grep -F '`day_instructions`: day-level指示' "$model" >/dev/null
grep -F 'formal Trip相当の' "$model" >/dev/null
grep -F 'trip-detail-ui.md' "$spec" >/dev/null

if grep -F '現在のPhase 3' "$roadmap" >/dev/null; then
  printf '%s\n' 'Roadmap still marks Phase 3 as current.' >&2
  exit 1
fi

printf '%s\n' 'Trip detail UI documentation check passed.'
