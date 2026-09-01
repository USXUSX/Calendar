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
grep -F 'AIG' "$contract" >/dev/null

printf '%s\n' 'Trip detail model contract check passed.'
