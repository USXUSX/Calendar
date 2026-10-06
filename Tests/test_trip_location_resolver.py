import io
import json
import unittest
from scripts.trip_location_resolver import resolve_location_plan


class Response:
    def __init__(self, value):
        self.value = value
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.value).encode("utf-8")


class ResolverTest(unittest.TestCase):
    def test_resolves_each_missing_point_and_reuses_duplicate_query(self):
        calls = []
        def opener(request, timeout=None):
            calls.append(request)
            if isinstance(request, str):
                return Response({"key": "synthetic"})
            body = json.loads(request.data.decode("utf-8"))
            query = body["textQuery"]
            values = {
                "A": {"places": [{"id": "ga", "location": {"latitude": 1.0, "longitude": 2.0}}]},
                "B": {"places": []},
            }
            return Response(values[query])
        plan = [
            {"place_id": "a1", "query": "A", "location": None, "skip_search": False},
            {"place_id": "a2", "query": "A", "location": None, "skip_search": False},
            {"place_id": "b", "query": "B", "location": None, "skip_search": False},
            {"place_id": "existing", "query": "C", "location": {"latitude": 3, "longitude": 4}},
        ]
        result = resolve_location_plan(plan, "http://example/config", opener=opener)
        self.assertEqual(result["coordinates"], {"attempted": 3, "filled": 2, "missing": 1, "existing": 1})
        self.assertEqual(result["coordinate_results"]["a1"], result["coordinate_results"]["a2"])
        self.assertIsNone(result["coordinate_results"]["b"])
        self.assertEqual(len(calls), 3)  # config + unique queries A/B

    def test_no_search_does_not_require_map_connection(self):
        def fail(*args, **kwargs):
            raise AssertionError("map connection must not be used")
        result = resolve_location_plan(
            [{"place_id": "x", "query": "X", "location": {"latitude": 1, "longitude": 2}}],
            opener=fail,
        )
        self.assertEqual(result["coordinate_results"], {})
        self.assertEqual(result["coordinates"]["attempted"], 0)


if __name__ == "__main__":
    unittest.main()
