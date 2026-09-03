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
grep -F '`export_working_trip_for_chat`' "$contract" >/dev/null
grep -F '`adopt_working_trip_candidate(trip_id, candidate)`' "$contract" >/dev/null
grep -F 'candidate file pathや生成元情報は受け取らず' "$contract" >/dev/null
grep -F '`status: accepted`' "$contract" >/dev/null
grep -F 'captured effective revisionとcurrent effective revisionを比較' "$contract" >/dev/null
grep -F 'staleでもWorkingの表示・編集・再exportは継続' "$contract" >/dev/null
grep -F '共通のatomic adoption層をgenerator-neutralに分離' "$contract" >/dev/null
grep -F '採用成功後だけ同じTripのWorking rowを削除' "$contract" >/dev/null
grep -F 'raw Working envelopeをユーザー意図' "$contract" >/dev/null
grep -F 'formal complete Trip JSON object 1個だけ' "$contract" >/dev/null
grep -F '### Step 8: Place enrichment' "$contract" >/dev/null
grep -F '場所名だけを引き続き許容' "$contract" >/dev/null
grep -F 'provider-neutralな要求' "$contract" >/dev/null
grep -F '同名候補を自動採用したりしない' "$contract" >/dev/null
grep -F '外部Place IDが永続的に必要だと確認された場合だけ' "$contract" >/dev/null
grep -F 'provider/API接続' "$contract" >/dev/null
grep -F '新規Trip作成はbaseを持たない' "$contract" >/dev/null
grep -F 'map-readinessを満たす' "$contract" >/dev/null
grep -F '地図用の別正本は作らない' "$contract" >/dev/null
grep -F 'AIG' "$contract" >/dev/null

printf '%s\n' 'Trip detail model contract check passed.'
