import json
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "scripts" / "serve_calendar.py"
sys.path.insert(0, str(ROOT))
from Sources.calendar_domain import CalendarDomain  # noqa: E402
from scripts.init_calendar_db import initialize  # noqa: E402


def request(base, path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        with urllib.request.urlopen(urllib.request.Request(
            base + path, data=data, method=method,
            headers={"Content-Type": "application/json"} if data else {},
        ), timeout=2) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class LocalTripApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.local_data = Path(self.temp.name)
        trips = self.local_data / "trips"
        trips.mkdir()
        with (ROOT / "Samples" / "synthetic-trip.json").open(encoding="utf-8") as handle:
            self.sample = json.load(handle)
        for trip_id, title in (("first-trip", "First Trip"), ("second-trip", "Second Trip")):
            payload = dict(self.sample)
            payload["id"] = trip_id
            payload["title"] = title
            (trips / f"{trip_id}.json").write_text(json.dumps(payload), encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER), "--port", "0", "--local-data", str(self.local_data)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        line = self.process.stdout.readline().strip()
        self.base = line.split("Calendar: ", 1)[1].rsplit("/Sources/web/", 1)[0]

    def tearDown(self):
        self.process.terminate()
        self.process.wait(timeout=3)
        self.process.stdout.close()
        self.process.stderr.close()
        self.temp.cleanup()

    def test_lists_minimal_metadata_and_returns_current(self):
        status, trips = request(self.base, "/api/trips")
        self.assertEqual(status, 200)
        self.assertEqual({trip["id"] for trip in trips}, {"first-trip", "second-trip"})
        self.assertEqual(set(trips[0]), {"id", "title", "dateRange"})
        status, current = request(self.base, "/api/trips/first-trip")
        self.assertEqual(status, 200)
        self.assertEqual(current["summary"], self.sample["summary"])

    def test_rejects_missing_private_and_write_paths(self):
        self.assertEqual(request(self.base, "/api/trips/missing")[0], 404)
        self.assertEqual(request(self.base, "/api/trips/first-trip/candidate")[0], 404)
        self.assertEqual(request(self.base, "/api/trips/first-trip", "POST")[0], 405)
        self.assertEqual(request(self.base, "/api/trips/..%2Ffirst-trip")[0], 404)

    def test_reports_invalid_json_and_id_mismatch(self):
        trip_file = self.local_data / "trips" / "first-trip.json"
        trip_file.write_text("not json", encoding="utf-8")
        self.assertEqual(request(self.base, "/api/trips")[0], 500)
        trip_file.write_text(json.dumps({"id": "wrong", "title": "Wrong", "dateRange": {"start": "2099-01-01", "end": "2099-01-01"}}), encoding="utf-8")
        self.assertEqual(request(self.base, "/api/trips/first-trip")[0], 500)


class DirectEditApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.local_data = Path(self.temp.name)
        trips = self.local_data / "trips"
        trips.mkdir()
        (trips / "trip-setouchi-2027.json").write_bytes((ROOT / "Samples" / "synthetic-trip.json").read_bytes())
        db = self.local_data / "calendar.sqlite3"
        initialize(db)
        CalendarDomain(db, self.local_data).register_trip("trip-setouchi-2027", "owner")
        self.process = subprocess.Popen(
            [sys.executable, str(SERVER), "--port", "0", "--local-data", str(self.local_data), "--db", str(db)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        line = self.process.stdout.readline().strip()
        self.base = line.split("Calendar: ", 1)[1].rsplit("/Sources/web/", 1)[0]

    def tearDown(self):
        self.process.terminate()
        self.process.wait(timeout=3)
        self.process.stdout.close()
        self.process.stderr.close()
        self.temp.cleanup()

    def test_direct_edit_returns_effective_trip_and_rejects_partial_invalid_change(self):
        valid = {"command_id": "api-edit", "source_type": "scheduleItem",
                 "source_item_id": "schedule-port-breakfast",
                 "changes": {"status": "undecided", "title": "港で朝食とコーヒーを楽しむ"}}
        status, result = request(self.base, "/api/trips/trip-setouchi-2027/direct-edit", "POST", valid)
        self.assertEqual(status, 200)
        self.assertEqual(result["trip"]["days"][0]["scheduleItems"][0]["status"], "undecided")
        invalid = {"command_id": "api-bad", "source_type": "scheduleItem",
                   "source_item_id": "schedule-port-breakfast",
                   "changes": {"status": "tentative", "time_mode": "range", "end": None}}
        self.assertEqual(request(self.base, "/api/trips/trip-setouchi-2027/direct-edit", "POST", invalid)[0], 422)
        current = request(self.base, "/api/trips/trip-setouchi-2027")[1]
        self.assertEqual(current["days"][0]["scheduleItems"][0]["status"], "undecided")


if __name__ == "__main__":
    unittest.main()
