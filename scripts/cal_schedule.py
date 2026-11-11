#!/usr/bin/env python3
"""CAL schedule CLI for the existing RDC connection. One JSON response per invocation."""
import sys
sys.dont_write_bytecode = True
from contextlib import nullcontext
from uuid import UUID
import argparse
import base64
import json
import sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain import CalendarDomain, DomainError, ConflictError
from scripts.trip_location_resolver import resolve_location_plan
from Sources.calendar_domain.timing import Timing, span, count, count_trip

DEFAULT_ROOT = Path('/Users/us/Tools/LocalData/Calendar_Local')


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--database', type=Path, default=DEFAULT_ROOT/'db/calendar.sqlite3', help='synthetic tests only: override the existing CAL database')
    p.add_argument('--local-root', type=Path, default=DEFAULT_ROOT, help='synthetic tests only: override the CAL local root')
    p.add_argument('--timing', action='store_true', help='emit invocation timing JSON to stderr')
    p.add_argument('--timing-file', type=Path, help='also append timing JSONL outside the source checkout')
    p.add_argument('--timing-group', type=lambda value: str(UUID(value)), help='optional UUID correlating separate invocations')
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('doctor')
    sub.add_parser('google-status')
    sub.add_parser('google-retry')
    sub.add_parser('google-reconcile')
    sub.add_parser('trips')
    sub.add_parser('travels')
    travel = sub.add_parser('travel-get');travel.add_argument('--id', required=True);travel.add_argument('--start');travel.add_argument('--end')
    series=sub.add_parser('series');series.add_argument('--id')
    trip = sub.add_parser('trip-get');trip.add_argument('--id', required=True)
    sub.add_parser('trip-plan')
    resolve = sub.add_parser('trip-resolve');resolve.add_argument('--map-config-url', default='http://127.0.0.1:8080/api/calendar/map-config')
    read = sub.add_parser('read');read.add_argument('--start', required=True);read.add_argument('--end', required=True)
    get = sub.add_parser('get');get.add_argument('--kind', choices=['event','todo'], required=True);get.add_argument('--id', required=True)
    lookup = sub.add_parser('lookup');lookup.add_argument('--request-id', required=True)
    sub.add_parser('trip-operation')
    apply = sub.add_parser('apply');apply.add_argument('--request-base64', help='UTF-8 JSON encoded as base64; otherwise read JSON from stdin')
    args = p.parse_args(argv)
    try:
        timing = Timing(args.action, args.timing_group) if args.timing or args.timing_file else None
    except Exception:
        timing = None
    result, code = dict(status='unknown'), 5
    try:
        with timing.activate() if timing else nullcontext():
            with span('command'):
                result, code = execute(args)
            with span('response_prepare'):
                output = json.dumps(result, ensure_ascii=False, sort_keys=True)
            with span('response_write'):
                print(output, flush=True)
        return code
    finally:
        if timing:
            timing.finish(result, code)
            timing.emit(sys.stderr, args.timing_file)



def execute(args):
    try:
        if not args.database.is_file():
            raise ValueError('database_unavailable')
        # Fail before calling CAL if the additive migration is missing. No implicit init/migration.
        with sqlite3.connect(args.database.resolve().as_uri()+'?mode=ro', uri=True) as c:
            if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_receipts'").fetchone() is None:
                raise ValueError('receipt_migration_required')
            if c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedule_series'").fetchone() is None:
                raise ValueError('recurrence_migration_required')
        with span('domain_init'):
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
        elif args.action == 'travels':
            result = dict(status='ok', travels=cal.list_travel())
        elif args.action == 'travel-get':
            result = dict(status='ok', **cal.get_travel(args.id,args.start,args.end))
        elif args.action == 'trips':
            result = dict(status='ok', trips=cal.list_trips())
        elif args.action == 'trip-get':
            result = dict(status='ok', **cal.get_trip_command_context(args.id))
            count_trip(result['trip'])
        elif args.action in ('trip-plan','trip-resolve'):
            with span('input'):
                value = json.load(sys.stdin)
            if not isinstance(value,dict) or not isinstance(value.get('trip'),dict):
                raise ValueError('trip_required')
            count_trip(value['trip'])
            cal._validated_candidate(value['trip'].get('id'),value['trip'])
            with span('location_plan'):
                plan = cal.prepare_import_locations(value['trip'], existing_trip_id=value.get('existing_trip_id'))
            if args.action == 'trip-plan':
                result = dict(status='ok', location_plan=plan)
            else:
                result = dict(status='ok', **resolve_location_plan(plan, args.map_config_url))
        elif args.action == 'read':
            result = dict(status='ok', **cal.read_schedule(args.start,args.end,include_completed=True,include_trips=False))
        elif args.action == 'get':
            result = dict(status='ok', **cal.get_schedule_item(args.kind,args.id))
        elif args.action == 'lookup':
            result = cal.lookup_chat_request(args.request_id)
        elif args.action == 'trip-operation':
            result = cal.apply_trip_operation(json.load(sys.stdin))
        else:
            with span('input'):
                raw = base64.b64decode(args.request_base64, validate=True).decode('utf-8') if args.request_base64 else sys.stdin.read()
                request = json.loads(raw)
            if isinstance(request, dict) and request.get('kind') == 'trip':
                count(create=int(request.get('action') == 'create'), save=int(request.get('action') == 'save'))
            try:
                if isinstance(request,dict) and 'scope' in request:
                    result=cal.apply_recurrence_request(request)
                else:
                    if isinstance(request,dict) and request.get('kind') == 'travel':
                        result = cal.apply_travel_request(request)
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
                    return result, 5
                raise
        if args.action in ('lookup','doctor'):
            result['google'] = cal.google_status()
        return result, 0 if result['status'] != 'not_found' else 4
    except ConflictError as e:
        result = dict(status='rejected', reason=str(e));code=3
    except (DomainError, ValueError, TypeError, UnicodeError) as e:
        unknown = str(e).startswith('Calendar database')
        result = dict(status='unknown' if unknown else 'rejected', reason=str(e));code=5 if unknown else 2
    except (OSError, sqlite3.Error):
        result = dict(status='unknown', reason='storage_unavailable');code=5
    return result, code


if __name__ == '__main__':
    raise SystemExit(main())
