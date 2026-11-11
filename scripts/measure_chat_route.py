#!/usr/bin/env python3
"""Isolated RDC route fixture for #281, not a normal Chat or AI benchmark."""
import sys
sys.dont_write_bytecode = True
import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch
from uuid import uuid4

SOURCE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE))
from scripts.init_calendar_db import initialize
from scripts.measure_chat_timing import scaled_trip, LAUNCH

CASES = ('small-save', 'small-create', 'large-create')
STEPS = ('acquire', 'draft', 'resolve', 'apply', 'lookup', 'reread', 'frame', 'replay', 'stale')


def load(path):
    return json.loads(path.read_text())


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False))


def invoke(root, group, command, value=None):
    start = time.monotonic_ns()
    completed = subprocess.run([sys.executable, '-B', '-c', LAUNCH, '--database', str(root/'db/calendar.sqlite3'),
                                '--local-root', str(root), '--timing', '--timing-group', group, *command],
                               cwd=SOURCE, input=json.dumps(value), text=True, capture_output=True)
    end = time.monotonic_ns()
    response, diagnostic = json.loads(completed.stdout), json.loads(completed.stderr)
    assert diagnostic['exit_code'] == completed.returncode
    return response, dict(process_start_ns=start, process_end_ns=end, process_wall_ms=(end-start)/1e6, cal=diagnostic)


def prepare(root):
    root.mkdir()  # Refuse existing roots; never reuse an operational DB.
    save(root/'fixture.json', dict(protocol='cal-route-fixture-v1', group=str(uuid4())))
    initialize(root/'db/calendar.sqlite3')
    sample = load(SOURCE/'Samples/hokkaido-4days-candidate.json')
    for case in CASES:
        work = root/case
        work.mkdir()
        trip = scaled_trip(sample, case == 'large-create')
        trip['id'] = 'synthetic-route-'+case
        for place in trip['places']:
            # Intentionally synthetic coordinates: no geocoding, no inferred real location.
            place['location'] = dict(latitude=43.0, longitude=141.0)
        save(work/'sample.json', trip)
        if case == 'small-save':
            response, _ = invoke(root, load(root/'fixture.json')['group'], ['apply'],
                                 dict(request_id=str(uuid4()), kind='trip', action='create', trip=trip, coordinate_results={}))
            assert response['status'] == 'committed'
    return dict(status='prepared', group=load(root/'fixture.json')['group'])


