#!/usr/bin/env python3
"""Publish lightweight travel/item lookup indexes; fetch current data from Mac."""
import sys
sys.dont_write_bytecode = True
import argparse
import fcntl
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import subprocess
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain import CalendarDomain
from Sources.calendar_domain.trip_index import CONFIG

REPOSITORY = 'USXUSX/Calendar'
BRANCH = 'chat-index'
INDEX_PATH = 'trip-index.json'
DATA_PREFIX = 'item-index/'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def build_files(cal):
    files, travels, by_date = {}, [], {}
    # Read index metadata from one CAL state, including direct overrides.
    with cal._command() as c:
        c.execute('BEGIN IMMEDIATE')
        cal._trip_write_state.connection = c
        try:
            for travel in cal.list_travel():
                tid = travel['id']
                travels.append({k: travel[k] for k in ('id', 'title', 'dateRange', 'has_itinerary')})
                if not travel['has_itinerary']:
                    continue
                if cal._journal_path(tid).exists():
                    raise ValueError('pending Trip adoption; defer index publication')
                trip = cal.get_effective_trip(tid)
                names = {p['id']: p['name'] for p in trip['places']}
                days = []
                for day in sorted(trip['days'], key=lambda d: d['date']):
                    items = []
                    for item in day['scheduleItems']:
                        items.append(dict(source_type='scheduleItem', source_item_id=item['id'],
                                          start=(item.get('time') or {}).get('start'), title=item['action']))
                    for item in trip['transports']:
                        if item['dayId'] != day['id']:
                            continue
                        origin = names.get(item.get('fromPlaceId'), item.get('fromPlaceId') or '未定')
                        destination = names.get(item.get('toPlaceId'), item.get('toPlaceId') or '未定')
                        items.append(dict(source_type='transport', source_item_id=item['id'],
                                          start=(item.get('time') or {}).get('start'),
                                          title=item['mode'] + ': ' + origin + '→' + destination))
                    days.append(dict(date=day['date'], items=items))
                    by_date.setdefault(day['date'], []).append(dict(trip_id=tid, items=items))
                files[DATA_PREFIX + 'by-trip/' + tid + '.json'] = dict(
                    schema='cal-item-index-v1', trip_id=tid, days=days)
        finally:
            cal._trip_write_state.connection = None
    files[INDEX_PATH] = dict(schema='cal-trip-index-v1', travels=sorted(travels, key=lambda t: t['id']))
    for day_date, trips in by_date.items():
        files[DATA_PREFIX + 'by-date/' + day_date + '.json'] = dict(
            schema='cal-item-index-v1', date=day_date, trips=sorted(trips, key=lambda t: t['trip_id']))
    return files


def build_index(cal):
    return build_files(cal)[INDEX_PATH]


def github(gh, method, endpoint, body=None):
    command = [gh, 'api', '--method', method, endpoint]
    if body is not None:
        command.extend(['--input', '-'])
    result = subprocess.run(command, input=canonical(body) if body is not None else None,
                            text=True, capture_output=True, timeout=45)
    if result.returncode:
        raise RuntimeError('github_delivery_failed')
    return json.loads(result.stdout)


def blob_sha(content):
    raw = content.encode('utf-8')
    return hashlib.sha1(('blob ' + str(len(raw)) + '\0').encode() + raw).hexdigest()


def publish_files(gh, files):
    """Update lookup indexes and remove obsolete index files in one Git commit."""
    endpoint = 'repos/' + REPOSITORY + '/git/'
    ref = github(gh, 'GET', endpoint + 'ref/heads/' + BRANCH)
    parent = ref['object']['sha']
    commit = github(gh, 'GET', endpoint + 'commits/' + parent)
    tree_sha = commit['tree']['sha']
    tree = github(gh, 'GET', endpoint + 'trees/' + tree_sha + '?recursive=1')
    if tree.get('truncated'):
        raise RuntimeError('github_tree_incomplete')
    old = {i['path']: i['sha'] for i in tree['tree']
           if i['type'] == 'blob' and (i['path'] == INDEX_PATH or i['path'].startswith(DATA_PREFIX))}
    edits = []
    for path, content in sorted(files.items()):
        if old.get(path) != blob_sha(content):
            edits.append(dict(path=path, mode='100644', type='blob', content=content))
    for path in sorted(old.keys() - files.keys()):
        edits.append(dict(path=path, mode='100644', type='blob', sha=None))
    if not edits:
        return dict(status='unchanged', commit_sha=parent)
    tree = github(gh, 'POST', endpoint + 'trees', dict(base_tree=tree_sha, tree=edits))
    commit = github(gh, 'POST', endpoint + 'commits', dict(
        message='Update CAL travel and item lookup indexes', tree=tree['sha'], parents=[parent]))
    # Do not overwrite a concurrent branch update.
    github(gh, 'PATCH', endpoint + 'refs/heads/' + BRANCH, dict(sha=commit['sha'], force=False))
    return dict(status='published', commit_sha=commit['sha'])


def write_state(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(canonical(value) + '\n', encoding='utf-8')
    temporary.replace(path)


def publish(database, root):
    root = Path(root)
    folder = root / 'settings'
    config = json.loads((folder / CONFIG).read_text(encoding='utf-8'))
    if Path(config['database']).resolve() != Path(database).resolve():
        raise ValueError('database_mismatch')
    state_path = folder / 'trip-index-publication-state.json'
    with (folder / 'trip-index-publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            values = build_files(CalendarDomain(database, root, chat_root=root / 'chat-unused'))
            files = {path: canonical(value) + '\n' for path, value in values.items()}
            digest = hashlib.sha256(canonical(files).encode('utf-8')).hexdigest()
            try:
                state = json.loads(state_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                state = {}
            if state.get('status') == 'published' and state.get('content_hash') == digest:
                return dict(status='unchanged')
            result = publish_files(config['gh'], files)
            write_state(state_path, dict(status='published', content_hash=digest,
                                         commit_sha=result['commit_sha'],
                                         checked_at=datetime.now(timezone.utc).isoformat()))
            return dict(result, count=len(values[INDEX_PATH]['travels']), files=len(files))
        except Exception:
            write_state(state_path, dict(status='failed', checked_at=datetime.now(timezone.utc).isoformat()))
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--local-root', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = publish(args.database, args.local_root)
    except Exception:
        print(json.dumps(dict(status='failed', reason='index_publication_failed')))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
