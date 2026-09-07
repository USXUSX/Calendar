import unittest
from datetime import date

from Sources.calendar_domain.weather import OpenMeteoAdapter, build_weather_by_day


def place(place_id, name, latitude=None, longitude=None):
    return {
        "id": place_id,
        "name": name,
        "location": None if latitude is None else {"latitude": latitude, "longitude": longitude},
    }


def schedule(item_id, day_id, order, selected):
    return {
        "id": item_id,
        "order": order,
        "placeSelection": {"selection": selected},
    }


def trip(days, places):
    return {"days": days, "places": places, "transports": []}


def open_meteo_payload():
    return {
        "daily": {
            "time": ["2026-09-08"],
            "weather_code": [1],
            "temperature_2m_max": [29.5],
            "temperature_2m_min": [21.0],
            "precipitation_probability_max": [20],
            "precipitation_sum": [0.4],
        },
        "daily_units": {
            "weather_code": "wmo code",
            "temperature_2m_max": "°C",
            "temperature_2m_min": "°C",
            "precipitation_probability_max": "%",
            "precipitation_sum": "mm",
        },
    }


class FakeAdapter:
    def __init__(self, value=None):
        self.value = value or {"status": "available", "weather_label": "晴れ"}
        self.calls = []

    def forecast(self, location, target_date):
        self.calls.append((location, target_date))
        return dict(self.value)


class WeatherContextTests(unittest.TestCase):
    def test_available_uses_first_selected_place_with_stored_coordinates(self):
        data = trip([
            {"id": "day-1", "date": "2026-09-10", "scheduleItems": [
                schedule("first", "day-1", 10, ["missing-location"]),
                schedule("second", "day-1", 20, ["known"]),
            ], "transportIds": []},
        ], [place("missing-location", "No coords"), place("known", "Known", 35.0, 139.0)])
        adapter = FakeAdapter()
        result = build_weather_by_day(data, adapter, today=date(2026, 9, 7))["day-1"]
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["place_id"], "known")
        self.assertEqual(result["place_name"], "Known")
        self.assertEqual(result["forecast_date"], "2026-09-10")
        self.assertEqual(result["attribution"], "Weather data by Open-Meteo.com")
        self.assertEqual(len(adapter.calls), 1)

    def test_outside_forecast_does_not_call_provider(self):
        data = trip([
            {"id": "day-1", "date": "2026-09-23", "scheduleItems": [
                schedule("one", "day-1", 10, ["known"]),
            ], "transportIds": []},
        ], [place("known", "Known", 35.0, 139.0)])
        adapter = FakeAdapter()
        result = build_weather_by_day(data, adapter, today=date(2026, 9, 7))["day-1"]
        self.assertEqual(result["status"], "outside_forecast")
        self.assertEqual(adapter.calls, [])

    def test_in_range_without_coordinates_is_location_unknown(self):
        data = trip([
            {"id": "day-1", "date": "2026-09-08", "scheduleItems": [
                schedule("one", "day-1", 10, ["unknown"]),
            ], "transportIds": []},
        ], [place("unknown", "Unknown")])
        adapter = FakeAdapter()
        result = build_weather_by_day(data, adapter, today=date(2026, 9, 7))["day-1"]
        self.assertEqual(result["status"], "location_unknown")
        self.assertEqual(adapter.calls, [])

    def test_provider_failure_remains_distinct(self):
        data = trip([
            {"id": "day-1", "date": "2026-09-08", "scheduleItems": [
                schedule("one", "day-1", 10, ["known"]),
            ], "transportIds": []},
        ], [place("known", "Known", 35.0, 139.0)])
        adapter = FakeAdapter({"status": "unavailable"})
        result = build_weather_by_day(data, adapter, today=date(2026, 9, 7))["day-1"]
        self.assertEqual(result["status"], "unavailable")
        self.assertEqual(result["place_name"], "Known")

    def test_open_meteo_adapter_maps_daily_values_and_units(self):
        def transport(params):
            self.assertEqual(params["forecast_days"], 16)
            self.assertEqual(params["timezone"], "auto")
            return open_meteo_payload()
        adapter = OpenMeteoAdapter(transport=transport)
        result = adapter.forecast({"latitude": 35.0, "longitude": 139.0}, date(2026, 9, 8))
        self.assertEqual(result["status"], "available")
        self.assertFalse(result["cached"])
        self.assertEqual(result["weather_label"], "晴れ")
        self.assertEqual(result["temperature_max"], 29.5)
        self.assertEqual(result["temperature_min"], 21.0)
        self.assertEqual(result["precipitation_probability_max"], 20)
        self.assertEqual(result["precipitation_sum"], 0.4)
        self.assertEqual(result["units"]["temperature_max"], "°C")

    def test_expired_cache_is_never_returned_as_current(self):
        now = [0.0]
        calls = []

        def transport(_params):
            calls.append(now[0])
            if len(calls) == 1:
                return open_meteo_payload()
            raise OSError("provider unavailable")

        adapter = OpenMeteoAdapter(
            transport=transport, cache_seconds=10, clock=lambda: now[0],
        )
        location = {"latitude": 35.0, "longitude": 139.0}
        target = date(2026, 9, 8)
        first = adapter.forecast(location, target)
        now[0] = 5.0
        cached = adapter.forecast(location, target)
        now[0] = 11.0
        expired = adapter.forecast(location, target)

        self.assertEqual(first["status"], "available")
        self.assertFalse(first["cached"])
        self.assertEqual(cached["status"], "available")
        self.assertTrue(cached["cached"])
        self.assertEqual(expired, {"status": "unavailable"})
        self.assertEqual(calls, [0.0, 11.0])


if __name__ == "__main__":
    unittest.main()
