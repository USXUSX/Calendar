#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -m unittest Tests.test_comment_enrichment
