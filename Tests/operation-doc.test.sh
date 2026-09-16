#!/bin/sh

set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
operation="$root/docs/operation.md"

test -f "$operation"

for required in \
  '/Users/us/Tools/LocalData/Calendar_Local' \
  '/Users/us/マイドライブ/Tools/Calendar_Chat' \
  '/Users/us/マイドライブ/Tools/Calendar_GD' \
  '(trip-json-generation.md)' \
  '(trip-json-import.md)' \
  '/calendar/import' \
  '/calendar/trips' \
  '通常load/reloadは読み取り専用ではありません' \
  '## 保持している旧経路'
do
  grep -F "$required" "$operation" >/dev/null
done

grep -F 'python3 scripts/serve_calendar.py' "$operation" >/dev/null
grep -F '移動はTransportだけにする' "$root/docs/trip-json-generation.md" >/dev/null
grep -F 'selectionはcandidatePlaceIdsの部分集合' "$root/docs/trip-json-generation.md" >/dev/null
grep -F '受渡しとCAL採用の境界' "$root/docs/trip-json-generation.md" >/dev/null
grep -F '(docs/operation.md)' "$root/README.md" >/dev/null

if git -C "$root" ls-files | grep -E '(^|/)trips/.*\.json$|(^|/)current\.json$|(^|/)candidate\.json$|(^|/)history/' >/dev/null; then
  echo 'Private operational trip data must not be tracked by Git.' >&2
  exit 1
fi

echo 'Operation documentation checks passed.'