def frame_read(root, trip, revision, frame_source):
    # Existing Frame code, one ephemeral loopback server; no production process changes.
    sys.path.insert(0, str(frame_source))
    from frame_server.adapter import DemoTaskAdapter
    from frame_server.calendar import CalendarDomainAdapter
    from frame_server.server import FrameServer
    import urllib.request
    adapter = CalendarDomainAdapter(str(SOURCE), str(root/'db/calendar.sqlite3'), str(root), chat_root=root/'chat-unused')
    server = FrameServer(('127.0.0.1', 0), DemoTaskAdapter(), adapter)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    original = socket.socket.connect
    def loopback(sock, address):
        if address[0] != '127.0.0.1':
            raise AssertionError('external network forbidden')
        return original(sock, address)
    try:
        with patch.object(socket.socket, 'connect', loopback):
            start = time.monotonic_ns()
            with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/calendar/trips/{trip["id"]}/effective', timeout=5) as response:
                value = json.load(response)
                no_store = response.headers.get('Cache-Control') == 'no-store'
            end = time.monotonic_ns()
        assert value['revision'] == revision and value['title'] == trip['title'] and no_store
        # Revision hashes the effective Trip including the intended title and all data.
        return dict(http_ms=(end-start)/1e6, revision_match=True, title_match=True, cache_no_store=no_store)
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def step(root, case, name, frame_source=None):
    group = load(root/'fixture.json')['group']
    work = root/case
    trip = load(work/'sample.json')
    record = dict(protocol='cal-route-step-v1', group=group, case=case, step=name,
                  start_ns=time.monotonic_ns(), clock='process-local-python-monotonic-ns', python=sys.version.split()[0])
    if name == 'draft':
        start = time.monotonic_ns()
        request = dict(request_id=str(uuid4()), kind='trip', action='create', trip=trip, coordinate_results={})
        if case == 'small-save':
            context = load(work/'context.json')
            request.update(action='save', trip=context['trip'], expected_revision=context['revision'])
            request['trip']['title'] = 'Synthetic route title change'
        save(work/'request.json', request)
        record.update(scripted_draft_ms=(time.monotonic_ns()-start)/1e6,
                      input_bytes=len(json.dumps(request, ensure_ascii=False).encode()))
        # This is deterministic Mac fixture preparation, not Chat reasoning.
    elif name == 'frame':
        if frame_source is None:
            raise ValueError('explicit Frame source required')
        receipt = load(work/'receipt.json')
        record.update(frame_read(root, receipt['trip'], receipt['revision'], frame_source))
    else:
        value = None
        if name == 'acquire':
            command = ['trip-get', '--id', trip['id']] if case == 'small-save' else ['trips']
        elif name == 'resolve':
            request = load(work/'request.json')
            value = dict(trip=request['trip'])
            if case == 'small-save':
                value['existing_trip_id'] = trip['id']
            command = ['trip-resolve']
        elif name in ('apply', 'replay', 'stale'):
            value = load(work/'request.json')
            if name == 'apply':
                value['coordinate_results'] = load(work/'resolved.json')['coordinate_results']
                save(work/'request.json', value)
            elif name == 'stale':
                value.update(request_id=str(uuid4()), action='save', expected_revision={})
            command = ['apply']
        elif name == 'lookup':
            command = ['lookup', '--request-id', load(work/'request.json')['request_id']]
        else:
            command = ['trip-get', '--id', trip['id']]
        response, observation = invoke(root, group, command, value)
        record.update(observation)
        record['status'] = response['status']
        if name == 'stale':
            assert response['status'] == 'rejected' and response['reason'] == 'revision_conflict'
        else:
            assert response['status'] in ('ok', 'committed')
        if name == 'acquire' and case == 'small-save':
            save(work/'context.json', response)
        elif name == 'resolve':
            save(work/'resolved.json', response)
            record['coordinates'] = response['coordinates']
            assert response['coordinates']['attempted'] == 0
        elif name == 'apply':
            assert response['resolution'] == 'new'
            save(work/'receipt.json', response['receipt'])
        elif name in ('lookup', 'replay'):
            assert response['receipt'] == load(work/'receipt.json')
        elif name == 'reread':
            receipt = load(work/'receipt.json')
            assert response['trip'] == receipt['trip'] and response['revision'] == receipt['revision']
    record['end_ns'] = time.monotonic_ns()
    record['step_wall_ms'] = (record['end_ns']-record['start_ns'])/1e6
    # Only this allowlisted diagnostic is logged; fixture payloads stay separate.
    with (root/'route.jsonl').open('a') as handle:
        handle.write(json.dumps(record)+'\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    parser.add_argument('--frame-source', type=Path)
    parser.add_argument('action', choices=('prepare', *STEPS))
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    root = args.root.resolve()
    temporary_roots = (Path(tempfile.gettempdir()).resolve(), Path('/tmp').resolve())
    if not any(temporary in root.parents for temporary in temporary_roots):
        parser.error('fixture root must be a new directory under the system temporary directory')
    if args.action == 'prepare':
        value = prepare(root)
    else:
        if args.case is None:
            parser.error('--case required')
        assert load(root/'fixture.json')['protocol'] == 'cal-route-fixture-v1'
        value = step(root, args.case, args.action, args.frame_source)
    print(json.dumps(value), flush=True)


if __name__ == '__main__':
    main()
