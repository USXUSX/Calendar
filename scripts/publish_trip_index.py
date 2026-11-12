#!/usr/bin/env python3
"""Publish CAL read copies for Chat preparation; Mac remains authoritative."""
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
from Sources.calendar_domain import CalendarDomain, ConflictError
from Sources.calendar_domain.trip_index import CONFIG

REPOSITORY = 'USXUSX/Calendar'
BRANCH = 'chat-index'
INDEX_PATH = 'trip-index.json'
DATA_PREFIX = 'chat-data/'


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def build_files(cal):
    """Read one locked CAL state; never export DB files, settings or credentials."""
    files, travels = {}, []
    # The reservation also protects formal Trip files from CAL writers while read.
    with cal._command() as c:
        c.execute('BEGIN IMMEDIATE')
        cal._trip_write_state.connection = c
        try:
            for row in c.execute('SELECT id FROM trips ORDER BY id').fetchall():
                tid = row['id']
                if cal._journal_path(tid).exists():
                    raise ConflictError('pending Trip adoption; defer publication')
                basic = cal._travel_basic(c, tid)
                path = DATA_PREFIX + 'trips/' + tid
                summary = dict(id=tid, title=basic['title'], dateRange=basic['dateRange'],
                               has_itinerary=basic['has_itinerary'], travel_path=path + '/travel.json')
                files[summary['travel_path']] = dict(status='ok', travel=basic)
                if basic['has_itinerary']:
                    context = cal._trip_command_context(c, tid)
                    summary.update(items_path=path + '/items.json', context_path=path + '/context.json')
                    files[summary['context_path']] = dict(status='ok', **context)
                    trip = context['trip']
                    items = []
                    for day in trip['days']:
                        for item in day['scheduleItems']:
                            items.append(dict(source_type='scheduleItem', source_item_id=item['id'],
                                              day_id=day['id'], date=day['date'], item=item))
                    dates = {day['id']: day['date'] for day in trip['days']}
                    for item in trip['transports']:
                        items.append(dict(source_type='transport', source_item_id=item['id'],
                                          day_id=item['dayId'], date=dates[item['dayId']], item=item))
                    files[summary['items_path']] = dict(
                        status='ok', context_scope='items', trip_id=tid,
                        trip_summary={k: trip[k] for k in ('id', 'title', 'dateRange')},
                        items=items, places=[dict(id=p['id'], name=p['name']) for p in trip['places']],
                        instructions=context['instructions'], revision=context['revision'])
                travels.append(summary)
            ordinary = []
            for kind, table in [('event', 'events'), ('todo', 'todos')]:
                for row in c.execute('SELECT id FROM ' + table + ' ORDER BY id').fetchall():
                    ordinary.append(cal.get_schedule_item(kind, row['id']))
            series = [cal.get_series(row['id']) for row in c.execute(
                'SELECT id FROM schedule_series ORDER BY id').fetchall()]
            schedule_path = DATA_PREFIX + 'schedule.json'
            files[schedule_path] = dict(status='ok', items=ordinary, series=series)
        finally:
            cal._trip_write_state.connection = None
    files[INDEX_PATH] = dict(schema='cal-chat-copy-v2', travels=travels, schedule_path=schedule_path)
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
    """One non-forced ref update makes all copies visible in the same Git commit."""
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
        message='Update CAL read copies for Chat', tree=tree['sha'], parents=[parent]))
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
