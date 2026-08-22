#!/bin/sh

set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

python3 - "$root" <<'PY'
import copy
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "scripts"))
from validate_trip import validate_value

schema = json.loads((root / "Schemas" / "trip.schema.json").read_text())
trip = json.loads((root / "Samples" / "synthetic-trip.json").read_text())
trip = copy.deepcopy(trip)
trip["places"][0]["urls"] = ["https://example.com/place"]
errors = validate_value(trip, schema)
assert not errors, errors
PY

printf '%s\n' 'Schema pattern semantics check passed.'
