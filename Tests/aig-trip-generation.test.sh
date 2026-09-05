#!/bin/sh
set -eu

python3 -m unittest Tests.test_aig_trip_generation Tests.test_candidate_diagnostic Tests.test_candidate_diff Tests.test_review_promotion Tests.test_candidate_preview
