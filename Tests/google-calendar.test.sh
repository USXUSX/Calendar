#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 -B -m unittest discover -s Tests -p test_google_calendar.py
