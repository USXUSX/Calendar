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
    sub.add_parser('google-status')
    sub.add_parser('google-retry')
    sub.add_parser('google-reconcile')
    sub.add_parser('trips')
    series=sub.add_parser('series');series.add_argument('--id')
    trip = sub.add_parser('trip-get');trip.add_argument('--id', required=True)
    sub.add_parser('trip-plan')
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
            if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_series'").fetchone() is None:
                raise ValueError('recurrence_migration_required')
        cal = CalendarDomain(args.database, args.local_root, chat_root=args.local_root/'chat-unused')
        if args.action == 'google-status':
            result = cal.google_status()
        elif args.action in ('google-retry','google-reconcile'):
            result = cal.sync_google(reconcile=args.action=='google-reconcile')
        elif args.action == 'doctor':
            result = dict(status='ready', protocol='cal-schedule-v1', receipt_storage='CAL SQLite', time_zone='Asia/Tokyo')
        elif args.action == 'series':
            if args.id:
                result=dict(status='ok',series=cal.get_series(args.id))
            else:
                with cal._read() as c:
                    identities=[r[0] for r in c.execute('SELECT id FROM schedule_series')]
                result=dict(status='ok',series=[cal.get_series(i) for i in identities])
        elif args.action == 'trips':
            result = dict(status='ok', trips=cal.list_trips())
        elif args.action == 'trip-get':
            result = dict(status='ok', **cal.get_trip_command_context(args.id))
        elif args.action == 'trip-plan':
            value = json.load(sys.stdin)
            if not isinstance(value,dict) or not isinstance(value.get('trip'),dict):
                raise ValueError('trip_required')
            cal._validated_candidate(value['trip'].get('id'),value['trip'])
            result = dict(status='ok', location_plan=cal.prepare_import_locations(value['trip'], existing_trip_id=value.get('existing_trip_id')))
        elif args.action == 'read':
            result = dict(status='ok', **cal.read_schedule(args.start,args.end,include_completed=True,include_trips=False))
        elif args.action == 'get':
            result = dict(status='ok', **cal.get_schedule_item(args.kind,args.id))
        elif args.action == 'lookup':
            result = cal.lookup_chat_request(args.request_id)
        else:
            raw = base64.b64decode(args.request_base64, validate=True).decode('utf-8') if args.request_base64 else sys.stdin.read()
            request = json.loads(raw)
            try:
                if isinstance(request,dict) and 'scope' in request:
                    result=cal.apply_recurrence_request(request)
                else:
                    result = cal.apply_trip_request(request) if isinstance(request,dict) and request.get('kind') == 'trip' else cal.apply_schedule_request(request)
            except Exception:
                trip_value = request.get('trip') if isinstance(request,dict) else None
                trip_id = trip_value.get('id') if isinstance(trip_value,dict) else None
                pending = False
                if isinstance(trip_id,str):
                    try:
                        pending = cal._journal_path(trip_id).exists()
                    except DomainError:
                        pass
                if isinstance(request,dict) and request.get('kind') == 'trip' and pending:
                    result = dict(status='unknown', reason='pending_trip_adoption',request_id=request.get('request_id'))
                    print(json.dumps(result),flush=True)
                    return 5
                raise
        if args.action in ('lookup','doctor'):
            result['google'] = cal.google_status()
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
