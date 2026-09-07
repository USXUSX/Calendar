#!/bin/sh
set -eu
python3 -m unittest discover -s Tests -p test_direct_schedule.py
