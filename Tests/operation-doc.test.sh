#!/bin/sh

set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
operation="$root/docs/operation.md"

test -f "$operation"

for required in \
  'Calendar_Local/trips/<trip-id>/' \
  'current.json' \
  'candidate.json' \
  'history/' \
  '採用済みの元 `current.json` 全文' \
  '差分や部分JSONではなく' \
  '不採用の場合' \
  '新規旅行を作る入口'
do
  grep -F "$required" "$operation" >/dev/null
done

grep -F 'python3 scripts/serve_calendar.py' "$operation" >/dev/null
grep -F '「AI更新依頼をコピー」' "$operation" >/dev/null
grep -F '候補版・未採用' "$operation" >/dev/null
grep -F '元の `current.json`' "$operation" >/dev/null

grep -F '[`docs/operation.md`](docs/operation.md)' "$root/README.md" >/dev/null

if git -C "$root" ls-files | grep -E '(^|/)current\.json$|(^|/)candidate\.json$|(^|/)history/' >/dev/null; then
  echo 'Private operational trip data must not be tracked by Git.' >&2
  exit 1
fi

echo 'Operation documentation checks passed.'
