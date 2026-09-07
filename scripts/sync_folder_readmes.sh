#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
local_source="$repo_root/templates/folder-readmes/Calendar_Local_README.md"
local_target="/Users/us/Tools/LocalData/Calendar_Local/README.md"

test -f "$local_source"
test -d "$(dirname "$local_target")"

cp "$local_source" "$local_target"

cmp "$local_source" "$local_target"

echo "Calendar local folder README synchronized from Git source."
