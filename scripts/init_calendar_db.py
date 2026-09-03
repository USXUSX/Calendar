#!/usr/bin/env python3
"""Initialize an empty SQLite database with the CAL v3 schema."""

import argparse
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "Schemas" / "calendar-v3.sql"


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
