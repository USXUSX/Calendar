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
grep -F '| 4. Working Trip編集基盤 | 完了 |' "$roadmap" >/dev/null
grep -F '| 5. Working Trip確定フロー | 完了 |' "$roadmap" >/dev/null
grep -F '| 6. AI接続を実用化 | 現在 |' "$roadmap" >/dev/null
grep -F '### 完了したPhase 5: Working Trip確定フロー' "$roadmap" >/dev/null
grep -F '1. **完了（us確認済み）**: candidate受入れ・確定境界を確定する。' "$roadmap" >/dev/null
grep -F '2. **完了（us確認済み）**: complete candidate受入れを実装する。' "$roadmap" >/dev/null
grep -F '3. **完了（us確認済み）**: stale確認を確定ゲートへ接続する。' "$roadmap" >/dev/null
grep -F '4. **完了（us確認済み）**: formal Validationを確定する。' "$roadmap" >/dev/null
grep -F '5. **完了（us確認済み）**: atomic adoptionとWorking後始末を実装する。' "$roadmap" >/dev/null
grep -F '6. **完了（us確認済み）**: Chat手動往復の受入れを合成データで確認する。' "$roadmap" >/dev/null
grep -F '7. **完了（us確認済み）**: FRMの最小確定導線を実装する。' "$roadmap" >/dev/null
grep -F '8. **完了（us確認済み）**: Phase 5全体を合成データでValidationする。' "$roadmap" >/dev/null
grep -F '9. **完了（us確認済み）**: Phase 5を振り返り、Phase 6のAI接続境界を再確認する。' "$roadmap" >/dev/null
grep -F 'Working export → generator-neutralなcomplete candidate → CAL Validation' "$roadmap" >/dev/null
grep -F '1. **完了（us確認済み）**: AIG接続境界と最小generation stateを確定する。' "$roadmap" >/dev/null
grep -F '2. **完了（us確認済み）**: CALにWorking Tripごとの最新generation stateとcandidateを実装する。' "$roadmap" >/dev/null
grep -F '3. **完了（us確認済み）**: AIGにWorking exportからcomplete candidateを1件返すstatelessな最小生成境界を実装する。' "$roadmap" >/dev/null
grep -F '4. **完了（us確認済み）**: CAL → AIG → Phase 5 candidate受入れを接続する。' "$roadmap" >/dev/null
grep -F '5. **完了**: `auto / review` adoption policyを実装する。' "$roadmap" >/dev/null
grep -F 'AIGはworkflow stateを保持せず' "$roadmap" >/dev/null
grep -F 'candidate受入れ、Schema・semantic Validation、captured revisionに対するstale確認、all-or-nothingのadoption' "$roadmap" >/dev/null
grep -F '自動retry、queue、履歴' "$roadmap" >/dev/null
grep -F 'CAL外旅行計画正本更新、production activation' "$roadmap" >/dev/null
grep -F '`item_changes`: 既存予定の変更と削除予定' "$model" >/dev/null
grep -F '`temporary_items`: 新規仮追加' "$model" >/dev/null
grep -F '`day_instructions`: day-level指示' "$model" >/dev/null
grep -F 'formal Trip相当の' "$model" >/dev/null
grep -F '## Phase 6のAIG接続境界と最小generation state' "$model" >/dev/null
grep -F '`generation_id`、`trip_id`' "$model" >/dev/null
grep -F '`generating / candidate_ready / failed / adopted`' "$model" >/dev/null
grep -F '生成identity不一致の' "$model" >/dev/null
grep -F 'trip-detail-ui.md' "$spec" >/dev/null

if grep -F '現在のPhase 5' "$roadmap" >/dev/null; then
  printf '%s\n' 'Roadmap still marks Phase 5 as current.' >&2
  exit 1
fi

printf '%s\n' 'Trip detail UI documentation check passed.'
