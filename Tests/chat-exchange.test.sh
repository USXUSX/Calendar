#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest Tests.test_chat_exchange
