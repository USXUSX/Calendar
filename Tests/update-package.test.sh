#!/bin/sh

set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
node "$root/Tests/update-package.test.mjs"
