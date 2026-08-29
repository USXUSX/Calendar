#!/bin/sh

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHONPATH="$repo_root" python3 "$repo_root/Tests/test_calendar_domain.py"
