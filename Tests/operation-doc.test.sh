#!/bin/sh

set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
operation="$root/docs/operation.md"

test -f "$operation"

for required in \
  'Calendar_Local/trips/' \
  '<trip-id>.json' \
  '旧形式 JSON の互換変換は行わない' \
  '完全 JSON' \
  '候補、履歴、差分 JSON' \
  'JSON を修正または再生成' \
  '新規旅行'
do
  grep -F "$required" "$operation" >/dev/null
done

grep -F 'python3 scripts/serve_calendar.py' "$operation" >/dev/null
grep -F '生成JSONを`trips/`以外の一時作業場所へ保存' "$operation" >/dev/null
grep -F '既存IDと変更対象外の内容を維持した次版の完全JSON' "$operation" >/dev/null
grep -F '予定・移動・Placeの重複、候補Placeの欠落' "$operation" >/dev/null
grep -F '移動はTransportだけにすること' "$root/docs/trip-json-generation.md" >/dev/null
grep -F '候補Placeを先に残す項目へ統合' "$root/docs/trip-json-generation.md" >/dev/null
grep -F '生成 → 検証 → 配置 → 表示確認' "$root/docs/trip-json-generation.md" >/dev/null
grep -F '[`docs/operation.md`](docs/operation.md)' "$root/README.md" >/dev/null

if git -C "$root" ls-files | grep -E '(^|/)trips/.*\.json$|(^|/)current\.json$|(^|/)candidate\.json$|(^|/)history/' >/dev/null; then
  echo 'Private operational trip data must not be tracked by Git.' >&2
  exit 1
fi

echo 'Operation documentation checks passed.'
