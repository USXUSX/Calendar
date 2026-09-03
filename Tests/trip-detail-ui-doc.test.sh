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
grep -F '9. **完了**: Phase 5を振り返り、Phase 6のAI接続境界を再確認する。' "$roadmap" >/dev/null
grep -F 'Working export → generator-neutralなcomplete candidate → CAL Validation' "$roadmap" >/dev/null
grep -F 'candidate生成成功だけではauthoritative Tripを変更しない' "$roadmap" >/dev/null
grep -F '最初の接続先をAIGとするか' "$roadmap" >/dev/null
grep -F 'candidate受入れ、Schema・semantic Validation、captured revisionに対するstale確認、all-or-nothingのadoption' "$roadmap" >/dev/null
grep -F 'candidate生成・再構成の自動化はPhase 6' "$roadmap" >/dev/null
grep -F 'CAL外の旅行計画正本更新は当面手運用でCAL責務に含めない' "$roadmap" >/dev/null
grep -F '`item_changes`: 既存予定の変更と削除予定' "$model" >/dev/null
grep -F '`temporary_items`: 新規仮追加' "$model" >/dev/null
grep -F '`day_instructions`: day-level指示' "$model" >/dev/null
grep -F 'formal Trip相当の' "$model" >/dev/null
grep -F 'trip-detail-ui.md' "$spec" >/dev/null

if grep -F '現在のPhase 5' "$roadmap" >/dev/null; then
  printf '%s\n' 'Roadmap still marks Phase 5 as current.' >&2
  exit 1
fi

printf '%s\n' 'Trip detail UI documentation check passed.'
