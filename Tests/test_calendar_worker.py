import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from Sources.calendar_domain import CalendarDomain
from Sources.calendar_worker import GeneratorError, command_generator, run_once
from scripts.init_calendar_db import initialize

ROOT = Path(__file__).resolve().parents[1]
TRIP_ID = "trip-setouchi-2027"
ACTION_PATH = "/days/0/scheduleItems/0/action"


class CalendarWorkerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "calendar.sqlite3"
        self.trip_root = root / "trip-data"
        (self.trip_root / "trips").mkdir(parents=True)
        self.current_path = self.trip_root / "trips" / f"{TRIP_ID}.json"
        shutil.copyfile(ROOT / "Samples" / "synthetic-trip.json", self.current_path)
        initialize(self.db_path)
        self.domain = CalendarDomain(self.db_path, self.trip_root)
        self.domain.register_trip(TRIP_ID)
        self.original = self.current_path.read_bytes()

    def tearDown(self):
        self.temp.cleanup()

    def states(self, instruction_id):
        with sqlite3.connect(self.db_path) as connection:
            return connection.execute(
                "SELECT i.state, r.state, t.version FROM ai_instructions i "
                "JOIN generation_requests r ON r.instruction_id = i.id "
                "JOIN trips t ON t.id = i.trip_id WHERE i.id = ?", (instruction_id,)
            ).fetchone()

    def add(self, instruction_id="one"):
        self.domain.add_ai_instruction(instruction_id, TRIP_ID, "Change the first item")

    def test_no_request_is_successful_no_op(self):
        called = []
        self.assertEqual(run_once(self.domain, lambda payload: called.append(payload))["status"], "no-op")
        self.assertEqual(called, [])

    def test_single_and_multi_patch_receive_only_semantic_payload(self):
        self.add("single")
        seen = []
        result = run_once(self.domain, lambda payload: seen.append(payload) or [
            {"op": "replace", "path": ACTION_PATH, "value": "single"}
        ])
        self.assertEqual(result["status"], "adopted")
        self.assertEqual(set(seen[0]), {"request_id", "instruction_id", "trip_id", "instruction", "base_version", "base_hash", "trip"})
        self.assertFalse(any("path" in key or "table" in key for key in seen[0]))
        self.add("multi")
        result = run_once(self.domain, lambda payload: [
            {"op": "replace", "path": ACTION_PATH, "value": "multi"},
            {"op": "replace", "path": "/days/0/title", "value": "Changed"},
        ])
        self.assertEqual(result["status"], "adopted")
        self.assertEqual(self.states("multi"), ("applied", "completed", 3))

    def test_generator_failure_releases_request_and_keeps_current(self):
        for instruction_id, generator in (
            ("exception", lambda payload: (_ for _ in ()).throw(RuntimeError("failed"))),
            ("invalid-json", command_generator(["python3", "-c", "print('not json')"], 2)),
            ("non-zero", command_generator(["python3", "-c", "raise SystemExit(4)"], 2)),
        ):
            with self.subTest(instruction_id=instruction_id):
                self.add(instruction_id)
                result = run_once(self.domain, generator)
                self.assertEqual(result["status"], "generator_failed")
                self.assertEqual(self.states(instruction_id)[:2], ("pending", "queued"))
                self.assertEqual(self.current_path.read_bytes(), self.original)
                self.domain.cancel_ai_instruction(instruction_id)

    def test_invalid_patch_stops_retry_and_keeps_instruction_pending(self):
        self.add("invalid")
        result = run_once(self.domain, lambda payload: {"not": "a patch"})
        self.assertEqual(result["status"], "review_required")
        self.assertEqual(self.states("invalid"), ("pending", "cancelled", 1))
        self.assertEqual(self.current_path.read_bytes(), self.original)

    def test_stale_submit_requeues_without_changing_current(self):
        self.add("stale")
        def make_stale(payload):
            with sqlite3.connect(self.db_path) as connection:
                connection.execute("UPDATE trips SET version = version + 1 WHERE id = ?", (TRIP_ID,))
            return [{"op": "replace", "path": ACTION_PATH, "value": "stale"}]
        result = run_once(self.domain, make_stale)
        self.assertEqual(result["status"], "stale")
        self.assertEqual(self.states("stale"), ("pending", "queued", 2))
        self.assertEqual(self.current_path.read_bytes(), self.original)

    def test_same_trip_remains_serial_through_worker(self):
        self.add("first")
        self.add("second")
        observed = []
        run_once(self.domain, lambda payload: observed.append(payload["instruction_id"]) or [
            {"op": "replace", "path": ACTION_PATH, "value": payload["instruction_id"]}
        ])
        self.assertEqual(observed, ["first"])
        self.assertEqual(self.states("second")[1], "queued")

    def test_worker_recovers_interrupted_adoption_before_claim(self):
        self.add("recover")
        claim = self.domain.claim_generation_request()
        def stop_after_replace():
            raise SystemExit("simulated stop")
        self.domain._after_candidate_replace = stop_after_replace
        with self.assertRaises(SystemExit):
            self.domain.submit_json_patch(
                claim["request_id"], claim["instruction_id"], claim["trip_id"],
                [{"op": "replace", "path": ACTION_PATH, "value": "recovered"}],
                claim["base_version"], claim["base_hash"],
            )
        result = run_once(CalendarDomain(self.db_path, self.trip_root), lambda payload: [])
        self.assertEqual(result["status"], "no-op")
        self.assertEqual(result["recovered"][0]["status"], "adopted")
        self.assertEqual(self.states("recover"), ("applied", "completed", 2))


if __name__ == "__main__":
    unittest.main()
