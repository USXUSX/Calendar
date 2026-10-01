"""Add schedule fields to an existing CAL v3 database, preserving all rows."""
import argparse
import sqlite3
from pathlib import Path
if __package__:
    from .init_calendar_db import extend_schedule
else:
    from init_calendar_db import extend_schedule


def migrate(database):
    connection = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=rw', uri=True)
    try:
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('BEGIN IMMEDIATE')
        if connection.execute('SELECT version FROM schema_meta').fetchone() != (3,):
            raise ValueError('CAL v3 database required')
        extend_schedule(connection)
        connection.commit()
    finally:
        connection.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    migrate(parser.parse_args().database)
