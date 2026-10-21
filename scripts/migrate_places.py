"""Explicit additive sightseeing-table migration; does not seed content or change castle visits."""
import argparse
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain.places import extend_places


def migrate(database):
    with sqlite3.connect(Path(database).resolve().as_uri()+'?mode=rw', uri=True) as c:
        c.execute('BEGIN IMMEDIATE')
        extend_places(c)
    return dict(status='ready')


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('database', type=Path)
    print(migrate(p.parse_args().database))
