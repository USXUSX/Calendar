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
grep -F '挿入位置や既存予定との上下関係はStep 4' "$contract" >/dev/null
grep -F '新規Trip作成はbaseを持たない' "$contract" >/dev/null
grep -F 'map-readinessを満たす' "$contract" >/dev/null
grep -F '地図用の別正本は作らない' "$contract" >/dev/null
grep -F 'AIG' "$contract" >/dev/null

printf '%s\n' 'Trip detail model contract check passed.'
