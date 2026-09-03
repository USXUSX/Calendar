#!/bin/sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
contract="$root/docs/trip-detail-model.md"

test -f "$contract"
grep -F '表示モデル自体を保存せず' "$contract" >/dev/null
grep -F 'effective Trip' "$contract" >/dev/null
grep -F '未送信の`OK / NG`' "$contract" >/dev/null
grep -F 'trip_item_local_update' "$contract" >/dev/null
grep -F 'generation_requests' "$contract" >/dev/null
grep -F 'complete candidate Validation' "$contract" >/dev/null
grep -F 'base_effective_revision' "$contract" >/dev/null
grep -F '自動再適用・自動mergeを行わない' "$contract" >/dev/null
grep -F '`disposition`を`changed`または`pending_delete`' "$contract" >/dev/null
grep -F '通常へ戻す場合はrecordを削除する' "$contract" >/dev/null
grep -F 'formal Trip schemaを' "$contract" >/dev/null
grep -F 'stable `temporary_id`' "$contract" >/dev/null
grep -F '手入力だけで作成・更新できる' "$contract" >/dev/null
grep -F '`anchor_source_item_id`、`edge`' "$contract" >/dev/null
grep -F 'temporary item同士をanchorにする連鎖' "$contract" >/dev/null
grep -F '`day_instructions`は既存`day_id`' "$contract" >/dev/null
grep -F '個別予定へ分解・適用しない' "$contract" >/dev/null
grep -F 'Step 6のWorking合成表示も行わない' "$contract" >/dev/null
grep -F '`get_working_trip_detail_view`はauthoritative Trip' "$contract" >/dev/null
grep -F '`working_state: pending_delete`' "$contract" >/dev/null
grep -F 'raw Working envelopeをconsumerへ渡さず' "$contract" >/dev/null
grep -F 'D案UIからの既存予定編集は`save_working_trip_item_change`' "$contract" >/dev/null
grep -F 'Workingをstale化しない' "$contract" >/dev/null
grep -F '新規Trip作成はbaseを持たない' "$contract" >/dev/null
grep -F 'map-readinessを満たす' "$contract" >/dev/null
grep -F '地図用の別正本は作らない' "$contract" >/dev/null
grep -F 'AIG' "$contract" >/dev/null

printf '%s\n' 'Trip detail model contract check passed.'
