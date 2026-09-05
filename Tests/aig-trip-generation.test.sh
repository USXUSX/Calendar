#!/bin/sh
set -eu

python3 -m unittest Tests.test_aig_trip_generation Tests.test_candidate_diagnostic
