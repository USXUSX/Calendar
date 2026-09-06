import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from Sources.place_acquisition import Acquisition, FacilityCandidate, FacilityQuery
from Sources.aig_candidate_recommendation import CONTRACT, failure, recommend, command_transport
from scripts.init_calendar_db import initialize
from scripts.validate_trip import semantic_errors


def success(ids):
    return dict(contract_version=CONTRACT, status="succeeded", recommended_ids=ids,
                reason="候補です。静かさは未確認です。", unverified_conditions=["静かな席"], failure_code=None)


class RecommendationTests(unittest.TestCase):
    def test_zero_to_three_and_order(self):
        candidates = [dict(id=str(i), name="合成", snippet="", url="") for i in range(5)]
        for ids in ([], ["2"], ["2", "0"], ["2", "0", "1"]):
            calls = []
            def send(request):
                calls.append(request)
                return success(ids)
            self.assertEqual(recommend(" 元の条件 ", candidates, send), success(ids))
            self.assertEqual(calls, [dict(contract_version=CONTRACT, query=" 元の条件 ", candidates=candidates)])

    def test_invalid_results_fail_as_a_whole(self):
        candidates = [dict(id=str(i), name="合成", snippet="", url="") for i in range(5)]
        for result in [success(["9"]), success(["0", "0"]), success(["0", "1", "2", "3"]),
                       success([True]), dict(success([]), reason=""), dict(success([]), raw="private"),
                       dict(success([]), contract_version="old"), dict(failure("afm_unavailable"), reason="raw")]:
            with self.subTest(result=result):
                self.assertEqual(recommend("条件", candidates, lambda _: result), failure("invalid_recommendation"))

    def test_safe_failures_empty_inputs_and_transport_failure(self):
        candidates = [dict(id="a", name="合成", snippet="", url="")]
        for code in ("afm_unavailable", "generation_failed", "invalid_request", "invalid_recommendation"):
            self.assertEqual(recommend("条件", candidates, lambda _: failure(code)), failure(code))
        def fail(_):
            raise TimeoutError("raw private response")
        self.assertEqual(recommend("条件", candidates, fail), failure("generation_failed"))
        self.assertEqual(recommend("条件", [], fail)["recommended_ids"], [])
        self.assertEqual(recommend("x" * 12000, candidates, fail), failure("invalid_request"))

    def test_command_explicit_afm(self):
        with patch("Sources.aig_candidate_recommendation.subprocess.run") as run:
            run.return_value.returncode = 0
            run.return_value.stdout = json.dumps(success([]))
            command_transport("/explicit/aig-candidate-recommendation")(dict(query="条件"))
            self.assertEqual(run.call_args.args[0], ["/explicit/aig-candidate-recommendation", "--provider", "afm"])
            self.assertEqual(run.call_count, 1)
            self.assertTrue(run.call_args.kwargs["capture_output"])


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.db = self.root / "calendar.sqlite3"
        initialize(self.db)
        self.domain = CalendarDomain(self.db, self.root / "data")
        draft = self.domain.parse_chat_paste("旅行名: 合成\n日付: 2027-06-12\n代表エリア: 青町\n予定: 09:00 | 散歩\nカテゴリ: 観光\n場所: 既存公園")
        self.trip_id = self.domain.import_chat_paste("fixture", draft, confirmed=True)["trip_id"]
        self.trip = self.domain.get_effective_trip(self.trip_id)
        self.day_id = self.trip["days"][0]["id"]
        self.before = self.domain._trip_path(self.trip_id).read_bytes()
        self.query = " 青町で静かな席のあるカフェ "
        self.values = dict(title="休憩", category="food", start="14:00", end="15:00")
        self.calls, self.requests = [], []
        self.acquisition = Acquisition("candidates", [FacilityCandidate(
            dict(name=f"合成カフェ{i}", address=f"青町{i}", urls=[f"https://example.com/{i}"],
                 location=dict(latitude=35 + i / 100, longitude=139), summary="restricted"),
            dict(description="一時snippet", provider_id=f"private-{i}", source=f"https://example.com/source/{i}",
                 license="fixture", attribution="source", expires="end_of_operation")) for i in range(5)])
        self.reply = success(["candidate-3", "candidate-1", "candidate-2"])
        owner = self
        class Adapter:
            def search(self, query):
                owner.calls.append(query)
                return copy.deepcopy(owner.acquisition)
        self.adapter = Adapter()

    def transport(self, request):
        self.requests.append(request)
        return copy.deepcopy(self.reply)

    def search(self, **kwargs):
        return self.domain.search_schedule_candidates(self.trip_id, self.day_id, self.query,
                                                     self.adapter, self.transport, **kwargs)

    def add(self, result, ids=None, command="add", values=None):
        return self.domain.add_conditioned_schedule(command, self.trip_id, self.day_id,
            self.values if values is None else values, result, [] if ids is None else ids, confirmed=True)

    def rows(self):
        with sqlite3.connect(self.db) as db:
            return [db.execute("SELECT * FROM " + t).fetchall() for t in
                    ("direct_overrides", "working_trips", "working_trip_generations", "trips")]

    def test_search_is_read_only_preserves_original_and_ranking(self):
        before = self.rows()
        result = self.search(search_queries=[FacilityQuery("カフェ", "青町"), FacilityQuery("喫茶店", "青町")])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(self.requests[0]["query"], self.query)
        self.assertEqual(len(self.requests[0]["candidates"]), 5)
        self.assertEqual(set(self.requests[0]), {"query", "candidates", "contract_version"})
        self.assertNotIn("region", self.requests[0]["candidates"][0])
        self.assertEqual([c["id"] for c in result["candidates"]], self.reply["recommended_ids"])
        self.assertEqual(result["unverified_conditions"], ["静かな席"])
        self.assertNotIn("summary", result["candidates"][0]["fields"])
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.domain._trip_path(self.trip_id).read_bytes(), self.before)

    def test_one_two_three_or_none_save_exactly_one_schedule(self):
        result = self.search()
        for count in range(4):
            with self.subTest(count=count):
                ids = [c["id"] for c in result["candidates"]][:count]
                saved = self.add(result, ids, command=f"add-{count}", values=dict(self.values, title=f"休憩{count}"))
                item = saved["trip"]["days"][0]["scheduleItems"][-1]
                self.assertEqual(len(item["placeSelection"]["candidatePlaceIds"]), count)
                self.assertEqual(len(item["placeSelection"]["selection"]), 1 if count == 1 else 0)
                self.assertEqual(item["searchQuery"], self.query)
                self.assertEqual(saved["trip"]["days"][0]["scheduleItems"][0], self.trip["days"][0]["scheduleItems"][0])
                self.assertEqual(saved["trip"]["places"][0], self.trip["places"][0])
                self.assertNotIn("一時snippet", json.dumps(saved))
                self.assertNotIn("private-", json.dumps(self.rows()))
        self.assertEqual(len(self.domain.list_unresolved_schedule_queries(self.trip_id)), 3)
        self.assertEqual(self.domain._trip_path(self.trip_id).read_bytes(), self.before)
        reopened = CalendarDomain(self.db, self.root / "data")
        self.assertEqual(reopened.get_effective_trip(self.trip_id), saved["trip"])

    def test_failures_and_all_ng_can_save_undecided(self):
        cases = [(Acquisition("no_candidates"), self.reply, "no_candidates"),
                 (Acquisition("unavailable"), self.reply, "search_failed"),
                 (self.acquisition, failure("afm_unavailable"), "recommendation_failed"),
                 (self.acquisition, failure("generation_failed"), "recommendation_failed"),
                 (self.acquisition, success([]), "no_candidates")]
        for n, (acquisition, reply, status) in enumerate(cases):
            self.acquisition, self.reply = acquisition, reply
            result = self.search()
            self.assertEqual(result["status"], status)
            saved = self.add(result, command=str(n), values=dict(self.values, title=f"未定{n}"))
            self.assertEqual(saved["trip"]["days"][0]["scheduleItems"][-1]["placeSelection"]["selection"], [])
        self.assertEqual(len(self.domain.list_unresolved_schedule_queries(self.trip_id)), 5)

    def test_invalid_selections_and_fields_write_nothing(self):
        result = self.search()
        before = self.rows()
        for ids in [["foreign"], ["candidate-1"] * 2, ["candidate-1", "candidate-2", "candidate-3", "candidate-4"], [True]]:
            with self.assertRaises(ValidationError):
                self.add(result, ids)
        for change in [dict(start="25:00"), dict(category="unknown"), dict(normal_comment=[]), dict(extra="raw")]:
            with self.assertRaises(ValidationError):
                self.add(result, values=dict(self.values, **change))
        with self.assertRaises(ValidationError):
            self.domain.add_conditioned_schedule("add", self.trip_id, self.day_id, self.values, result, [])
        self.assertEqual(self.rows(), before)

    def test_restricted_name_cannot_be_persisted(self):
        self.acquisition.candidates[0] = FacilityCandidate({}, dict(name="restricted name", description="temporary"))
        self.reply = success(["candidate-1"])
        result = self.search()
        self.assertFalse(result["candidates"][0]["selectable"])
        with self.assertRaises(ValidationError):
            self.add(result, ["candidate-1"])
        self.add(result, [])
        self.assertNotIn("restricted name", json.dumps(self.rows()))

    def test_double_submit_and_obvious_duplicate_rejected(self):
        result = self.search()
        self.add(result)
        for command in ("add", "another-command"):
            with self.assertRaises(ConflictError):
                self.add(result, command=command)
        with self.assertRaises(ConflictError):
            self.add(result, command="duplicate-existing", values=dict(title="散歩", category="sightseeing", start="09:00"))
        self.assertEqual(len(self.domain.get_effective_trip(self.trip_id)["days"][0]["scheduleItems"]), 2)

    def test_transaction_rollback_and_pending_journal(self):
        result = self.search()
        before = self.rows()
        store = self.domain._store_trip_fields
        count = 0
        def broken(*args):
            nonlocal count
            count += 1
            store(*args)
            if count == 2:
                raise sqlite3.OperationalError("simulated failure")
        with patch.object(self.domain, "_store_trip_fields", side_effect=broken):
            with self.assertRaises(ValidationError):
                self.add(result, ["candidate-1", "candidate-2"])
        self.assertEqual(self.rows(), before)
        journal = self.domain._journal_path(self.trip_id)
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text("pending")
        with self.assertRaises(ConflictError):
            self.add(result)
        self.assertEqual(self.rows(), before)

    def test_other_edits_and_working_retained_and_new_item_editable(self):
        self.domain.start_working_trip(self.trip_id)
        result = self.search()
        self.domain.edit_trip_item("edit-old", self.trip_id, "scheduleItem", self.trip["days"][0]["scheduleItems"][0]["id"], {"title": "編集済み散歩"})
        working_before = self.rows()[1:3]
        saved = self.add(result, ["candidate-1"])
        self.assertEqual(self.rows()[1:3], working_before)
        self.assertTrue(self.domain.get_working_trip(self.trip_id)["stale"])
        self.domain.edit_trip_item("aaa-edit-new", self.trip_id, "scheduleItem", saved["source_item_id"], {"title": "新しい名称"})
        trip = self.domain.get_effective_trip(self.trip_id)
        self.assertEqual(trip["days"][0]["scheduleItems"][0]["action"], "編集済み散歩")
        self.assertEqual(trip["days"][0]["scheduleItems"][-1]["action"], "新しい名称")
        # Recomposition onto a base that already includes the additions is idempotent.
        with self.domain._read() as connection:
            self.domain._validate_adoption_constraints(connection, self.trip_id, trip, ())
        self.assertEqual(self.domain._trip_path(self.trip_id).read_bytes(), self.before)

    def test_empty_candidates_require_nonblank_query_in_formal_validation(self):
        for fields in ({}, {"searchQuery": None}, {"searchQuery": ""},
                       {"searchQuery": " \t\n\u3000"}, {"searchQuery": 123}):
            with self.subTest(fields=fields):
                candidate = copy.deepcopy(self.trip)
                item = candidate["days"][0]["scheduleItems"][0]
                item["placeSelection"].update(candidatePlaceIds=[], selection=[])
                item.update(fields)
                self.assertTrue(any("searchQuery" in error for error in semantic_errors(candidate)))
                with self.assertRaises(ValidationError):
                    self.domain._validated_candidate(self.trip_id, candidate)
        self.assertEqual(self.domain._trip_path(self.trip_id).read_bytes(), self.before)

    def test_empty_candidates_with_original_query_remain_valid(self):
        candidate = copy.deepcopy(self.trip)
        item = candidate["days"][0]["scheduleItems"][0]
        item["placeSelection"].update(candidatePlaceIds=[], selection=[])
        item["searchQuery"] = self.query
        self.assertEqual(semantic_errors(candidate), [])
        validated, _ = self.domain._validated_candidate(self.trip_id, candidate)
        self.assertEqual(validated, candidate)
        self.assertEqual(validated["days"][0]["scheduleItems"][0]["searchQuery"], self.query)

    def test_existing_candidates_do_not_require_query(self):
        for selected in (True, False):
            with self.subTest(selected=selected):
                candidate = copy.deepcopy(self.trip)
                item = candidate["days"][0]["scheduleItems"][0]
                self.assertNotIn("searchQuery", item)
                self.assertTrue(item["placeSelection"]["candidatePlaceIds"])
                if not selected:
                    item["placeSelection"]["selection"] = []
                self.assertEqual(semantic_errors(candidate), [])
                validated, _ = self.domain._validated_candidate(self.trip_id, candidate)
                self.assertEqual(validated, candidate)

    def test_addition_semantics_rechecked_against_future_base(self):
        result = self.search()
        self.add(result)
        candidate = copy.deepcopy(self.trip)
        candidate["days"][0]["scheduleItems"][0]["order"] = 1
        with self.domain._read() as connection:
            with self.assertRaises(ValidationError):
                self.domain._validate_adoption_constraints(connection, self.trip_id, candidate, ())

    def test_candidate_aggregation_is_bounded(self):
        self.acquisition.candidates *= 4
        # Different provider IDs stand for distinct evidence, even if names coincide.
        self.acquisition.candidates = [copy.deepcopy(c) for c in self.acquisition.candidates]
        for n, candidate in enumerate(self.acquisition.candidates):
            candidate.temporary["provider_id"] = str(n)
        self.search(search_queries=[FacilityQuery("a"), FacilityQuery("b")])
        self.assertEqual(len(self.requests[0]["candidates"]), 10)
        self.assertEqual(len(self.calls), 1)

    def test_changed_day_area_requires_refresh(self):
        result = self.search()
        self.domain.edit_trip_day("area", self.trip_id, self.day_id, {"route_summary": "別の町"})
        with self.assertRaises(ConflictError):
            self.add(result)

    def test_search_failure_stops_queries_and_leaks_no_errors(self):
        with patch.object(self.adapter, "search", side_effect=TimeoutError("private raw")) as call:
            result = self.search(search_queries=[FacilityQuery("a"), FacilityQuery("b")])
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result["status"], "search_failed")
        self.assertNotIn("private raw", json.dumps(result))
        self.add(result)


if __name__ == "__main__":
    unittest.main()
