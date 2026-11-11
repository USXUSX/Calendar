#!/usr/bin/env python3
"""Synthetic #279 measurement only. Explicit temporary DB/Trip/Chat roots; no network."""
import sys
sys.dont_write_bytecode = True
import argparse
import copy
import json
from pathlib import Path
import statistics
import subprocess
import tempfile
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from Sources.calendar_domain import CalendarDomain
from scripts.init_calendar_db import initialize

# Each call uses a fresh interpreter, just like the RDC CLI. The socket guard
# fails closed even if an external connection is accidentally introduced.
LAUNCH = '''import socket,sys
from unittest.mock import patch
from scripts.cal_schedule import main
with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden in synthetic measurement')):
    raise SystemExit(main(sys.argv[1:]))
'''


def invoke(db, root, action, value=None):
    start = time.monotonic_ns()
    completed = subprocess.run([sys.executable, '-B', '-c', LAUNCH, '--database', str(db),
                                '--local-root', str(root), '--timing', *action], cwd=ROOT,
                               input=json.dumps(value), text=True, capture_output=True, check=True)
    wall_ms = (time.monotonic_ns()-start)/1_000_000
    # Responses/receipts are used for contract checks, never saved to diagnostics.
    return json.loads(completed.stdout), json.loads(completed.stderr), wall_ms


def scaled_trip(sample, large=False):
    trip = copy.deepcopy(sample)
    trip['id'] = 'synthetic-timing'
    if large:
        for index in range(63):
            point = copy.deepcopy(sample['places'][index % len(sample['places'])])
            point['id'] = 'synthetic-place-'+str(index)
            trip['places'].append(point)
        day = trip['days'][0]
        for index in range(100):
            item = copy.deepcopy(day['scheduleItems'][0])
            item.update(id='synthetic-item-'+str(index), order=index+10)
            day['scheduleItems'].append(item)
    return trip


def measure(repeats=3):
    sample = json.loads((ROOT/'Samples/hokkaido-4days-candidate.json').read_text())
    measurements = []
    for case in ('small-create', 'small-save', 'large-create'):
        for iteration in range(repeats+1):
            with tempfile.TemporaryDirectory(prefix='cal-279-') as tmp:
                root = Path(tmp)
                db = root/'db/calendar.sqlite3'
                initialize(db)
                cal = CalendarDomain(db, root, chat_root=root/'chat-unused')
                trip = scaled_trip(sample, case == 'large-create')
                plan = cal.prepare_import_locations(trip)
                request = dict(request_id=str(uuid4()), kind='trip', action='create', trip=trip,
                               coordinate_results={p['place_id']: None for p in plan if p['location'] is None and not p.get('skip_search')})
                if case == 'small-save':
                    cal.apply_trip_request(request)
                    context = cal.get_trip_command_context(trip['id'])
                    request.update(request_id=str(uuid4()), action='save', expected_revision=context['revision'], trip=context['trip'])
                    request['trip']['title'] = 'Synthetic title change'
                response, timing, wall = invoke(db, root, ['apply'], request)
                assert response['resolution'] == 'new'
                measurements.append(dict(case=case, phase='first' if iteration == 0 else 'warm',
                                         bytes=len(json.dumps(request, ensure_ascii=False).encode()), timing=timing, process_wall_ms=wall))
                receipt = response['receipt']
                response, timing, wall = invoke(db, root, ['apply'], request)
                assert response['resolution'] == 'replayed' and response['receipt'] == receipt
                measurements.append(dict(case=case+'-replay', phase='first' if iteration == 0 else 'warm',
                                         timing=timing, process_wall_ms=wall))
                for action in (['lookup', '--request-id', request['request_id']], ['trip-get', '--id', trip['id']]):
                    response, timing, wall = invoke(db, root, action)
                    if action[0] == 'lookup':
                        assert response['receipt'] == receipt
                    else:
                        assert response['revision'] == receipt['revision']
                    measurements.append(dict(case=case+'-'+action[0], phase='first' if iteration == 0 else 'warm',
                                             timing=timing, process_wall_ms=wall))
    return measurements


def summary(measurements):
    rows = []
    for case in dict.fromkeys(m['case'] for m in measurements):
        selected = [m for m in measurements if m['case'] == case]
        warm = [m['timing']['total_ms'] for m in selected if m['phase'] == 'warm']
        walls = [m['process_wall_ms'] for m in selected if m['phase'] == 'warm']
        rows.append(dict(case=case, first_ms=selected[0]['timing']['total_ms'], warm_median_ms=statistics.median(warm),
                         warm_range_ms=[min(warm), max(warm)], process_wall_median_ms=statistics.median(walls),
                         counts=selected[0]['timing']['counts'], bytes=selected[0].get('bytes')))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path, help='JSON report outside any Git checkout')
    args = parser.parse_args()
    target = args.output.resolve()
    if any((p/'.git').exists() for p in target.parents):
        parser.error('output must be outside any Git checkout')
    measurements = measure()
    report = dict(protocol='cal-synthetic-timing-v1', python=sys.version.split()[0],
                  repeats=3, network='blocked', external_services='unconfigured', rdc_round_trip=False,
                  first='first observed per scenario; no OS cache purge; fresh interpreter on every call',
                  warm='three subsequent runs with fresh temporary DB/Trip/Chat roots',
                  total='CAL after argument parsing; excludes interpreter/import startup and diagnostic emission',
                  process_wall='local subprocess including imports, test network guard, output capture and exit; not RDC/AI time',
                  summary=summary(measurements), measurements=measurements)
    target.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(output=str(target), summary=report['summary']), indent=2))


if __name__ == '__main__':
    main()
