#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
guidance_file="$repo_root/AGENTS.md"
sample_file="$repo_root/Samples/project-locations.json"

test -f "$guidance_file"
test -f "$sample_file"

/usr/bin/python3 -m json.tool "$sample_file" >/dev/null

assert_in_both() {
  expected=$1
  grep -Fq "$expected" "$guidance_file"
  grep -Fq "$expected" "$sample_file"
}

assert_in_both '/Users/us/Tools/Development/Calendar_Dev'
assert_in_both '/Users/us/Tools/GoogleDrive/Calendar_GD'
assert_in_both '/Users/us/Tools/LocalData/Calendar_Local'

grep -Fq '"development"' "$sample_file"
grep -Fq '"shared_references"' "$sample_file"
grep -Fq '"private_local_data"' "$sample_file"

printf '%s\n' 'Project discovery check passed.'
