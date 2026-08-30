#!/usr/bin/env python3
"""Process at most one CAL generation request with an external Patch generator."""

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from Sources.calendar_domain import CalendarDomain
from Sources.calendar_worker import command_generator, run_once


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="explicit CAL SQLite path")
    parser.add_argument("--trip-root", required=True, type=Path, help="explicit CAL Trip data root")
    parser.add_argument("--timeout", type=float, default=60.0, help="generator timeout in seconds")
    parser.add_argument("generator", nargs=argparse.REMAINDER, help="generator argv after --")
    args = parser.parse_args()
    generator_argv = args.generator[1:] if args.generator[:1] == ["--"] else args.generator
    result = run_once(CalendarDomain(args.db, args.trip_root), command_generator(generator_argv, args.timeout))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"no-op", "adopted"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
