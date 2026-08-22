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


def request(base, path, method="GET"):
    try:
        with urllib.request.urlopen(urllib.request.Request(base + path, method=method), timeout=2) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


class LocalTripApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.local_data = Path(self.temp.name)
        trips = self.local_data / "trips"
        trips.mkdir()
        for trip_id, title, start in (("future-trip", "Future Trip", "2099-03-01"), ("past-trip", "Past Trip", "2020-02-01")):
            payload = {"id": trip_id, "title": title, "dateRange": {"start": start, "end": start}, "private": "fixture"}
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
        self.assertEqual({trip["id"] for trip in trips}, {"future-trip", "past-trip"})
        self.assertEqual(set(trips[0]), {"id", "title", "dateRange"})
        status, current = request(self.base, "/api/trips/future-trip")
        self.assertEqual(status, 200)
        self.assertEqual(current["private"], "fixture")

    def test_rejects_missing_private_and_write_paths(self):
        self.assertEqual(request(self.base, "/api/trips/missing")[0], 404)
        self.assertEqual(request(self.base, "/api/trips/future-trip/candidate")[0], 404)
        self.assertEqual(request(self.base, "/api/trips/future-trip", "POST")[0], 405)
        self.assertEqual(request(self.base, "/api/trips/..%2Ffuture-trip")[0], 404)

    def test_reports_invalid_json_and_id_mismatch(self):
        trip_file = self.local_data / "trips" / "future-trip.json"
        trip_file.write_text("not json", encoding="utf-8")
        self.assertEqual(request(self.base, "/api/trips")[0], 500)
        trip_file.write_text(json.dumps({"id": "wrong", "title": "Wrong", "dateRange": {"start": "2099-01-01", "end": "2099-01-01"}}), encoding="utf-8")
        self.assertEqual(request(self.base, "/api/trips/future-trip")[0], 500)


if __name__ == "__main__":
    unittest.main()
