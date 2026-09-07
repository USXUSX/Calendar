import copy
import unittest

from Sources.calendar_domain.trip_detail import build_trip_detail_view


def schedule(item_id, order, start, end, *, mode="fixed"):
    return {
        "id": item_id,
        "dayId": "day-1",
        "order": order,
        "status": "confirmed",
        "action": item_id,
        "category": "sightseeing",
        "summary": None,
        "details": [],
        "time": {"mode": mode, "start": start, "end": end, "durationMinutes": None},
        "placeSelection": {
            "candidatePlaceIds": ["place-1"],
            "selection": ["place-1"],
            "minSelections": 1,
            "maxSelections": 1,
        },
    }


def trip(items):
    return {
        "id": "trip-1",
        "title": "Test trip",
        "dateRange": {"start": "2026-09-07", "end": "2026-09-07"},
        "summary": None,
        "days": [{
            "id": "day-1",
            "date": "2026-09-07",
            "title": "Day 1",
            "routeSummary": None,
            "scheduleItems": copy.deepcopy(items),
            "transportIds": [],
        }],
        "places": [{
            "id": "place-1",
            "name": "Place",
            "summary": None,
            "category": "attraction",
            "address": None,
            "location": None,
            "urls": [],
            "rating": None,
        }],
        "transports": [],
        "preparation": {"id": "prep-1", "tasks": []},
        "rioPlan": {
            "id": "rio-1",
            "applicable": False,
            "careMode": "not_applicable",
            "careDecisionDueDate": None,
            "careDetails": None,
            "packingTemplate": None,
            "packingItems": [],
        },
        "bookings": [],
    }


class TimeConflictTests(unittest.TestCase):
    def entries(self, items):
        return build_trip_detail_view(trip(items))["days"][0]["entries"]

    def test_adjacent_explicit_overlap_marks_both_entries(self):
        entries = self.entries([
            schedule("first", 1, "09:00", "10:00"),
            schedule("second", 2, "09:30", "11:00"),
            schedule("third", 3, "11:00", "12:00"),
        ])
        self.assertEqual([entry["source_item_id"] for entry in entries], ["first", "second", "third"])
        self.assertEqual([entry["time_conflict"] for entry in entries], [True, True, False])

    def test_exact_boundary_is_not_a_conflict(self):
        entries = self.entries([
            schedule("first", 1, "09:00", "10:00"),
            schedule("second", 2, "10:00", "11:00"),
        ])
        self.assertEqual([entry["time_conflict"] for entry in entries], [False, False])

    def test_unknown_times_are_not_guessed(self):
        entries = self.entries([
            schedule("first", 1, "09:00", None),
            schedule("second", 2, None, None, mode="undecided"),
        ])
        self.assertEqual([entry["time_conflict"] for entry in entries], [False, False])

    def test_possible_overnight_previous_entry_is_not_judged(self):
        entries = self.entries([
            schedule("first", 1, "23:00", "01:00"),
            schedule("second", 2, "00:30", "02:00"),
        ])
        self.assertEqual([entry["time_conflict"] for entry in entries], [False, False])


if __name__ == "__main__":
    unittest.main()
