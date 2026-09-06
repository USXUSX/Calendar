import copy
import json
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from pathlib import Path

from Sources.place_acquisition import Acquisition, FacilityCandidate, FacilityQuery, WikidataAdapter
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize


def statement(value, **extra):
    return dict(rank="normal", mainsnak={"snaktype": "value", "datavalue": {"value": value}}, **extra)


def entity(qid="Q1"):
    return {"id": qid, "labels": {"ja": {"value": "サンプルタワー"}},
            "descriptions": {"ja": {"value": "東京の塔"}}, "claims": {
                "P625": [statement({"latitude": 35.6, "longitude": 139.7,
                                    "globe": "http://www.wikidata.org/entity/Q2"})],
                "P6375": [statement({"language": "ja", "text": "東京都サンプル区"})],
                "P856": [statement("https://example.com/tower")]}}


class AcquisitionTests(unittest.TestCase):
    def adapter(self, entities=None):
        entities = {"Q1": entity()} if entities is None else entities
        self.calls = []

        def transport(params):
            self.calls.append(params)
            if params["action"] == "wbsearchentities":
                return {"search": [{"id": qid} for qid in entities]}
            return {"entities": entities}
        return WikidataAdapter(transport=transport)

    def test_shared_adapter_separates_cc0_values_from_evidence(self):
        result = self.adapter().search(FacilityQuery("サンプルタワー", "東京"))
        self.assertEqual(result.status, "candidates")
        fields = result.candidates[0].persistable
        self.assertEqual(set(fields), {"name", "location", "address", "urls"})
        self.assertEqual(result.candidates[0].temporary["license"], "CC0")
        self.assertTrue(result.candidates[0].temporary["area_hint_matches"])
        self.assertEqual(len(self.calls), 2)
        self.assertEqual(self.calls[0]["limit"], 5)
        self.assertEqual(self.calls[0]["search"], "サンプルタワー")
        self.assertEqual(set(self.calls[0]), {"action", "search", "language", "uselang", "type", "limit", "format", "maxlag"})

    def test_no_results_and_failure_are_bounded(self):
        self.assertEqual(self.adapter({}).search(FacilityQuery("不明")).status, "no_candidates")
        self.assertEqual(len(self.calls), 1)
        calls = []
        def fail(params):
            calls.append(params)
            raise TimeoutError("private provider body")
        result = WikidataAdapter(transport=fail).search(FacilityQuery("例"))
        self.assertEqual(result, Acquisition("unavailable"))
        self.assertEqual(len(calls), 1)
        self.assertNotIn("private", repr(result))

    def test_rate_limit_stops_without_retry_or_sleeping_through_cooldown(self):
        adapter = WikidataAdapter()
        error = HTTPError(adapter.endpoint, 429, "limited", {"Retry-After": "120"}, None)
        with patch("Sources.place_acquisition.urlopen", side_effect=error) as request:
            self.assertEqual(adapter.search(FacilityQuery("例")).status, "unavailable")
            self.assertEqual(adapter.search(FacilityQuery("例")).status, "unavailable")
            self.assertEqual(request.call_count, 1)

    def test_api_error_stops_and_malformed_response_fails_closed(self):
        for value in ({"error": {"code": "maxlag", "info": "raw"}}, {"search": "bad"}, []):
            calls = []
            def transport(params):
                calls.append(params)
                return value
            adapter = WikidataAdapter(transport=transport)
            self.assertEqual(adapter.search(FacilityQuery("例")), Acquisition("unavailable"))
            self.assertEqual(len(calls), 1)
        with self.assertRaises(ValueError):
            FacilityQuery(None)

    def test_conflicting_qualified_invalid_and_non_earth_values_omitted(self):
        for prop, values in [
            ("P625", [statement({"latitude": True, "longitude": 0, "globe": "http://www.wikidata.org/entity/Q2"})]),
            ("P625", [statement({"latitude": float("nan"), "longitude": 0, "globe": "http://www.wikidata.org/entity/Q2"})]),
            ("P625", [statement({"latitude": 0, "longitude": 0, "globe": "moon"})]),
            ("P856", [statement("http://example.com")]),
            ("P856", [statement("https://example.com", qualifiers={"P580": []})]),
            ("P856", [statement("https://example.com"), statement("https://example.org")]),
        ]:
            with self.subTest(prop=prop, values=values):
                e = entity()
                e["claims"][prop] = values
                result = self.adapter({"Q1": e}).search(FacilityQuery("例"))
                self.assertNotIn({"P625": "location", "P856": "urls"}[prop], result.candidates[0].persistable)


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.db = root / "calendar.sqlite3"
        initialize(self.db)
        self.domain = CalendarDomain(self.db, root / "data")
        draft = self.domain.parse_chat_paste("旅行名: 合成\n日付: 2027-06-12\n代表エリア: 東京\n予定: 未定 | 散歩\nカテゴリ: 観光\n場所: サンプルタワー")
        self.trip_id = self.domain.import_chat_paste("test", draft, confirmed=True)["trip_id"]
        self.trip = self.domain.get_effective_trip(self.trip_id)
        self.target = {"place_id": self.trip["places"][0]["id"]}
        self.before = self.domain._trip_path(self.trip_id).read_bytes()
        self.db_before = self.db.read_bytes()
        self.fields = {"name": "同名の別表記", "address": "例住所", "urls": ["https://example.com"],
                       "location": {"latitude": 35, "longitude": 139}}

    def acquire(self, fields=None, count=1):
        owner = self
        class Adapter:
            def search(self, query):
                owner.query = query
                return Acquisition("candidates", [FacilityCandidate(
                    copy.deepcopy(owner.fields if fields is None else fields),
                    {"provider_id": "private-id", "restricted": "not adoptable"}) for _ in range(count)])
        return self.domain.get_place_enrichment(self.trip_id, self.target, Adapter(), area="東京")

    def test_confirmation_payload_and_existing_complete_trip_adoption(self):
        result = self.acquire()
        self.assertEqual(result["status"], "confirmation_required")
        with self.assertRaises(ValidationError):
            self.domain.prepare_place_enrichment(self.trip_id, self.target, result, 0)
        prepared = self.domain.prepare_place_enrichment(self.trip_id, self.target, result, 0, confirmed=True)
        self.assertEqual(set(prepared["fields"]), {"address", "location", "urls"})
        self.assertEqual(self.query, FacilityQuery("サンプルタワー", "東京", ""))
        self.assertEqual(self.domain._trip_path(self.trip_id).read_bytes(), self.before)
        self.assertEqual(self.db.read_bytes(), self.db_before)
        self.domain.start_working_trip(self.trip_id)
        candidate = copy.deepcopy(self.trip)
        candidate["places"][0].update(prepared["fields"])
        self.domain.adopt_working_trip_candidate(self.trip_id, candidate)
        expected = copy.deepcopy(self.trip)
        expected["places"][0].update(prepared["fields"])
        self.assertEqual(self.domain.get_effective_trip(self.trip_id), expected)
        self.assertNotIn("private-id", self.domain._trip_path(self.trip_id).read_text())

    def test_ambiguity_no_auto_selection_and_restricted_fields_excluded(self):
        fields = dict(self.fields, provider_id="bad", summary="restricted summary")
        result = self.acquire(fields, 2)
        self.assertEqual(result["status"], "ambiguous")
        self.assertNotIn("provider_id", json.dumps(result))
        self.assertNotIn("summary", result["candidates"][0]["fields"])
        for index in (-1, 2, True):
            with self.assertRaises(ValidationError):
                self.domain.prepare_place_enrichment(self.trip_id, self.target, result, index, confirmed=True)
        self.assertEqual(self.domain._trip_path(self.trip_id).read_bytes(), self.before)
        result = self.acquire({})
        prepared = self.domain.prepare_place_enrichment(self.trip_id, self.target, result, 0, confirmed=True)
        self.assertEqual(prepared["status"], "unfilled")

    def test_existing_nonempty_values_and_stale_input(self):
        result = self.acquire()
        candidate = copy.deepcopy(self.trip)
        candidate["places"][0].update(address="手入力", urls=["https://example.org"],
                                      location={"latitude": 1, "longitude": 2})
        self.domain.start_working_trip(self.trip_id)
        self.domain.adopt_working_trip_candidate(self.trip_id, candidate)
        with self.assertRaises(ConflictError):
            self.domain.prepare_place_enrichment(self.trip_id, self.target, result, 0, confirmed=True)
        result = self.acquire()
        self.assertEqual(self.domain.prepare_place_enrichment(self.trip_id, self.target, result, 0,
                                                              confirmed=True)["fields"], {})

    def test_target_mismatch_and_failure_do_not_change_trip(self):
        result = self.acquire()
        result["target"] = {"place_id": "another"}
        with self.assertRaises(ValidationError):
            self.domain.prepare_place_enrichment(self.trip_id, self.target, result, 0, confirmed=True)
        class Failure:
            def search(self, query):
                raise RuntimeError("reservation or raw body")
        result = self.domain.get_place_enrichment(self.trip_id, self.target, Failure())
        self.assertEqual(result["status"], "unavailable")
        self.assertNotIn("reservation", json.dumps(result))
        self.assertEqual(self.domain._trip_path(self.trip_id).read_bytes(), self.before)
        self.assertEqual(self.db.read_bytes(), self.db_before)

    def test_temporary_target_uses_name_only_and_does_not_write_working(self):
        day = self.trip["days"][0]
        self.domain.save_working_trip_temporary_item(self.trip_id, "temp", day["id"],
            {"place_name": "サンプルタワー"},
            {"anchor_source_type": "scheduleItem", "anchor_source_item_id": day["scheduleItems"][0]["id"], "edge": "after"})
        before = self.domain.get_working_trip(self.trip_id)
        self.target = {"temporary_id": "temp"}
        result = self.acquire()
        self.assertEqual(self.domain.prepare_place_enrichment(self.trip_id, self.target, result, 0,
                                                              confirmed=True)["status"], "ready")
        self.assertEqual(self.domain.get_working_trip(self.trip_id), before)


if __name__ == "__main__":
    unittest.main()
