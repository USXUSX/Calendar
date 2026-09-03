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

    def test_working_candidate_accepts_only_a_json_object_for_one_working_trip(self):
        original = self.trip_path.read_bytes()
        self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [], "temporary_items": [], "day_instructions": [],
        })
        candidate = json.loads(original)
        result = self.domain.adopt_working_trip_candidate("trip-setouchi-2027", candidate)
        self.assertEqual((result["trip_id"], result["status"]),
                         ("trip-setouchi-2027", "adopted"))
        self.assertEqual((result["version"], result["recovered"]), (2, False))
        candidate["title"] = "caller-side mutation"
        self.assertEqual(self.trip_path.read_bytes(), original)
        with self.assertRaises(NotFoundError):
            self.domain.get_working_trip("trip-setouchi-2027")

        for invalid in (self.trip_path, str(self.trip_path), [], {"value": float("nan")}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValidationError):
                    self.domain.adopt_working_trip_candidate("trip-setouchi-2027", invalid)

    def test_working_candidate_requires_an_existing_working_target(self):
        candidate = json.loads(self.trip_path.read_bytes())
        with self.assertRaises(NotFoundError):
            self.domain.adopt_working_trip_candidate("trip-setouchi-2027", candidate)

    def test_working_candidate_rejects_stale_without_changing_or_blocking_working(self):
        original = self.trip_path.read_bytes()
        initial = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [], "temporary_items": [],
            "day_instructions": [{"day_id": "day-2027-05-14", "instruction": "雨天想定"}],
        })
        self.domain.edit_trip_item(
            "edit-after-working-candidate", "trip-setouchi-2027", "scheduleItem",
            "schedule-dinner", {"normal_comment": "確定側の後続変更"},
        )
        candidate = json.loads(original)

        with self.assertRaisesRegex(ConflictError, "stale"):
            self.domain.adopt_working_trip_candidate("trip-setouchi-2027", candidate)

        self.assertEqual(self.trip_path.read_bytes(), original)
        working = self.domain.get_working_trip("trip-setouchi-2027")
        self.assertTrue(working["stale"])
        self.assertEqual(working["base_effective_revision"], initial["base_effective_revision"])
        self.assertEqual(
            self.domain.get_working_trip_detail_view("trip-setouchi-2027")["working"],
            {"present": True, "stale": True},
        )
        edited = self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "雨天想定を強める",
        )
        self.assertTrue(edited["stale"])
        exported = self.domain.export_working_trip_for_chat("trip-setouchi-2027")
        self.assertTrue(exported["working"]["stale"])

    def test_working_candidate_reuses_formal_validation_without_changing_state(self):
        self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [], "temporary_items": [], "day_instructions": [],
        })
        original_trip = self.trip_path.read_bytes()
        original_working = self.domain.get_working_trip("trip-setouchi-2027")
        valid = json.loads(original_trip)
        invalid_candidates = []

        wrong_id = json.loads(original_trip)
        wrong_id["id"] = "another-trip"
        invalid_candidates.append((wrong_id, ValidationError, "id does not match"))

        schema_invalid = json.loads(original_trip)
        del schema_invalid["title"]
        invalid_candidates.append((schema_invalid, ValidationError, "invalid"))

        semantic_invalid = json.loads(original_trip)
        semantic_invalid["transports"][0]["fromPlaceId"] = "missing-place"
        invalid_candidates.append((semantic_invalid, ValidationError, "unknown endpoint"))

        for candidate, error_type, message in invalid_candidates:
            with self.subTest(message=message):
                with self.assertRaisesRegex(error_type, message):
                    self.domain.adopt_working_trip_candidate(
                        "trip-setouchi-2027", candidate,
                    )
                self.assertEqual(self.trip_path.read_bytes(), original_trip)
                self.assertEqual(
                    self.domain.get_working_trip("trip-setouchi-2027"),
                    original_working,
                )

        result = self.domain.adopt_working_trip_candidate(
            "trip-setouchi-2027", valid,
        )
        self.assertEqual(result["status"], "adopted")
        self.assertEqual(self.trip_path.read_bytes(), original_trip)
        with self.assertRaises(NotFoundError):
            self.domain.get_working_trip("trip-setouchi-2027")

    def test_working_candidate_validates_active_overrides_and_todo_item_references(self):
        self.domain.set_direct_override(
            "override-1", "trip-setouchi-2027", "schedule-port-breakfast",
            "/time/start", "09:00",
        )
        self.domain.create_todo(
            "todo-1", label="Keep", trip_id="trip-setouchi-2027",
            trip_item_id="schedule-dinner",
        )
        self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [], "temporary_items": [], "day_instructions": [],
        })
        original_trip = self.trip_path.read_bytes()
        original_working = self.domain.get_working_trip("trip-setouchi-2027")

        invalid_effective = json.loads(original_trip)
        breakfast_time = invalid_effective["days"][0]["scheduleItems"][0]["time"]
        breakfast_time.update({"mode": "undecided", "start": None, "end": None})
        with self.assertRaisesRegex(ValidationError, "effective Trip is invalid"):
            self.domain.adopt_working_trip_candidate(
                "trip-setouchi-2027", invalid_effective,
            )

        missing_stable_item = json.loads(original_trip)
        missing_stable_item["days"][0]["scheduleItems"].pop(2)
        with self.assertRaisesRegex(ConflictError, "referenced by a Todo"):
            self.domain.adopt_working_trip_candidate(
                "trip-setouchi-2027", missing_stable_item,
            )

        missing_override_target = json.loads(original_trip)
        missing_override_target["days"][0]["scheduleItems"].pop(0)
        with self.assertRaisesRegex(ConflictError, "active Direct Override"):
            self.domain.adopt_working_trip_candidate(
                "trip-setouchi-2027", missing_override_target,
            )

        self.assertEqual(self.trip_path.read_bytes(), original_trip)
        self.assertEqual(
            self.domain.get_working_trip("trip-setouchi-2027"), original_working,
        )
        self.assertTrue(
            self.domain.list_active_direct_overrides("trip-setouchi-2027")[0]["active"]
        )

        valid = json.loads(original_trip)
        valid["title"] = "採用済み候補"
        result = self.domain.adopt_working_trip_candidate(
            "trip-setouchi-2027", valid,
        )
        self.assertEqual((result["status"], result["version"]), ("adopted", 2))
        self.assertEqual(json.loads(self.trip_path.read_bytes())["title"], "採用済み候補")
        self.assertEqual(
            self.domain.get_effective_trip("trip-setouchi-2027")["days"][0]
            ["scheduleItems"][0]["time"]["start"],
            "09:00",
        )
        self.assertTrue(
            self.domain.list_active_direct_overrides("trip-setouchi-2027")[0]["active"]
        )
        with self.assertRaises(NotFoundError):
            self.domain.get_working_trip("trip-setouchi-2027")

    def test_working_candidate_recovery_finishes_version_and_clear_after_replace(self):
        self.domain.set_direct_override(
            "override-recovery", "trip-setouchi-2027", "schedule-port-breakfast",
            "/summary", "維持するOverride",
        )
        self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [], "temporary_items": [], "day_instructions": [],
        })
        candidate = json.loads(self.trip_path.read_bytes())
        candidate["title"] = "中断後に採用"

        def stop_after_replace():
            raise SystemExit("simulated stop")

        self.domain._after_candidate_replace = stop_after_replace
        with self.assertRaises(SystemExit):
            self.domain.adopt_working_trip_candidate("trip-setouchi-2027", candidate)

        recovered = CalendarDomain(self.db_path, self.trip_root).recover_trip_adoption(
            "trip-setouchi-2027"
        )
        self.assertEqual((recovered["status"], recovered["version"], recovered["recovered"]),
                         ("adopted", 2, True))
        with self.assertRaises(NotFoundError):
            self.domain.get_working_trip("trip-setouchi-2027")
        self.assertTrue(self.domain.list_active_direct_overrides("trip-setouchi-2027")[0]["active"])

    def test_working_candidate_recovery_keeps_working_when_old_current_remains(self):
        original_working = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [], "temporary_items": [],
            "day_instructions": [{"day_id": "day-2027-05-14", "instruction": "維持"}],
        })
        candidate = json.loads(self.trip_path.read_bytes())
        candidate["title"] = "未採用候補"
        _, payload = self.domain._validated_candidate("trip-setouchi-2027", candidate)
        candidate_hash = self.domain._digest(payload)
        old_hash = self.domain._digest(self.trip_path.read_bytes())
        journal = {
            "version": 3, "kind": "working_trip", "trip_id": "trip-setouchi-2027",
            "request_id": None, "instruction_id": None, "old_version": 1,
            "old_hash": old_hash, "candidate_hash": candidate_hash,
        }
        self.domain._write_file(
            self.domain._staging_path("trip-setouchi-2027", candidate_hash), payload,
        )
        self.domain._write_journal(
            self.domain._journal_path("trip-setouchi-2027"), journal,
        )

        recovered = self.domain.recover_trip_adoption("trip-setouchi-2027")
        self.assertEqual((recovered["status"], recovered["version"]), ("not_adopted", 1))
        self.assertEqual(self.domain.get_working_trip("trip-setouchi-2027"), original_working)

    def test_working_item_change_upserts_and_preserves_other_envelope_regions(self):
        original = self.trip_path.read_bytes()
        seeded = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [],
            "temporary_items": [{"future": "step-3"}],
            "day_instructions": [{"future": "step-5"}],
        })
        changed = self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "changed",
            {"start": None, "title": "夕食候補を再検討"},
        )
        self.assertEqual(changed["state"]["item_changes"], [{
            "source_type": "scheduleItem", "source_item_id": "schedule-dinner",
            "disposition": "changed", "changes": {"start": None, "title": "夕食候補を再検討"},
        }])
        self.assertEqual(changed["state"]["temporary_items"], [{"future": "step-3"}])
        self.assertEqual(changed["state"]["day_instructions"], [{"future": "step-5"}])
        deleted = self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "pending_delete", {},
        )
        self.assertEqual(len(deleted["state"]["item_changes"]), 1)
        self.assertEqual(deleted["state"]["item_changes"][0]["disposition"], "pending_delete")
        self.assertEqual(deleted["base_effective_revision"], seeded["base_effective_revision"])
        self.assertEqual(self.domain.list_active_direct_overrides("trip-setouchi-2027"), [])
        self.assertEqual(self.trip_path.read_bytes(), original)
        cleared = self.domain.clear_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
        )
        self.assertEqual(cleared["state"]["item_changes"], [])

    def test_working_item_edit_keeps_direct_overrides_and_revision_current(self):
        overrides_before = self.domain.list_active_direct_overrides("trip-setouchi-2027")
        changed = self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "changed",
            {"title": "Working夕食", "status": "tentative"},
        )
        self.assertFalse(changed["stale"])
        self.assertEqual(
            self.domain.list_active_direct_overrides("trip-setouchi-2027"), overrides_before,
        )
        redisplayed = self.domain.get_working_trip_detail_view("trip-setouchi-2027")
        dinner = next(entry for day in redisplayed["days"] for entry in day["entries"]
                      if entry["source_item_id"] == "schedule-dinner")
        self.assertEqual((dinner["title"], dinner["status"], dinner["working_state"]),
                         ("Working夕食", "tentative", "changed"))
        deleted = self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "pending_delete", {},
        )
        self.assertFalse(deleted["stale"])
        redisplayed = self.domain.get_working_trip_detail_view("trip-setouchi-2027")
        dinner = next(entry for day in redisplayed["days"] for entry in day["entries"]
                      if entry["source_item_id"] == "schedule-dinner")
        self.assertEqual(dinner["working_state"], "pending_delete")
        self.domain.clear_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
        )
        redisplayed = self.domain.get_working_trip_detail_view("trip-setouchi-2027")
        dinner = next(entry for day in redisplayed["days"] for entry in day["entries"]
                      if entry["source_item_id"] == "schedule-dinner")
        self.assertNotIn("working_state", dinner)

    def test_working_item_change_validates_target_and_step_2_fields_without_formal_trip(self):
        self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "transport", "transport-ferry", "changed", {"start": None},
        )
        for source_type, source_item_id, disposition, changes in (
            ("place", "place-port", "changed", {"title": "x"}),
            ("transport", "schedule-dinner", "changed", {"start": "10:00"}),
            ("scheduleItem", "missing", "changed", {"title": "x"}),
            ("transport", "transport-ferry", "changed", {"title": "x"}),
            ("scheduleItem", "schedule-dinner", "normal", {}),
            ("scheduleItem", "schedule-dinner", "changed", {}),
        ):
            with self.subTest(source_type=source_type, source_item_id=source_item_id, disposition=disposition):
                with self.assertRaises(ValidationError):
                    self.domain.save_working_trip_item_change(
                        "trip-setouchi-2027", source_type, source_item_id, disposition, changes,
                    )

    def test_stale_existing_working_item_change_remains_editable(self):
        initial = self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "changed",
            {"title": "Working title"},
        )
        self.domain.edit_trip_item(
            "edit-after-working-item", "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
            {"normal_comment": "確定側の後続変更"},
        )
        edited = self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "pending_delete", {},
        )
        self.assertTrue(edited["stale"])
        self.assertEqual(edited["base_effective_revision"], initial["base_effective_revision"])

    def test_temporary_item_supports_manual_create_edit_and_clear(self):
        original = self.trip_path.read_bytes()
        created = self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-lunch", "day-2027-05-14", {}, {
                "anchor_source_type": "scheduleItem",
                "anchor_source_item_id": "schedule-port-breakfast", "edge": "after",
            },
        )
        self.assertEqual(created["state"]["temporary_items"], [{
            "temporary_id": "temporary-lunch", "day_id": "day-2027-05-14", "values": {},
            "position": {"anchor_source_type": "scheduleItem",
                         "anchor_source_item_id": "schedule-port-breakfast", "edge": "after"},
        }])
        edited = self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-lunch", "day-2027-05-14", {
                "title": "港で昼食", "status": "tentative", "start": "12:30",
                "end": None, "time_mode": "start_only", "normal_comment": "手入力",
                "place_name": "青凪港食堂",
            },
        )
        self.assertEqual(len(edited["state"]["temporary_items"]), 1)
        self.assertEqual(edited["state"]["temporary_items"][0]["values"]["title"], "港で昼食")
        self.assertEqual(edited["state"]["temporary_items"][0]["position"]["edge"], "after")
        self.assertEqual(edited["base_effective_revision"], created["base_effective_revision"])
        self.assertEqual(edited["state"]["item_changes"], [])
        self.assertEqual(edited["state"]["day_instructions"], [])
        self.assertEqual(self.domain.list_active_direct_overrides("trip-setouchi-2027"), [])
        self.assertEqual(self.trip_path.read_bytes(), original)
        cleared = self.domain.clear_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-lunch",
        )
        self.assertEqual(cleared["state"]["temporary_items"], [])

    def test_temporary_item_validates_identity_day_and_manual_fields(self):
        for temporary_id, day_id, values, error_type in (
            ("", "day-2027-05-14", {}, ValidationError),
            ("temporary-lunch", "missing-day", {}, ValidationError),
            ("schedule-dinner", "day-2027-05-14", {}, ConflictError),
            ("temporary-lunch", "day-2027-05-14", {"ai_instruction": "make lunch"}, ValidationError),
            ("temporary-lunch", "day-2027-05-14", {"insertion_position": "after:item"}, ValidationError),
            ("temporary-lunch", "day-2027-05-14", {"title": float("nan")}, ValidationError),
        ):
            with self.subTest(temporary_id=temporary_id, day_id=day_id):
                with self.assertRaises(error_type):
                    self.domain.save_working_trip_temporary_item(
                        "trip-setouchi-2027", temporary_id, day_id, values, {
                            "anchor_source_type": "scheduleItem",
                            "anchor_source_item_id": "schedule-port-breakfast", "edge": "after",
                        },
                    )
        self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-lunch", "day-2027-05-14", {"title": "Lunch"}, {
                "anchor_source_type": "transport", "anchor_source_item_id": "transport-ferry",
                "edge": "before",
            },
        )

    def test_temporary_item_requires_a_same_day_existing_item_position(self):
        base = ("trip-setouchi-2027", "temporary-lunch", "day-2027-05-14", {"title": "Lunch"})
        invalid_positions = (
            None,
            {"anchor_source_type": "scheduleItem", "anchor_source_item_id": "schedule-port-breakfast"},
            {"anchor_source_type": "temporaryItem", "anchor_source_item_id": "temporary-other", "edge": "after"},
            {"anchor_source_type": "scheduleItem", "anchor_source_item_id": "schedule-port-breakfast", "edge": "middle"},
            {"anchor_source_type": "transport", "anchor_source_item_id": "transport-local-train", "edge": "after"},
        )
        for position in invalid_positions:
            with self.subTest(position=position):
                with self.assertRaises(ValidationError):
                    self.domain.save_working_trip_temporary_item(*base, position)

    def test_stale_temporary_item_remains_manually_editable(self):
        initial = self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-lunch", "day-2027-05-14", {"title": "Lunch"}, {
                "anchor_source_type": "scheduleItem",
                "anchor_source_item_id": "schedule-port-breakfast", "edge": "after",
            },
        )
        self.domain.edit_trip_item(
            "edit-after-temporary", "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
            {"normal_comment": "確定側の後続変更"},
        )
        edited = self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-lunch", "day-2027-05-14", {"title": "Manual lunch"},
        )
        self.assertTrue(edited["stale"])
        self.assertEqual(edited["base_effective_revision"], initial["base_effective_revision"])

    def test_day_instruction_supports_register_edit_and_clear_without_applying(self):
        original = self.trip_path.read_bytes()
        seeded = self.domain.save_working_trip("trip-setouchi-2027", {
            "item_changes": [{"future": "step-2"}],
            "temporary_items": [{"future": "step-3"}],
            "day_instructions": [],
        })
        created = self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "  午後を雨想定に組み換える  ",
        )
        self.assertEqual(created["state"]["day_instructions"], [{
            "day_id": "day-2027-05-14", "instruction": "午後を雨想定に組み換える",
        }])
        edited = self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "移動を減らして屋内中心にする",
        )
        self.assertEqual(len(edited["state"]["day_instructions"]), 1)
        self.assertEqual(edited["state"]["day_instructions"][0]["instruction"], "移動を減らして屋内中心にする")
        self.assertEqual(edited["state"]["item_changes"], [{"future": "step-2"}])
        self.assertEqual(edited["state"]["temporary_items"], [{"future": "step-3"}])
        self.assertEqual(edited["base_effective_revision"], seeded["base_effective_revision"])
        self.assertEqual(self.domain.list_active_direct_overrides("trip-setouchi-2027"), [])
        self.assertEqual(self.trip_path.read_bytes(), original)
        cleared = self.domain.clear_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14",
        )
        self.assertEqual(cleared["state"]["day_instructions"], [])

    def test_day_instruction_validates_new_day_and_non_empty_text(self):
        for day_id, instruction in (("missing-day", "change"), ("day-2027-05-14", "  "), ("", "change")):
            with self.subTest(day_id=day_id, instruction=instruction):
                with self.assertRaises(ValidationError):
                    self.domain.save_working_trip_day_instruction(
                        "trip-setouchi-2027", day_id, instruction,
                    )

    def test_stale_day_instruction_remains_editable_and_clearable(self):
        initial = self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "雨天想定",
        )
        self.domain.edit_trip_item(
            "edit-after-day-instruction", "trip-setouchi-2027", "scheduleItem", "schedule-dinner",
            {"normal_comment": "確定側の後続変更"},
        )
        edited = self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "雨天想定を強める",
        )
        self.assertTrue(edited["stale"])
        self.assertEqual(edited["base_effective_revision"], initial["base_effective_revision"])
        cleared = self.domain.clear_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14",
        )
        self.assertEqual(cleared["state"]["day_instructions"], [])
        self.assertTrue(cleared["stale"])

    def test_working_trip_detail_composes_effective_then_all_working_display_states(self):
        original = self.trip_path.read_bytes()
        self.domain.edit_trip_item(
            "direct-before-working", "trip-setouchi-2027", "scheduleItem",
            "schedule-port-breakfast", {"title": "Direct朝食"},
        )
        self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-port-breakfast", "changed",
            {"title": "Working朝食", "start": "07:30"},
        )
        self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "transport", "transport-ferry", "pending_delete", {},
        )
        self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-coffee", "day-2027-05-14",
            {"title": "珈琲休憩", "status": "tentative", "time_mode": "undecided"}, {
                "anchor_source_type": "scheduleItem",
                "anchor_source_item_id": "schedule-port-breakfast", "edge": "after",
            },
        )
        self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "午後は雨想定",
        )
        composed = self.domain.get_working_trip_detail_view("trip-setouchi-2027")
        self.assertEqual(composed["working"], {"present": True, "stale": False})
        self.assertNotIn("state", composed["working"])
        day = composed["days"][0]
        self.assertEqual(day["working_instruction"], "午後は雨想定")
        ids = [entry["source_item_id"] for entry in day["entries"]]
        breakfast_index = ids.index("schedule-port-breakfast")
        self.assertEqual(ids[breakfast_index + 1], "temporary-coffee")
        breakfast = day["entries"][breakfast_index]
        self.assertEqual((breakfast["title"], breakfast["time"]["label"]), ("Working朝食", "07:30"))
        self.assertEqual(breakfast["working_state"], "changed")
        temporary = day["entries"][breakfast_index + 1]
        self.assertEqual((temporary["title"], temporary["working_state"]), ("珈琲休憩", "temporary"))
        ferry = next(entry for entry in day["entries"] if entry["source_item_id"] == "transport-ferry")
        self.assertEqual(ferry["working_state"], "pending_delete")
        self.assertEqual(self.trip_path.read_bytes(), original)

    def test_working_trip_detail_reports_absent_and_stale_without_confirming(self):
        plain = self.domain.get_working_trip_detail_view("trip-setouchi-2027")
        self.assertEqual(plain["working"], {"present": False, "stale": False})
        self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "changed",
            {"title": "Working dinner"},
        )
        self.domain.edit_trip_item(
            "direct-after-working-view", "trip-setouchi-2027", "scheduleItem",
            "schedule-port-breakfast", {"normal_comment": "確定側の後続変更"},
        )
        composed = self.domain.get_working_trip_detail_view("trip-setouchi-2027")
        self.assertEqual(composed["working"], {"present": True, "stale": True})
        dinner = next(entry for day in composed["days"] for entry in day["entries"]
                      if entry["source_item_id"] == "schedule-dinner")
        self.assertEqual((dinner["title"], dinner["working_state"]), ("Working dinner", "changed"))

    def test_chat_export_contains_complete_sources_revision_and_user_intent(self):
        original = self.trip_path.read_bytes()
        self.domain.edit_trip_item(
            "direct-before-chat-export", "trip-setouchi-2027", "scheduleItem",
            "schedule-port-breakfast", {"title": "Direct breakfast"},
        )
        self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "transport", "transport-ferry", "pending_delete", {},
        )
        self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-coffee", "day-2027-05-14",
            {"title": "Coffee"}, {
                "anchor_source_type": "scheduleItem",
                "anchor_source_item_id": "schedule-port-breakfast", "edge": "after",
            },
        )
        self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "Keep the afternoon indoors",
        )

        exported = self.domain.export_working_trip_for_chat("trip-setouchi-2027")

        self.assertEqual(set(exported), {
            "format", "task", "trip_id", "authoritative_trip", "effective_trip",
            "working", "user_intent",
        })
        self.assertEqual(exported["format"], "cal.complete-trip-regeneration.v1")
        self.assertEqual(exported["trip_id"], "trip-setouchi-2027")
        self.assertEqual(exported["authoritative_trip"]["id"], "trip-setouchi-2027")
        authoritative_breakfast = next(
            item for day in exported["authoritative_trip"]["days"]
            for item in day["scheduleItems"] if item["id"] == "schedule-port-breakfast"
        )
        effective_breakfast = next(
            item for day in exported["effective_trip"]["days"]
            for item in day["scheduleItems"] if item["id"] == "schedule-port-breakfast"
        )
        self.assertNotEqual(authoritative_breakfast["action"], "Direct breakfast")
        self.assertEqual(effective_breakfast["action"], "Direct breakfast")
        self.assertFalse(exported["working"]["stale"])
        self.assertEqual(
            exported["working"]["base_effective_revision"],
            exported["working"]["current_effective_revision"],
        )
        self.assertEqual(exported["user_intent"]["item_changes"][0]["disposition"], "pending_delete")
        self.assertEqual(exported["user_intent"]["temporary_items"][0]["temporary_id"], "temporary-coffee")
        self.assertEqual(
            exported["user_intent"]["day_instructions"][0]["instruction"],
            "Keep the afternoon indoors",
        )
        self.assertIn("One complete formal CAL Trip JSON object only.", exported["task"]["required_output"])
        self.assertEqual(self.trip_path.read_bytes(), original)

    def test_chat_export_reports_stale_without_rebasing_or_confirming(self):
        created = self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-dinner", "changed",
            {"title": "Working dinner"},
        )
        self.domain.edit_trip_item(
            "direct-after-chat-export-base", "trip-setouchi-2027", "scheduleItem",
            "schedule-port-breakfast", {"normal_comment": "New confirmed context"},
        )

        exported = self.domain.export_working_trip_for_chat("trip-setouchi-2027")

        self.assertTrue(exported["working"]["stale"])
        self.assertEqual(exported["working"]["base_effective_revision"], created["base_effective_revision"])
        self.assertNotEqual(
            exported["working"]["base_effective_revision"],
            exported["working"]["current_effective_revision"],
        )
        self.assertEqual(exported["user_intent"]["item_changes"][0]["changes"]["title"], "Working dinner")

    def test_manual_chat_round_trip_adopts_all_working_intent_as_complete_candidate(self):
        self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "scheduleItem", "schedule-port-breakfast", "changed",
            {"title": "港でブランチをとる", "start": "10:30"},
        )
        self.domain.save_working_trip_item_change(
            "trip-setouchi-2027", "transport", "transport-ferry", "pending_delete", {},
        )
        self.domain.save_working_trip_temporary_item(
            "trip-setouchi-2027", "temporary-coffee", "day-2027-05-14",
            {"title": "港の喫茶店で休憩"}, {
                "anchor_source_type": "scheduleItem",
                "anchor_source_item_id": "schedule-port-breakfast", "edge": "after",
            },
        )
        self.domain.save_working_trip_day_instruction(
            "trip-setouchi-2027", "day-2027-05-14", "船を使わず港周辺でゆっくり過ごす",
        )

        package = self.domain.export_working_trip_for_chat("trip-setouchi-2027")
        self.assertFalse(package["working"]["stale"])
        self.assertEqual(
            {record["disposition"] for record in package["user_intent"]["item_changes"]},
            {"changed", "pending_delete"},
        )

        # Simulate the one complete formal Trip object returned by a manual Chat round trip.
        candidate = package["effective_trip"]
        first_day = candidate["days"][0]
        breakfast = first_day["scheduleItems"][0]
        breakfast["action"] = "港でブランチをとる"
        breakfast["time"]["start"] = "10:30"
        coffee = json.loads(json.dumps(breakfast, ensure_ascii=False))
        coffee.update({
            "id": "schedule-harbor-coffee", "order": 20,
            "action": "港の喫茶店で休憩", "summary": "港周辺でゆっくり休憩する。",
        })
        coffee["time"] = {
            "mode": "undecided", "start": None, "end": None, "durationMinutes": 45,
        }
        first_day["scheduleItems"].insert(1, coffee)
        first_day["title"] = "船を使わず港周辺でゆっくり過ごす"
        first_day["routeSummary"] = "自宅 → 青凪港周辺"
        first_day["transportIds"].remove("transport-ferry")
        candidate["transports"] = [
            item for item in candidate["transports"] if item["id"] != "transport-ferry"
        ]
        candidate["bookings"] = [
            item for item in candidate["bookings"] if item["id"] != "booking-ferry"
        ]

        result = self.domain.adopt_working_trip_candidate(
            package["trip_id"], candidate,
        )

        self.assertEqual((result["status"], result["version"]), ("adopted", 2))
        adopted = json.loads(self.trip_path.read_bytes())
        adopted_day = adopted["days"][0]
        adopted_ids = [item["id"] for item in adopted_day["scheduleItems"]]
        self.assertEqual(adopted_day["scheduleItems"][0]["action"], "港でブランチをとる")
        self.assertEqual(adopted_day["scheduleItems"][0]["time"]["start"], "10:30")
        self.assertIn("schedule-harbor-coffee", adopted_ids)
        self.assertEqual(adopted_day["title"], "船を使わず港周辺でゆっくり過ごす")
        self.assertNotIn("transport-ferry", adopted_day["transportIds"])
        self.assertNotIn("transport-ferry", {item["id"] for item in adopted["transports"]})
        self.assertNotIn("booking-ferry", {item["id"] for item in adopted["bookings"]})
        with self.assertRaises(NotFoundError):
            self.domain.get_working_trip("trip-setouchi-2027")

    def test_chat_export_requires_existing_working_state(self):
        with self.assertRaisesRegex(NotFoundError, "Working Trip not found"):
            self.domain.export_working_trip_for_chat("trip-setouchi-2027")

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
