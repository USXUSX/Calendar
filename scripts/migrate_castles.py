"""Explicit additive migration from the adopted Frame #368/#371 source, after SQLite backup."""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain.castles import extend_castles, validate_record
from Sources.calendar_domain.schedule_chat import encoded


def source_rows(path):
    text = Path(path).read_text()
    # Parse only the JSON literal; never execute the supplied JavaScript.
    rows, _ = json.JSONDecoder().raw_decode(text.split('const castles=', 1)[1].lstrip())
    return rows


def migrate(database, source):
    rows = source_rows(source)
    if len(rows) != 100 or {r['id'] for r in rows} != set(range(1, 101)):
        raise ValueError('expected_adopted_100_castles')
    prepared = []
    for r in rows:
        master = dict(name=r['n'], prefecture=r['p'], city=r['city'], longitude=r['x'], latitude=r['y'])
        if any(not isinstance(master[k], str) or not master[k] for k in ('name','prefecture','city')):
            raise ValueError('invalid_master')
        if not (-180 <= master['longitude'] <= 180 and -90 <= master['latitude'] <= 90):
            raise ValueError('invalid_coordinates')
        visit = datetime.strptime(r['visitDate'], '%Y/%m/%d').date().isoformat() if r['visitDate'] else None
        record = dict(visited=bool(visit), visit_date=visit, comment='')
        validate_record(record)
        prepared.append((r['id'], encoded(master), encoded(record), 1))
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=rw', uri=True) as c:
        c.execute('BEGIN IMMEDIATE')
        extend_castles(c)
        existing = list(c.execute('SELECT id,master_json FROM castles ORDER BY id'))
        if existing:
            expected = sorted((r[0], r[1]) for r in prepared)
            if existing != expected:
                raise ValueError('existing_master_conflict')
            return dict(status='unchanged', count=len(existing))
        c.executemany('INSERT INTO castles VALUES (?,?,?,?)', prepared)
    return dict(status='migrated', count=100, visited=sum(json.loads(r[2])['visited'] for r in prepared))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database', type=Path); p.add_argument('source', type=Path)
    a = p.parse_args()
    print(json.dumps(migrate(a.database, a.source)))
