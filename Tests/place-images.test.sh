#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHONPATH=.:Tests python3 -B -m unittest test_place_images.PlaceImagesTest
