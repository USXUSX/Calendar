import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path

from Sources.calendar_domain import (
    CalendarDomain, ConflictError, NotFoundError, ValidationError,
    build_local_ai_update_request,
)
from scripts.init_calendar_db import initialize


ROOT = Path(__file__).resolve().parents[1]


class CalendarDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.db_path = root / "calendar.sqlite3"
        self.trip_root = root / "trip-data"
        (self.trip_root / "trips").mkdir(parents=True)
        self.trip_path = self.trip_root / "trips" / "trip-setouchi-2027.json"
        shutil.copyfile(ROOT / "Samples" / "synthetic-trip.json", self.trip_path)
        initialize(self.db_path)
        self.domain = CalendarDomain(self.db_path, self.trip_root)
        self.domain.register_trip("trip-setouchi-2027", "participants")

    def tearDown(self):
        self.temp.cleanup()

    def test_unified_events_preserve_source_and_do_not_copy_trip_events(self):
        self.domain.create_event("schedule-port-breakfast", title="Ordinary collision", start_date="2027-05-14")
        events = self.domain.list_events("2027-05-14", "2027-05-14")
        ordinary = next(item for item in events if item.source_kind == "ordinary")
        trip = next(item for item in events if item.source_item_id == "schedule-port-breakfast")
        transport = next(item for item in events if item.source_item_id == "transport-ferry")
        self.assertEqual(ordinary.identity, "ordinary:schedule-port-breakfast")
        self.assertEqual(trip.identity, "trip:trip-setouchi-2027:scheduleItem:schedule-port-breakfast")
        self.assertNotEqual(ordinary.identity, trip.identity)
        self.assertEqual(trip.visibility, "participants")
        self.assertIn("青凪港", transport.title)
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0], 1)

    def test_effective_trip_applies_active_override_without_writing_json(self):
        original = self.trip_path.read_bytes()
        self.domain.set_direct_override(
            "override-1", "trip-setouchi-2027", "schedule-port-breakfast", "/action", "港で昼食をとる"
        )
        effective = self.domain.get_effective_trip("trip-setouchi-2027")
        self.assertEqual(effective["days"][0]["scheduleItems"][0]["action"], "港で昼食をとる")
        self.assertEqual(self.trip_path.read_bytes(), original)
        self.domain.clear_direct_override("override-1")
        restored = self.domain.get_effective_trip("trip-setouchi-2027")
        self.assertEqual(restored["days"][0]["scheduleItems"][0]["action"], "港で朝食をとる")

    def test_trip_detail_view_derives_phase_1_model_without_new_authority(self):
        original = self.trip_path.read_bytes()
        view = self.domain.get_trip_detail_view(
            "trip-setouchi-2027",
            candidate_judgments={"schedule-island-art": {"place-art-museum": "ok"}},
            weather_by_day={"day-2027-05-14": {"summary": "晴れ", "updated_at": "synthetic"}},
        )
        first_day = view["days"][0]
        entries = {item["source_item_id"]: item for item in first_day["entries"]}
        breakfast = entries["schedule-port-breakfast"]
        art = entries["schedule-island-art"]
        dinner = entries["schedule-dinner"]
        ferry = entries["transport-ferry"]
        self.assertEqual([item["order"] for item in first_day["entries"]], [10, 20, 30, 40, 50])
        self.assertEqual(breakfast["status"], "confirmed")
        self.assertEqual(art["status"], "tentative")
        self.assertTrue(art["has_candidates"])
        self.assertEqual(art["candidates"][0]["judgment"], "ok")
        self.assertEqual(dinner["time"]["label"], "未定")
        self.assertEqual(ferry["category_icon_key"], "transport")
        self.assertTrue(ferry["important_comments"])
        self.assertEqual(first_day["weather"]["summary"], "晴れ")
        self.assertEqual(breakfast["direct_edit_paths"]["title"], "/action")
        self.assertEqual(self.trip_path.read_bytes(), original)

    def test_trip_detail_temporary_judgment_is_not_adopted_selection(self):
        view = self.domain.get_trip_detail_view(
            "trip-setouchi-2027",
            candidate_judgments={"schedule-island-art": {"place-art-museum": "ng"}},
        )
        art = next(
            item for item in view["days"][0]["entries"]
            if item["source_item_id"] == "schedule-island-art"
        )
        self.assertEqual(art["candidates"][0]["judgment"], "ng")
        self.assertFalse(art["candidates"][0]["selected_in_base"])
        effective = self.domain.get_effective_trip("trip-setouchi-2027")
        source = effective["days"][0]["scheduleItems"][1]
        self.assertEqual(source["placeSelection"]["selection"], [])
        with self.assertRaises(ValidationError):
            self.domain.get_trip_detail_view(
                "trip-setouchi-2027",
                candidate_judgments={"schedule-island-art": {"place-art-museum": "maybe"}},
            )

    def test_local_ai_update_request_is_target_scoped_and_not_queued(self):
        effective = self.domain.get_effective_trip("trip-setouchi-2027")
        request = build_local_ai_update_request(
            effective, "scheduleItem", "schedule-port-breakfast", "開始を9時にする"
        )
        self.assertEqual(request["kind"], "trip_item_local_update")
        self.assertEqual(request["result_contract"], "semantic_field_changes")
        self.assertEqual(request["current_target"]["time"]["start"], "08:30")
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM generation_requests").fetchone()[0], 0)

    def test_override_rejects_missing_target_path_and_invalid_value(self):
        cases = [
            ("missing", "/action", "value"),
            ("schedule-port-breakfast", "/missing", "value"),
            ("schedule-port-breakfast", "/time/start", "99:00"),
        ]
        for source_id, path, value in cases:
            with self.subTest(source_id=source_id, path=path):
                with self.assertRaises(ValidationError):
                    self.domain.set_direct_override("bad", "trip-setouchi-2027", source_id, path, value)
        self.assertEqual(self.domain.list_active_direct_overrides("trip-setouchi-2027"), [])

    def test_direct_edit_is_atomic_and_status_is_independent(self):
        original = self.trip_path.read_bytes()
        result = self.domain.edit_trip_item(
            "edit-1", "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
            {"status": "confirmed", "time_mode": "fixed", "start": "19:00",
             "end": None, "title": "夕食を予約店でとる", "normal_comment": "19時集合"},
        )
        dinner = result["trip"]["days"][0]["scheduleItems"][2]
        self.assertEqual((dinner["status"], dinner["time"]["mode"], dinner["action"]),
                         ("confirmed", "fixed", "夕食を予約店でとる"))
        self.assertEqual(self.trip_path.read_bytes(), original)
        before = self.domain.list_active_direct_overrides("trip-setouchi-2027")
        with self.assertRaises(ValidationError):
            self.domain.edit_trip_item(
                "edit-2", "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
                {"status": "tentative", "time_mode": "range", "start": "20:00", "end": None},
            )
        self.assertEqual(self.domain.list_active_direct_overrides("trip-setouchi-2027"), before)

    def test_transport_direct_edit_uses_same_status_and_time_contract(self):
        result = self.domain.edit_trip_item(
            "edit-transport", "trip-setouchi-2027", "transport", "transport-hotel-walk",
            {"status": "confirmed", "time_mode": "undecided", "start": None, "end": None},
        )
        transport = next(item for item in result["trip"]["transports"] if item["id"] == "transport-hotel-walk")
        self.assertEqual((transport["status"], transport["time"]["mode"]), ("confirmed", "undecided"))

    def test_working_trip_keeps_one_latest_state_and_does_not_change_authority(self):
        original = self.trip_path.read_bytes()
        first = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [{"source_item_id": "schedule-dinner", "disposition": "pending_delete"}],
            "temporary_items": [],
            "day_instructions": [],
        })
        self.assertFalse(first["stale"])
        self.assertEqual(self.domain.list_active_direct_overrides("trip-setouchi-2027"), [])
        updated = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [],
            "temporary_items": [{"id": "working-dinner", "title": "夕食候補"}],
            "day_instructions": [],
        })
        self.assertEqual(updated["state"], {
            "item_changes": [],
            "temporary_items": [{"id": "working-dinner", "title": "夕食候補"}],
            "day_instructions": [],
        })
        self.assertEqual(updated["base_effective_revision"], first["base_effective_revision"])
        self.assertEqual(self.trip_path.read_bytes(), original)
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM working_trips").fetchone()[0], 1)

    def test_stale_working_trip_remains_readable_and_editable_but_blocks_confirmation(self):
        initial = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [], "temporary_items": [], "day_instructions": [],
        })
        self.domain.edit_trip_item(
            "edit-after-working", "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
            {"normal_comment": "確定側の後続変更"},
        )
        stale = self.domain.get_working_trip("trip-setouchi-2027")
        self.assertTrue(stale["stale"])
        self.assertNotEqual(stale["base_effective_revision"], stale["current_effective_revision"])
        edited = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [],
            "temporary_items": [],
            "day_instructions": [{"day_id": "day-1", "instruction": "午後を雨想定に組み換え"}],
        })
        self.assertTrue(edited["stale"])
        self.assertEqual(edited["base_effective_revision"], initial["base_effective_revision"])
        with self.assertRaisesRegex(ConflictError, "stale"):
            self.domain.require_current_working_trip("trip-setouchi-2027")
        self.domain.clear_working_trip("trip-setouchi-2027")
        with self.assertRaises(NotFoundError):
            self.domain.get_working_trip("trip-setouchi-2027")

    def test_working_trip_requires_the_minimal_top_level_envelope(self):
        with self.assertRaises(ValidationError):
            self.domain.save_working_trip("trip-setouchi-2027", [])
        with self.assertRaises(ValidationError):
            self.domain.save_working_trip("trip-setouchi-2027", {
                "item_changes": [], "temporary_items": [],
            })
        with self.assertRaises(ValidationError):
            self.domain.save_working_trip("trip-setouchi-2027", {
                "item_changes": [], "temporary_items": [], "day_instructions": [], "extra": [],
            })
        with self.assertRaises(ValidationError):
            self.domain.save_working_trip("trip-setouchi-2027", {
                "item_changes": {}, "temporary_items": [], "day_instructions": [],
            })
        with self.assertRaises(ValidationError):
            self.domain.save_working_trip("trip-setouchi-2027", {
                "item_changes": ["strict-shape-not-defined"],
                "temporary_items": [], "day_instructions": [],
            })
        with self.assertRaises(ValidationError):
            self.domain.save_working_trip("trip-setouchi-2027", {
                "item_changes": [], "temporary_items": [],
                "day_instructions": [{"value": float("nan")}],
            })

    def test_ordinary_event_crud_and_source_boundary(self):
        created = self.domain.create_event("event-1", title="Meeting", start_date="2027-05-15")
        self.assertEqual(created["title"], "Meeting")
        self.assertEqual(self.domain.update_event("event-1", title="Updated")["title"], "Updated")
        with self.assertRaises(ValidationError):
            self.domain.update_event("event-1", start_time="24:00")
        self.assertEqual(self.domain.get_event("event-1")["title"], "Updated")
        with self.assertRaises(ConflictError):
            self.domain.update_event("trip:trip-setouchi-2027:scheduleItem:schedule-port-breakfast", title="Wrong")
        self.domain.delete_event("event-1")
        with self.assertRaises(NotFoundError):
            self.domain.get_event("event-1")

    def test_todo_crud_completion_and_constraints(self):
        todo = self.domain.create_todo("todo-1", label="Reserve", trip_id="trip-setouchi-2027")
        self.assertIsNone(todo["completed_at"])
        self.assertEqual(self.domain.update_todo("todo-1", label="Reserve ferry")["label"], "Reserve ferry")
        self.assertIsNotNone(self.domain.set_todo_completed("todo-1")["completed_at"])
        self.assertEqual(len(self.domain.list_todos(trip_id="trip-setouchi-2027", completed=True)), 1)
        with self.assertRaises(ValidationError):
            self.domain.create_todo("bad", label="Bad", trip_id="trip-setouchi-2027", event_id="missing")
        self.domain.delete_todo("todo-1")

    def test_ai_instruction_pending_and_cancel_only(self):
        instruction = self.domain.add_ai_instruction("instruction-1", "trip-setouchi-2027", "Reduce travel")
        self.assertEqual(instruction["state"], "pending")
        self.assertEqual(instruction["request_state"], "queued")
        self.assertEqual(len(self.domain.list_pending_ai_instructions("trip-setouchi-2027")), 1)
        self.assertEqual(self.domain.cancel_ai_instruction("instruction-1")["state"], "cancelled")
        with sqlite3.connect(self.db_path) as connection:
            self.assertEqual(
                connection.execute("SELECT state FROM generation_requests WHERE id = 'instruction-1'").fetchone()[0],
                "cancelled",
            )
        self.assertEqual(self.domain.list_pending_ai_instructions("trip-setouchi-2027"), [])
        with self.assertRaises(ConflictError):
            self.domain.cancel_ai_instruction("instruction-1")

    def test_trip_registration_validates_file_id_and_duplicate(self):
        with self.assertRaises(ConflictError):
            self.domain.register_trip("trip-setouchi-2027")
        with self.assertRaises(NotFoundError):
            self.domain.register_trip("missing-trip")
        bad_path = self.trip_root / "trips" / "different-id.json"
        shutil.copyfile(self.trip_path, bad_path)
        with self.assertRaises(ValidationError):
            self.domain.register_trip("different-id")

    def test_requires_explicit_paths_and_uses_only_temporary_storage(self):
        with self.assertRaises(ValidationError):
            CalendarDomain(None, self.trip_root)
        self.assertTrue(str(self.db_path).startswith(self.temp.name))
        self.assertTrue(str(self.trip_root).startswith(self.temp.name))

    def test_failed_command_rolls_back_without_partial_update(self):
        self.domain.create_event("event-rollback", title="Stable", start_date="2027-05-15", start_time="09:00")
        with self.assertRaises(ValidationError):
            self.domain.update_event("event-rollback", title="Changed", start_time="25:00")
        event = self.domain.get_event("event-rollback")
        self.assertEqual((event["title"], event["start_time"]), ("Stable", "09:00"))


if __name__ == "__main__":
    unittest.main()
