"""Add only the recurrence table to an existing CAL v3 schedule database."""
import argparse
import sqlite3
from pathlib import Path
if __package__:
    from .init_calendar_db import extend_recurrence
else:
    from init_calendar_db import extend_recurrence


def migrate(database):
    c = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=rw', uri=True)
    try:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT version FROM schema_meta').fetchone() != (3,):
            raise ValueError('CAL v3 required')
        for name, field in [('events', 'trip_id'), ('todos', 'notes')]:
            if field not in {r[1] for r in c.execute(f'PRAGMA table_info({name})')}:
                raise ValueError('schedule migration required first')
        if not c.execute("SELECT name FROM sqlite_master WHERE name='schedule_receipts'").fetchone():
            raise ValueError('receipt migration required first')
        extend_recurrence(c)
        c.commit()
    finally:
        c.close()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('database', type=Path)
    migrate(p.parse_args().database)
