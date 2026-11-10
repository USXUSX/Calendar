"""Explicit additive travel Todo URL migration (#275); existing DB only."""
import argparse
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.init_calendar_db import extend_travel_todos

def migrate(database):
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=rw',uri=True) as c:
        c.execute('BEGIN IMMEDIATE')
        if c.execute('SELECT version FROM schema_meta').fetchone() != (3,):
            raise ValueError('CAL v3 required')
        extend_travel_todos(c)

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('database',type=Path)
    migrate(p.parse_args().database)
