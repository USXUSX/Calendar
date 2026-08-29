import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("init_calendar_db", REPO_ROOT / "scripts/init_calendar_db.py")
assert SPEC and SPEC.loader
INIT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INIT_MODULE)
TS = "2026-08-30T12:34:56Z"


class CalendarSchemaV1Tests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "calendar.sqlite3"
        INIT_MODULE.initialize(self.database_path)
        self.connection = sqlite3.connect(self.database_path)
        self.connection.execute("PRAGMA foreign_keys = ON")

    def tearDown(self):
        self.connection.close()
        self.temporary_directory.cleanup()

    def insert_trip(self):
        self.connection.execute("INSERT INTO trips VALUES ('trip-1', 'owner', ?, ?)", (TS, TS))

    def test_schema_is_reproducible_and_versioned(self):
        tables = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")}
        self.assertEqual(tables, {"schema_meta", "trips", "events", "todos", "ai_instructions", "direct_overrides"})
        self.assertEqual(self.connection.execute("SELECT version FROM schema_meta").fetchone(), (1,))

    def test_foreign_keys_reject_unknown_parents(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO ai_instructions (id, trip_id, instruction, created_at, updated_at) VALUES ('i1', 'missing', 'change', ?, ?)", (TS, TS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO todos (id, label, event_id, visibility, created_at, updated_at) VALUES ('t1', 'prepare', 'missing', 'owner', ?, ?)", (TS, TS))

    def test_enums_and_trip_item_link_are_constrained(self):
        self.insert_trip()
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO events (id, title, start_date, visibility, created_at, updated_at) VALUES ('e1', 'Meeting', '2026-08-30', 'public', ?, ?)", (TS, TS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO todos (id, label, trip_item_id, visibility, created_at, updated_at) VALUES ('t1', 'Prepare', 'item-1', 'owner', ?, ?)", (TS, TS))

    def test_date_time_and_timestamp_formats_are_constrained(self):
        for start_date, start_time in (("2026-02-30", None), ("2026-08-30", "24:00")):
            with self.subTest(start_date=start_date, start_time=start_time):
                with self.assertRaises(sqlite3.IntegrityError):
                    self.connection.execute(
                        "INSERT INTO events (id, title, start_date, start_time, visibility, created_at, updated_at) VALUES (?, 'Meeting', ?, ?, 'owner', ?, ?)",
                        (f"event-{start_date}-{start_time}", start_date, start_time, TS, TS),
                    )
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO trips VALUES ('trip-bad-time', 'owner', '2026-08-30 12:34:56', ?)", (TS,))

    def test_ai_instruction_lifecycle_values(self):
        self.insert_trip()
        self.connection.execute("INSERT INTO ai_instructions (id, trip_id, instruction, created_at, updated_at) VALUES ('i1', 'trip-1', 'reduce travel', ?, ?)", (TS, TS))
        self.assertEqual(self.connection.execute("SELECT state FROM ai_instructions WHERE id = 'i1'").fetchone(), ("pending",))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("UPDATE ai_instructions SET state = 'failed' WHERE id = 'i1'")

    def test_direct_override_has_one_current_row_per_target(self):
        self.insert_trip()
        self.connection.execute("INSERT INTO direct_overrides (id, trip_id, source_item_id, field_path, value_json, created_at, updated_at) VALUES ('o1', 'trip-1', 'item-1', '/title', '\"First\"', ?, ?)", (TS, TS))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("INSERT INTO direct_overrides (id, trip_id, source_item_id, field_path, value_json, active, created_at, updated_at) VALUES ('o2', 'trip-1', 'item-1', '/title', '\"Second\"', 0, ?, ?)", (TS, TS))
        self.connection.execute("UPDATE direct_overrides SET value_json = '\"Second\"', active = 0, updated_at = ? WHERE id = 'o1'", (TS,))
        self.assertEqual(self.connection.execute("SELECT value_json, active FROM direct_overrides WHERE id = 'o1'").fetchone(), ('"Second"', 0))
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute("UPDATE direct_overrides SET value_json = 'not-json' WHERE id = 'o1'")

    def test_initializer_refuses_non_empty_database(self):
        with self.assertRaises(FileExistsError):
            INIT_MODULE.initialize(self.database_path)


if __name__ == "__main__":
    unittest.main()
