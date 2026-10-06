#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -B -m unittest discover -s Tests -p test_travel.py
