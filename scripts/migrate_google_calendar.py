"""Add Google delivery state to CAL v3; back up the existing DB before running."""
import argparse
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain.google_calendar import extend_google


def migrate(database):
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=rw',uri=True) as c:
        if c.execute('SELECT version FROM schema_meta').fetchone()!=(3,):raise ValueError('CAL v3 required')
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='schedule_series'").fetchone():raise ValueError('recurrence migration required')
        extend_google(c)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database',type=Path);migrate(p.parse_args().database)
