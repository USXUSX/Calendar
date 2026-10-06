#!/usr/bin/env python3
"""Initialize an empty SQLite database with the CAL v3 schema."""

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(REPO_ROOT))
SCHEMA_PATH = REPO_ROOT / "Schemas" / "calendar-v3.sql"


def extend_schedule(connection):
    if 'trip_id' not in {r[1] for r in connection.execute('PRAGMA table_info(events)')}:
        connection.execute('ALTER TABLE events ADD COLUMN trip_id TEXT REFERENCES trips(id)')
    if 'notes' not in {r[1] for r in connection.execute('PRAGMA table_info(todos)')}:
        connection.execute('ALTER TABLE todos ADD COLUMN notes TEXT')


def extend_schedule_receipts(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS schedule_receipts (request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, receipt_json TEXT NOT NULL)')


def extend_recurrence(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS schedule_series (id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('event','todo')), revision INTEGER NOT NULL, data_json TEXT NOT NULL)")


def extend_travel(connection):
    connection.execute("CREATE TABLE IF NOT EXISTS travel_basics (trip_id TEXT PRIMARY KEY REFERENCES trips(id), data_json TEXT NOT NULL, has_itinerary INTEGER NOT NULL DEFAULT 0)")
    for table in ('events', 'todos'):
        columns = {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}
        for name, declaration in [('category', "TEXT NOT NULL DEFAULT 'general'"), ('gmail_url', 'TEXT'), ('google_calendar_id','TEXT'), ('google_event_id','TEXT')]:
            if name not in columns:
                connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')


def initialize(database_path: Path) -> None:
    if database_path.exists() and database_path.stat().st_size != 0:
        raise FileExistsError(f"refusing to initialize non-empty file: {database_path}")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        if connection.execute("SELECT version FROM schema_meta").fetchone() != (3,):
            raise RuntimeError("schema version verification failed")
        extend_schedule(connection)
        extend_schedule_receipts(connection)
        extend_recurrence(connection)
        extend_travel(connection)
        from Sources.calendar_domain.google_calendar import extend_google
        extend_google(connection)
        connection.commit()
    except Exception:
        connection.close()
        if database_path.exists():
            database_path.unlink()
        raise
    else:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path, help="path to a new or empty SQLite file")
    args = parser.parse_args()
    initialize(args.database)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
