#!/usr/bin/env python3
"""Publish only approved travel routing metadata on Calendar's chat-index branch."""
import sys
sys.dont_write_bytecode = True
import argparse
import base64
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


def build_index(cal):
    """Do not publish participants, bookings, locations, instructions or revisions."""
    travels = [dict(id=t['id'], title=t['title'], dateRange=t['dateRange'],
                    has_itinerary=t['has_itinerary']) for t in cal.list_travel()]
    return dict(schema='cal-trip-index-v1', travels=sorted(travels, key=lambda t: t['id']))


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def github(gh, method, endpoint, body=None):
    command = [gh, 'api', '--method', method, endpoint]
    if body is not None:
        command.extend(['--input', '-'])
    result = subprocess.run(command, input=canonical(body) if body is not None else None,
                            text=True, capture_output=True, timeout=45)
    if result.returncode:
        # A missing file is expected only for the explicitly initialized branch.
        if method == 'GET' and 'HTTP 404' in result.stderr:
            return None
        raise RuntimeError('github_delivery_failed')
    return json.loads(result.stdout)


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
    # Serialize detached workers; each rereads current CAL after acquiring the lock.
    with (folder / 'trip-index-publication.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            index = build_index(CalendarDomain(database, root, chat_root=root / 'chat-unused'))
            digest = hashlib.sha256(canonical(index).encode('utf-8')).hexdigest()
            try:
                state = json.loads(state_path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                state = {}
            if state.get('status') == 'published' and state.get('content_hash') == digest:
                return dict(status='unchanged')
            gh = config['gh']
            endpoint = f'repos/{REPOSITORY}/contents/{INDEX_PATH}'
            previous = github(gh, 'GET', endpoint + '?ref=' + BRANCH)
            if previous is not None:
                remote = json.loads(base64.b64decode(previous['content']))
                if remote == index:
                    write_state(state_path, dict(status='published', content_hash=digest,
                                                 checked_at=datetime.now(timezone.utc).isoformat()))
                    return dict(status='unchanged')
            body = dict(message='Update public travel routing index', branch=BRANCH,
                        content=base64.b64encode((canonical(index) + '\n').encode('utf-8')).decode('ascii'))
            if previous is not None:
                body['sha'] = previous['sha']
            github(gh, 'PUT', endpoint, body)
            write_state(state_path, dict(status='published', content_hash=digest,
                                         published_at=datetime.now(timezone.utc).isoformat()))
            return dict(status='published', count=len(index['travels']))
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
