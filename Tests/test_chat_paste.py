import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize


ROOT = Path(__file__).resolve().parents[1]


class ChatPasteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db = root / "calendar.sqlite3"
        initialize(self.db)
        self.domain = CalendarDomain(self.db, root / "data", chat_root=root / "chat")
        self.example = re.search(r"```text\n(.*?)```", (ROOT / "docs/initial-release.md").read_text(), re.S)[1]

    def assert_empty(self):
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM trips").fetchone()[0], 0)
        self.assertFalse(list(self.domain.trip_root.glob("trips/*.json")))

    def test_spec_example_confirmation_then_import_and_repeat_conflict(self):
        review = self.domain.parse_chat_paste(self.example)
        self.assertEqual(review["unresolved"], [])
        self.assertFalse(any(r["path"].endswith(".category") for r in review["requirements"]))
        preview = self.domain.review_chat_paste("example", review)
        self.assertTrue(preview["ready"])
        self.assertEqual(len(preview["view"]["days"]), 2)
        self.assert_empty()
        with self.assertRaises(ValidationError):
            self.domain.import_chat_paste("example", review)
        result = self.domain.import_chat_paste("example", review, confirmed=True)
        trip = self.domain.get_effective_trip(result["trip_id"])
        self.assertEqual(trip["title"], "北海道旅行")
        self.assertEqual(trip["days"][0]["routeSummary"], "小樽→札幌")
        self.assertEqual([x["order"] for x in preview["view"]["days"][0]["entries"]], [0, 1, 2])
        lunch = trip["days"][0]["scheduleItems"][1]
        self.assertEqual(len(lunch["placeSelection"]["candidatePlaceIds"]), 2)
        self.assertEqual(lunch["placeSelection"]["selection"], [])
        self.assertEqual(lunch["category"], "food")
        self.assertEqual(lunch["summary"], "当日の気分で候補から選ぶ")
        self.assertEqual(trip["days"][1]["scheduleItems"][0]["time"]["end"], None)
        self.assertEqual(trip["days"][1]["scheduleItems"][1]["time"]["mode"], "undecided")
        self.assertEqual(trip["places"][3]["urls"], ["https://example.com/restaurant-a"])
        path = self.domain._trip_path(result["trip_id"])
        before = path.read_bytes()
        with self.assertRaises(ConflictError):
            self.domain.import_chat_paste("example", review, confirmed=True)
        self.assertEqual(path.read_bytes(), before)
        other = self.domain.import_chat_paste("another", review, confirmed=True)
        self.assertNotEqual(other["trip_id"], result["trip_id"])
        self.assertEqual(path.read_bytes(), before)
        self.assertNotIn("draft", json.loads(before))
        self.assertFalse(list(path.parent.glob(".paste-*")))

    def test_notation_unknowns_and_coordinates_are_preserved(self):
        text = "```text\n 旅行名： 合成\n日付：２０２７-０６-１２\n予定：９：００〜１０：００ ｜ 散歩\n カテゴリ ： 観光 \n場所：公園\n座標：３５．１，１３９．２\n候補：別の公園\nURL: https://example.com/park\nコメント: メモ\n読めない行\n```"
        review = self.domain.parse_chat_paste(text)
        self.assertEqual(review["unresolved"][0]["text"], "読めない行")
        item = review["draft"]["days"][0]["items"][0]
        self.assertEqual(item["time"]["start"], "09:00")
        self.assertEqual(item["place"]["location"], {"latitude": 35.1, "longitude": 139.2})
        self.assertEqual(item["candidates"][0]["urls"], ["https://example.com/park"])
        self.assertFalse(self.domain.review_chat_paste("notation", review)["ready"])
        with self.assertRaises(ValidationError):
            self.domain.import_chat_paste("notation", review, confirmed=True)
        review["unresolved"][0]["resolution"] = "excluded"
        self.assertTrue(self.domain.review_chat_paste("notation", review)["ready"])
        self.assert_empty()

    def test_all_categories_are_adopted_from_paste_without_content_inference(self):
        for label, expected in (("観光", "sightseeing"), ("食事", "food"), ("宿泊", "accommodation")):
            with self.subTest(label=label):
                # Deliberately identical content: CAL must use only the category label.
                review = self.domain.parse_chat_paste(
                    f"旅行名: 合成\n日付: 2027-06-12\n予定: 未定 | 昼食\nカテゴリ: {label}\n場所: 公園")
                self.assertEqual(review["unresolved"], [])
                self.assertFalse(any(r["path"].endswith(".category") for r in review["requirements"]))
                self.assertTrue(self.domain.review_chat_paste(label, review)["ready"])
                result = self.domain.import_chat_paste(label, review, confirmed=True)
                trip = self.domain.get_effective_trip(result["trip_id"])
                self.assertEqual(trip["days"][0]["scheduleItems"][0]["category"], expected)

    def test_missing_and_invalid_categories_block_until_corrected(self):
        for line in ("", "カテゴリ:", "カテゴリ: 未定", "カテゴリ: その他", "カテゴリ: food"):
            with self.subTest(line=line):
                review = self.domain.parse_chat_paste(
                    f"旅行名: 合成\n日付: 2027-06-12\n予定: 未定 | 昼食\n{line}\n場所: 食堂")
                self.assertIsNone(review["draft"]["days"][0]["items"][0]["category"])
                self.assertTrue(any(r["path"].endswith(".category") and r["required"] for r in review["requirements"]))
                self.assertEqual([r["text"] for r in review["unresolved"]], [line] if line else [])
                self.assertFalse(self.domain.review_chat_paste("category", review)["ready"])
                with self.assertRaises(ValidationError):
                    self.domain.import_chat_paste("category", review, confirmed=True)
                self.assert_empty()
                review["draft"]["days"][0]["items"][0]["category"] = "food"
                for unresolved in review["unresolved"]:
                    unresolved["resolution"] = "corrected"
                self.assertTrue(self.domain.review_chat_paste("category", review)["ready"])

    def test_category_scope_and_duplicates_preserve_confirmation(self):
        review = self.domain.parse_chat_paste(
            "旅行名: 合成\nカテゴリ: 食事\n日付: 2027-06-12\n"
            "予定: 未定 | A\nカテゴリ: 観光\nカテゴリ: 宿泊\n場所: 公園\n"
            "移動: 未定 | 駅A→駅B | 鉄道\nカテゴリ: 食事\n"
            "予定: 未定 | 昼食\n場所: 食堂\n日付: 2027-06-13\n"
            "カテゴリ: 宿泊\n予定: 未定 | 宿泊\n場所: ホテル")
        days = review["draft"]["days"]
        self.assertEqual(days[0]["items"][0]["category"], "sightseeing")
        self.assertNotIn("category", days[0]["items"][1])
        self.assertIsNone(days[0]["items"][2]["category"])
        self.assertIsNone(days[1]["items"][0]["category"])
        self.assertEqual(len(review["unresolved"]), 4)
        self.assertFalse(self.domain.review_chat_paste("scope", review)["ready"])
        self.assert_empty()

    def test_missing_dates_places_categories_and_transport_comments_need_correction(self):
        review = self.domain.parse_chat_paste("旅行名: 合成\n日付: 6-12\n予定: 未定 | 散歩\n移動: 未定 | 駅A→駅B | 鉄道\nコメント: 車窓を楽しむ\n住所: 不明な側")
        self.assertEqual(len(review["unresolved"]), 1)
        requirements = review["requirements"]
        for suffix in (".date", ".category", ".place", ".comment"):
            self.assertTrue(any(r["path"].endswith(suffix) and r["required"] for r in requirements))
        self.assertTrue(any(r["path"].endswith(".time") and not r["required"] for r in requirements))
        with self.assertRaises(ValidationError):
            self.domain.import_chat_paste("missing", review, confirmed=True)
        self.assert_empty()

    def test_formal_validation_rejects_invalid_corrected_values(self):
        for field, value in (("status", "invented"), ("time", {"mode": "fixed", "start": "99:00", "end": None, "durationMinutes": None})):
            with self.subTest(field=field):
                review = self.domain.parse_chat_paste(self.example)
                review["draft"]["days"][0]["items"][0][field] = value
                with self.assertRaises(ValidationError):
                    self.domain.import_chat_paste("invalid", review, confirmed=True)
                self.assert_empty()
        review = self.domain.parse_chat_paste(self.example)
        review["draft"]["days"][0]["items"][0]["time"] = {"mode": "undecided", "start": "09:00", "end": None, "durationMinutes": None}
        with self.assertRaises(ValidationError):
            self.domain.import_chat_paste("semantic", review, confirmed=True)
        self.assert_empty()

    def test_unknown_fields_and_nameless_metadata_are_not_dropped(self):
        for change in (lambda item: item.update(extra="keep me"),
                       lambda item: item.update(place={"name": None, "address": "keep me", "location": None, "urls": []})):
            review = self.domain.parse_chat_paste(self.example)
            change(review["draft"]["days"][0]["items"][0])
            with self.assertRaises(ValidationError):
                self.domain.import_chat_paste("fields", review, confirmed=True)
            self.assert_empty()

    def test_unregistered_file_and_registered_existing_data_are_never_replaced(self):
        review = self.domain.parse_chat_paste(self.example)
        trip_id = self.domain.review_chat_paste("occupied", review)["view"]["trip_id"]
        path = self.domain._trip_path(trip_id)
        path.parent.mkdir(parents=True)
        path.write_text("existing unregistered data")
        with self.assertRaises(ConflictError):
            self.domain.import_chat_paste("occupied", review, confirmed=True)
        self.assertEqual(path.read_text(), "existing unregistered data")

    def test_database_failure_rolls_back_new_file(self):
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER reject_import BEFORE INSERT ON trips BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(ValidationError):
            self.domain.import_chat_paste("db-failure", self.domain.parse_chat_paste(self.example), confirmed=True)
        self.assert_empty()
        self.assertFalse(list(self.domain.trip_root.glob("trips/.paste-*")))

    def test_day_crossing_and_bad_optional_metadata_are_returned_for_review(self):
        review = self.domain.parse_chat_paste("旅行名: 合成\n日付: 2027-06-12\n予定: 23:00-01:00 | 散歩\nカテゴリ: 観光\n場所: 公園\nURL: http://example.com\n座標: 999, 0")
        self.assertEqual(len(review["unresolved"]), 3)
        for line in review["unresolved"]:
            line["resolution"] = "excluded"
        self.assertFalse(self.domain.review_chat_paste("overnight", review)["ready"])
        self.assert_empty()


if __name__ == "__main__":
    unittest.main()
