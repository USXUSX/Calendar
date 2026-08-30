import copy
import json
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
ACTION_PATH = "/days/0/scheduleItems/0/action"


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

    def rows(self, instruction_id):
        with sqlite3.connect(self.db_path) as connection:
            return connection.execute(
                "SELECT i.state, i.base_version, i.base_hash, r.state, t.version "
                "FROM ai_instructions i JOIN generation_requests r ON r.instruction_id = i.id "
                "JOIN trips t ON t.id = i.trip_id WHERE i.id = ?", (instruction_id,)
            ).fetchone()

    def claim(self, instruction_id="instruction-1", text="Change Trip"):
        self.domain.add_ai_instruction(instruction_id, TRIP_ID, text)
        claim = self.domain.claim_generation_request()
        self.assertEqual(claim["instruction_id"], instruction_id)
        return claim

    def submit(self, claim, patch):
        return self.domain.submit_json_patch(
            claim["request_id"], claim["instruction_id"], claim["trip_id"], patch,
            claim["base_version"], claim["base_hash"],
        )

    def test_instruction_enqueue_is_atomic_and_claim_records_semantic_base(self):
        created = self.domain.add_ai_instruction("instruction-1", TRIP_ID, "Use lunch")
        self.assertEqual((created["state"], created["request_state"]), ("pending", "queued"))
        claim = self.domain.claim_generation_request()
        self.assertEqual(set(claim), {"request_id", "instruction_id", "trip_id", "instruction", "base_version", "base_hash", "trip"})
        self.assertEqual((claim["base_version"], claim["trip"]["id"]), (1, TRIP_ID))
        self.assertEqual(len(claim["base_hash"]), 64)
        self.assertEqual(self.rows("instruction-1")[1:4], (1, claim["base_hash"], "processing"))
        with self.assertRaises(ValidationError):
            self.domain.add_ai_instruction("bad", "missing-trip", "No parent")
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM generation_requests WHERE id = 'bad'").fetchone()[0], 0)

    def test_same_trip_serial_and_different_trip_parallel(self):
        second = json.loads(self.original)
        second["id"] = "trip-two"
        (self.trip_root / "trips" / "trip-two.json").write_text(json.dumps(second, ensure_ascii=False), encoding="utf-8")
        self.domain.register_trip("trip-two")
        self.domain.add_ai_instruction("a", TRIP_ID, "First")
        self.domain.add_ai_instruction("b", TRIP_ID, "Second")
        self.domain.add_ai_instruction("c", "trip-two", "Parallel")
        first = self.domain.claim_generation_request()
        parallel = self.domain.claim_generation_request()
        self.assertEqual(first["instruction_id"], "a")
        self.assertEqual(parallel["instruction_id"], "c")
        self.assertIsNone(self.domain.claim_generation_request())
        self.submit(first, [{"op": "replace", "path": ACTION_PATH, "value": "First done"}])
        self.assertEqual(self.domain.claim_generation_request()["instruction_id"], "b")

    def test_single_multi_and_day_object_replace_succeed(self):
        claim = self.claim("single")
        result = self.submit(claim, [{"op": "replace", "path": ACTION_PATH, "value": "昼食"}])
        self.assertEqual((result["status"], result["version"]), ("adopted", 2))
        self.assertEqual(self.rows("single"), ("applied", 1, claim["base_hash"], "completed", 2))
        claim = self.claim("multi")
        self.submit(claim, [
            {"op": "replace", "path": ACTION_PATH, "value": "軽食"},
            {"op": "replace", "path": "/days/0/scheduleItems/0/summary", "value": "短い説明"},
            {"op": "add", "path": "/days/0/scheduleItems/0/details/-", "value": "一時メモ"},
            {"op": "remove", "path": "/days/0/scheduleItems/0/details/0"},
        ])
        claim = self.claim("day")
        day = copy.deepcopy(claim["trip"]["days"][0])
        day["title"] = "雨の日"
        self.submit(claim, [{"op": "replace", "path": "/days/0", "value": day}])
        self.assertEqual(json.loads(self.current_path.read_bytes())["days"][0]["title"], "雨の日")

    def test_invalid_patch_or_candidate_leaves_current_unchanged(self):
        claim = self.claim("invalid")
        before = self.current_path.read_bytes()
        for patch in (
            [{"op": "move", "path": ACTION_PATH, "value": "x"}],
            [{"op": "replace", "path": "/missing", "value": "x"}],
            [{"op": "remove", "path": "/id"}],
            [{"op": "replace", "path": "/transports/0/fromPlaceId", "value": "missing-place"}],
        ):
            with self.subTest(patch=patch):
                with self.assertRaises(ValidationError):
                    self.submit(claim, patch)
                self.assertEqual(self.current_path.read_bytes(), before)
        self.assertEqual((self.rows("invalid")[0], self.rows("invalid")[3]), ("pending", "processing"))

    def test_stale_version_or_hash_requeues_and_keeps_pending(self):
        claim = self.claim("stale")
        result = self.domain.submit_json_patch(
            claim["request_id"], claim["instruction_id"], TRIP_ID,
            [{"op": "replace", "path": ACTION_PATH, "value": "古い変更"}],
            claim["base_version"] + 1, claim["base_hash"],
        )
        self.assertEqual(result["status"], "stale")
        self.assertEqual((self.rows("stale")[0], self.rows("stale")[3]), ("pending", "queued"))
        self.assertEqual(self.current_path.read_bytes(), self.original)
        claim = self.domain.claim_generation_request()
        result = self.domain.submit_json_patch(
            claim["request_id"], claim["instruction_id"], TRIP_ID,
            [{"op": "replace", "path": ACTION_PATH, "value": "wrong hash"}],
            claim["base_version"], "0" * 64,
        )
        self.assertEqual(result["status"], "stale")
        self.assertEqual((self.rows("stale")[0], self.rows("stale")[3]), ("pending", "queued"))

    def test_active_override_survives_and_reference_break_is_rejected(self):
        self.domain.set_direct_override("override-1", TRIP_ID, ITEM_ID, "/action", "直接指定")
        self.domain.create_todo("todo-1", label="Keep", trip_id=TRIP_ID, trip_item_id=ITEM_ID)
        claim = self.claim("break")
        with self.assertRaises(ConflictError):
            self.submit(claim, [{"op": "remove", "path": "/days/0/scheduleItems/0"}])
        self.assertEqual(self.current_path.read_bytes(), self.original)
        self.domain.release_generation_request(claim["request_id"])
        claim = self.domain.claim_generation_request()
        self.submit(claim, [{"op": "replace", "path": ACTION_PATH, "value": "AI変更"}])
        self.assertEqual(self.domain.get_effective_trip(TRIP_ID)["days"][0]["scheduleItems"][0]["action"], "直接指定")
        self.assertTrue(self.domain.list_active_direct_overrides(TRIP_ID)[0]["active"])

    def test_current_switch_uses_complete_staged_json(self):
        claim = self.claim("atomic")
        observed = []
        original_replace = self.domain._replace_current
        def inspect_then_replace(staging_path, current_path):
            observed.extend([json.loads(current_path.read_bytes())["id"], json.loads(staging_path.read_bytes())["id"]])
            original_replace(staging_path, current_path)
        self.domain._replace_current = inspect_then_replace
        self.submit(claim, [{"op": "replace", "path": ACTION_PATH, "value": "完全"}])
        self.assertEqual(observed, [TRIP_ID, TRIP_ID])

    def test_replace_failure_keeps_current_and_request_uncompleted(self):
        claim = self.claim("replace-failure")
        def fail_replace(staging_path, current_path):
            raise ConflictError("simulated replace failure")
        self.domain._replace_current = fail_replace
        with self.assertRaises(ConflictError):
            self.submit(claim, [{"op": "replace", "path": ACTION_PATH, "value": "未採用"}])
        self.assertEqual(self.current_path.read_bytes(), self.original)
        self.assertEqual((self.rows("replace-failure")[0], self.rows("replace-failure")[3]), ("pending", "processing"))

    def test_recovery_finishes_request_after_replace_before_database_update(self):
        claim = self.claim("recover")
        def stop_after_replace():
            raise SystemExit("simulated stop")
        self.domain._after_candidate_replace = stop_after_replace
        with self.assertRaises(SystemExit):
            self.submit(claim, [{"op": "replace", "path": ACTION_PATH, "value": "復旧"}])
        recovered = CalendarDomain(self.db_path, self.trip_root).recover_trip_adoption(TRIP_ID)
        self.assertEqual((recovered["status"], recovered["version"]), ("adopted", 2))
        self.assertEqual((self.rows("recover")[0], self.rows("recover")[3]), ("applied", "completed"))

    def test_recovery_old_hash_requeues_and_unknown_hash_conflicts(self):
        claim = self.claim("old")
        candidate = self.domain._apply_json_patch(claim["trip"], [{"op": "replace", "path": ACTION_PATH, "value": "候補"}])
        _, payload = self.domain._validated_candidate(TRIP_ID, candidate)
        candidate_hash = self.domain._digest(payload)
        journal = {"version": 2, "trip_id": TRIP_ID, "request_id": claim["request_id"], "instruction_id": claim["instruction_id"], "old_version": 1, "old_hash": claim["base_hash"], "candidate_hash": candidate_hash}
        self.domain._write_file(self.domain._staging_path(TRIP_ID, candidate_hash), payload)
        self.domain._write_journal(self.domain._journal_path(TRIP_ID), journal)
        self.assertEqual(self.domain.recover_trip_adoption(TRIP_ID)["status"], "not_adopted")
        self.assertEqual((self.rows("old")[0], self.rows("old")[3]), ("pending", "queued"))
        claim = self.domain.claim_generation_request()
        journal["old_version"] = claim["base_version"]
        journal["old_hash"] = claim["base_hash"]
        self.domain._write_file(self.domain._staging_path(TRIP_ID, candidate_hash), payload)
        self.domain._write_journal(self.domain._journal_path(TRIP_ID), journal)
        self.current_path.write_text('{"unexpected":true}', encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.domain.recover_trip_adoption(TRIP_ID)

    def test_direct_override_does_not_increment_trip_version(self):
        self.domain.set_direct_override("override-1", TRIP_ID, ITEM_ID, "/action", "直接指定")
        self.assertEqual(self.rows(self.claim("version")["instruction_id"])[4], 1)

    def test_uses_only_explicit_temporary_paths_not_calendar_local(self):
        self.claim("paths")
        self.assertTrue(str(self.db_path).startswith(self.temp.name))
        self.assertNotIn("Calendar_Local", str(self.db_path))


if __name__ == "__main__":
    unittest.main()
