#!/usr/bin/env python3
"""CAL sightseeing commands for existing RDC; JSON in/out, no implicit migration."""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain import CalendarDomain, DomainError, ConflictError

ROOT = Path('/Users/us/Tools/LocalData/Calendar_Local')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, default=ROOT/'db/calendar.sqlite3')
    p.add_argument('--local-root', type=Path, default=ROOT)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('read')
    get = sub.add_parser('get'); get.add_argument('--id', type=int, required=True)
    lookup = sub.add_parser('lookup'); lookup.add_argument('--request-id', required=True)
    sub.add_parser('apply')
    sub.add_parser('image')
    a = p.parse_args()
    try:
        cal = CalendarDomain(a.database, a.local_root)
        if a.action == 'read': result = dict(status='ok', places=cal.list_places())
        elif a.action == 'get': result = dict(status='ok', item=cal.get_place(a.id))
        elif a.action == 'lookup': result = cal.lookup_place_request(a.request_id)
        elif a.action == 'image': result = cal.apply_place_image_request(json.load(sys.stdin))
        else: result = cal.apply_place_request(json.load(sys.stdin))
        print(json.dumps(result, ensure_ascii=False))
        return 4 if result['status'] == 'not_found' else 0
    except ConflictError as e:
        result, code = dict(status='rejected', reason=str(e)), 3
    except (DomainError, ValueError, TypeError) as e:
        unknown = str(e).startswith('Calendar database')
        result, code = dict(status='unknown' if unknown else 'rejected', reason=str(e)), 5 if unknown else 2
    except (OSError, sqlite3.Error):
        result, code = dict(status='unknown', reason='storage_unavailable'), 5
    print(json.dumps(result)); return code


if __name__ == '__main__':
    raise SystemExit(main())
