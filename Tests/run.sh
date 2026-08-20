#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

find "$repo_root/Samples" -type f -name '*.json' -print |
  while IFS= read -r json_file; do
    python3 -m json.tool "$json_file" >/dev/null
  done

for test_file in "$repo_root"/Tests/*.test.sh; do
  sh "$test_file"
done

printf '%s\n' 'All project checks passed.'
