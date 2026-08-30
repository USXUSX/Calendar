import copy
import json
import os
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize


ROOT = Path(__file__).resolve().parents[1]
TRIP_ID = "trip-setouchi-2027"
ITEM_ID = "schedule-port-breakfast"


class CandidateAdoptionTests(unittest.TestCase):
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

    def candidate(self, action="候補として昼食をとる"):
        value = json.loads(self.original)
        value["days"][0]["scheduleItems"][0]["action"] = action
        return value

    def state(self, instruction_id):
        with sqlite3.connect(self.db_path) as connection:
            return connection.execute(
                "SELECT state FROM ai_instructions WHERE id = ?", (instruction_id,)
            ).fetchone()[0]

    def test_valid_candidate_applies_only_explicit_pending_instructions(self):
        self.domain.add_ai_instruction("used-1", TRIP_ID, "Use lunch")
        self.domain.add_ai_instruction("later-1", TRIP_ID, "Added after generation")
        result = self.domain.adopt_trip_candidate(TRIP_ID, self.candidate(), ["used-1"])
        self.assertEqual(result["status"], "adopted")
        self.assertEqual(self.state("used-1"), "applied")
        self.assertEqual(self.state("later-1"), "pending")
        self.assertEqual(json.loads(self.current_path.read_bytes())["days"][0]["scheduleItems"][0]["action"], "候補として昼食をとる")
        self.assertFalse((self.trip_root / ".adoption" / f"{TRIP_ID}.json").exists())

    def test_invalid_candidate_and_id_mismatch_leave_current_unchanged(self):
        invalid = self.candidate()
        invalid["transports"][0]["fromPlaceId"] = "missing-place"
        with self.assertRaises(ValidationError):
            self.domain.adopt_trip_candidate(TRIP_ID, invalid, [])
        mismatch = self.candidate()
        mismatch["id"] = "another-trip"
        with self.assertRaises(ValidationError):
            self.domain.adopt_trip_candidate(TRIP_ID, mismatch, [])
        self.assertEqual(self.current_path.read_bytes(), self.original)

    def test_non_pending_instruction_is_rejected(self):
        self.domain.add_ai_instruction("cancelled-1", TRIP_ID, "No longer wanted")
        self.domain.cancel_ai_instruction("cancelled-1")
        with self.assertRaises(ConflictError):
            self.domain.adopt_trip_candidate(TRIP_ID, self.candidate(), ["cancelled-1"])
        self.assertEqual(self.current_path.read_bytes(), self.original)

        self.domain.add_ai_instruction("applied-1", TRIP_ID, "Already used")
        self.domain.adopt_trip_candidate(TRIP_ID, self.candidate("first adoption"), ["applied-1"])
        adopted = self.current_path.read_bytes()
        with self.assertRaises(ConflictError):
            self.domain.adopt_trip_candidate(TRIP_ID, self.candidate("second adoption"), ["applied-1"])
        self.assertEqual(self.current_path.read_bytes(), adopted)

    def test_replace_failure_keeps_current_and_instruction_pending(self):
        self.domain.add_ai_instruction("used-1", TRIP_ID, "Use lunch")

        def fail_replace(staging_path, current_path):
            raise ConflictError("simulated replace failure")

        self.domain._replace_current = fail_replace
        with self.assertRaises(ConflictError):
            self.domain.adopt_trip_candidate(TRIP_ID, self.candidate(), ["used-1"])
        self.assertEqual(self.current_path.read_bytes(), self.original)
        self.assertEqual(self.state("used-1"), "pending")
        self.assertFalse((self.trip_root / ".adoption" / f"{TRIP_ID}.json").exists())

    def test_active_override_survives_and_effective_trip_is_valid(self):
        self.domain.add_ai_instruction("used-1", TRIP_ID, "Use lunch")
        self.domain.set_direct_override("override-1", TRIP_ID, ITEM_ID, "/action", "確定した直接指定")
        self.domain.adopt_trip_candidate(TRIP_ID, self.candidate(), ["used-1"])
        overrides = self.domain.list_active_direct_overrides(TRIP_ID)
        self.assertEqual([item["id"] for item in overrides], ["override-1"])
        effective = self.domain.get_effective_trip(TRIP_ID)
        self.assertEqual(effective["days"][0]["scheduleItems"][0]["action"], "確定した直接指定")

    def test_candidate_cannot_remove_override_target(self):
        self.domain.set_direct_override("override-1", TRIP_ID, ITEM_ID, "/action", "確定した直接指定")
        candidate = self.candidate()
        candidate["days"][0]["scheduleItems"] = []
        with self.assertRaises(ConflictError):
            self.domain.adopt_trip_candidate(TRIP_ID, candidate, [])
        self.assertEqual(self.current_path.read_bytes(), self.original)
        self.assertTrue(self.domain.list_active_direct_overrides(TRIP_ID)[0]["active"])

    def test_candidate_cannot_break_todo_trip_item_reference(self):
        self.domain.create_todo("todo-1", label="Keep breakfast", trip_id=TRIP_ID, trip_item_id=ITEM_ID)
        candidate = self.candidate()
        candidate["days"][0]["scheduleItems"] = []
        with self.assertRaises(ConflictError):
            self.domain.adopt_trip_candidate(TRIP_ID, candidate, [])
        self.assertEqual(self.current_path.read_bytes(), self.original)
        self.assertEqual(self.domain.get_todo("todo-1")["trip_item_id"], ITEM_ID)

    def test_current_switch_uses_complete_staged_json(self):
        candidate = self.candidate()
        observed = []

        def inspect_then_replace(staging_path, current_path):
            observed.append(json.loads(current_path.read_bytes())["id"])
            observed.append(json.loads(staging_path.read_bytes())["id"])
            os.replace(staging_path, current_path)

        self.domain._replace_current = inspect_then_replace
        self.domain.adopt_trip_candidate(TRIP_ID, candidate, [])
        self.assertEqual(observed, [TRIP_ID, TRIP_ID])
        self.assertEqual(json.loads(self.current_path.read_bytes())["id"], TRIP_ID)

    def test_recovery_finishes_instruction_update_after_atomic_replace(self):
        self.domain.add_ai_instruction("used-1", TRIP_ID, "Use lunch")

        def stop_after_replace():
            raise SystemExit("simulated process stop")

        self.domain._after_candidate_replace = stop_after_replace
        with self.assertRaises(SystemExit):
            self.domain.adopt_trip_candidate(TRIP_ID, self.candidate(), ["used-1"])
        self.assertNotEqual(self.current_path.read_bytes(), self.original)
        self.assertEqual(self.state("used-1"), "pending")

        recovered = CalendarDomain(self.db_path, self.trip_root).recover_trip_adoption(TRIP_ID)
        self.assertEqual((recovered["status"], recovered["recovered"]), ("adopted", True))
        self.assertEqual(self.state("used-1"), "applied")
        self.assertIsNone(CalendarDomain(self.db_path, self.trip_root).recover_trip_adoption(TRIP_ID))

    def test_recovery_keeps_pending_when_current_is_still_old(self):
        self.domain.add_ai_instruction("used-1", TRIP_ID, "Use lunch")
        candidate_value, candidate_payload = self.domain._validated_candidate(TRIP_ID, self.candidate())
        del candidate_value
        journal = {
            "version": 1,
            "trip_id": TRIP_ID,
            "candidate_digest": self.domain._digest(candidate_payload),
            "old_current_digest": self.domain._digest(self.original),
            "instruction_ids": ["used-1"],
        }
        self.domain._write_file(self.domain._staging_path(TRIP_ID, journal["candidate_digest"]), candidate_payload)
        self.domain._write_journal(self.domain._journal_path(TRIP_ID), journal)
        recovered = self.domain.recover_trip_adoption(TRIP_ID)
        self.assertEqual(recovered["status"], "not_adopted")
        self.assertEqual(self.state("used-1"), "pending")
        self.assertEqual(self.current_path.read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
