#!/usr/bin/env python3
"""Initialize an empty SQLite database with the CAL v3 schema."""

import argparse
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "Schemas" / "calendar-v3.sql"


def extend_schedule(connection):
    if 'trip_id' not in {r[1] for r in connection.execute('PRAGMA table_info(events)')}:
        connection.execute('ALTER TABLE events ADD COLUMN trip_id TEXT REFERENCES trips(id)')
    if 'notes' not in {r[1] for r in connection.execute('PRAGMA table_info(todos)')}:
        connection.execute('ALTER TABLE todos ADD COLUMN notes TEXT')


def extend_schedule_receipts(connection):
    connection.execute('CREATE TABLE IF NOT EXISTS schedule_receipts (request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, receipt_json TEXT NOT NULL)')


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
