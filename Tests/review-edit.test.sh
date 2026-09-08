#!/bin/sh
set -eu
python3 -m unittest discover -s Tests -p test_review_edit.py
