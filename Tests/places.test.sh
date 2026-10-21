#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHONPATH=. python3 -B -m unittest discover -s Tests -p test_places.py
