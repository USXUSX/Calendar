#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
shared_source="$repo_root/templates/folder-readmes/Calendar_GD_README.md"
local_source="$repo_root/templates/folder-readmes/Calendar_Local_README.md"
shared_target="/Users/us/Tools/GoogleDrive/Calendar_GD/README.md"
local_target="/Users/us/Tools/LocalData/Calendar_Local/README.md"

test -f "$shared_source"
test -f "$local_source"
test -d "$(dirname "$shared_target")"
test -d "$(dirname "$local_target")"

cp "$shared_source" "$shared_target"
cp "$local_source" "$local_target"

cmp "$shared_source" "$shared_target"
cmp "$local_source" "$local_target"

echo "Calendar folder READMEs synchronized from Git sources."
