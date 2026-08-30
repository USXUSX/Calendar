#!/bin/sh
set -eu

python3 -m unittest Tests.test_openai_patch_generator
