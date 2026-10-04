#!/usr/bin/env python3
"""CAL schedule CLI for the existing RDC connection. One JSON response per invocation."""
import sys
sys.dont_write_bytecode = True
import argparse
import base64
import json
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain import CalendarDomain, DomainError, ConflictError

DEFAULT_ROOT = Path('/Users/us/Tools/LocalData/Calendar_Local')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, default=DEFAULT_ROOT/'db/calendar.sqlite3', help='synthetic tests only: override the existing CAL database')
    p.add_argument('--local-root', type=Path, default=DEFAULT_ROOT, help='synthetic tests only: override the CAL local root')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('doctor')
    read = sub.add_parser('read');read.add_argument('--start', required=True);read.add_argument('--end', required=True)
    get = sub.add_parser('get');get.add_argument('--kind', choices=['event','todo'], required=True);get.add_argument('--id', required=True)
    lookup = sub.add_parser('lookup');lookup.add_argument('--request-id', required=True)
    apply = sub.add_parser('apply');apply.add_argument('--request-base64', help='UTF-8 JSON encoded as base64; otherwise read JSON from stdin')
    args = p.parse_args(argv)
    try:
        if not args.database.is_file():
            raise ValueError('database_unavailable')
        # Fail before calling CAL if the additive migration is missing. No implicit init/migration.
        with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as c:
            if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_receipts'").fetchone() is None:
                raise ValueError('receipt_migration_required')
        cal = CalendarDomain(args.database, args.local_root, chat_root=args.local_root/'chat-unused')
        if args.action == 'doctor':
            result = dict(status='ready', protocol='cal-schedule-v1', receipt_storage='CAL SQLite', time_zone='Asia/Tokyo')
        elif args.action == 'read':
            result = dict(status='ok', **cal.read_schedule(args.start,args.end,include_completed=True,include_trips=False))
        elif args.action == 'get':
            result = dict(status='ok', **cal.get_schedule_item(args.kind,args.id))
        elif args.action == 'lookup':
            result = cal.lookup_schedule_request(args.request_id)
        else:
            raw = base64.b64decode(args.request_base64, validate=True).decode('utf-8') if args.request_base64 else sys.stdin.read()
            result = cal.apply_schedule_request(json.loads(raw))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return 0 if result['status'] != 'not_found' else 4
    except ConflictError as e:
        result = dict(status='rejected', reason=str(e));code=3
    except (DomainError, ValueError, TypeError, UnicodeError) as e:
        unknown = str(e).startswith('Calendar database')
        result = dict(status='unknown' if unknown else 'rejected', reason=str(e));code=5 if unknown else 2
    except (OSError, sqlite3.Error):
        result = dict(status='unknown', reason='storage_unavailable');code=5
    print(json.dumps(result, ensure_ascii=False), flush=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
