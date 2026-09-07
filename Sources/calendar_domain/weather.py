"""Transient CAL weather context backed by Open-Meteo; never writes Trip or SQLite."""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_SOURCE = "https://open-meteo.com/"
_ATTRIBUTION = "Weather data by Open-Meteo.com"
_DAILY_FIELDS = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
)
_WEATHER_LABELS = {
    0: "快晴",
    1: "晴れ",
    2: "一部曇り",
    3: "曇り",
    45: "霧",
    48: "着氷性の霧",
    51: "弱い霧雨",
    53: "霧雨",
    55: "強い霧雨",
    56: "弱い着氷性霧雨",
    57: "強い着氷性霧雨",
    61: "弱い雨",
    63: "雨",
    65: "強い雨",
    66: "弱い着氷性の雨",
    67: "強い着氷性の雨",
    71: "弱い雪",
    73: "雪",
    75: "強い雪",
    77: "霧雪",
    80: "弱いにわか雨",
    81: "にわか雨",
    82: "強いにわか雨",
    85: "弱いにわか雪",
    86: "強いにわか雪",
    95: "雷雨",
    96: "雹を伴う雷雨",
    99: "強い雹を伴う雷雨",
}


def _local_today() -> date:
    return datetime.now().astimezone().date()


def _valid_location(location):
    return (
        isinstance(location, dict)
        and set(location) == {"latitude", "longitude"}
        and all(
            type(location.get(key)) in (int, float)
            and math.isfinite(location[key])
            and abs(location[key]) <= bound
            for key, bound in (("latitude", 90), ("longitude", 180))
        )
    )


def _day_places(trip, day):
    places = {place["id"]: place for place in trip["places"]}
    transports = {item["id"]: item for item in trip["transports"]}
    ordered = []
    for item in day["scheduleItems"]:
        ordered.append((item["order"], "schedule", item))
    for transport_id in day["transportIds"]:
        item = transports[transport_id]
        ordered.append((item["order"], "transport", item))
    for _, kind, item in sorted(ordered, key=lambda value: (value[0], value[2]["id"])):
        if kind == "schedule":
            place_ids = item.get("placeSelection", {}).get("selection", [])
        else:
            place_ids = [item["fromPlaceId"], item["toPlaceId"]]
        for place_id in place_ids:
            place = places.get(place_id)
            if place is not None and _valid_location(place.get("location")):
                yield place


class OpenMeteoAdapter:
    """One-shot forecast adapter. No retry or persistent cache."""

    endpoint = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, *, transport=None, timeout=10):
        if not 0 < timeout <= 30:
            raise ValueError("timeout must be between 0 and 30 seconds")
        self.transport = transport or self._http
        self.timeout = timeout

    def _http(self, params):
        request = Request(
            self.endpoint + "?" + urlencode(params),
            headers={"Accept": "application/json", "User-Agent": "Calendar/0.1"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            payload = response.read(500_001)
        if len(payload) > 500_000:
            raise ValueError("weather response too large")
        return json.loads(payload)

    def forecast(self, location, target_date):
        if not _valid_location(location) or not isinstance(target_date, date):
            raise ValueError("invalid weather request")
        params = {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "daily": ",".join(_DAILY_FIELDS),
            "timezone": "auto",
            "forecast_days": 16,
        }
        try:
            payload = self.transport(params)
            daily = payload["daily"]
            units = payload["daily_units"]
            dates = daily["time"]
            index = dates.index(target_date.isoformat())
            values = {field: daily[field][index] for field in _DAILY_FIELDS}
            if any(field not in units for field in _DAILY_FIELDS):
                raise ValueError("weather units missing")
            code = values["weather_code"]
            if type(code) not in (int, float):
                raise ValueError("invalid weather code")
            return {
                "status": "available",
                "retrieved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
                "weather_code": int(code),
                "weather_label": _WEATHER_LABELS.get(int(code), "不明"),
                "temperature_max": values["temperature_2m_max"],
                "temperature_min": values["temperature_2m_min"],
                "precipitation_probability_max": values["precipitation_probability_max"],
                "precipitation_sum": values["precipitation_sum"],
                "units": {
                    "temperature_max": units["temperature_2m_max"],
                    "temperature_min": units["temperature_2m_min"],
                    "precipitation_probability_max": units["precipitation_probability_max"],
                    "precipitation_sum": units["precipitation_sum"],
                },
            }
        except Exception:
            return {"status": "unavailable"}


def build_weather_by_day(trip, adapter, *, today=None):
    """Return one labeled forecast context per day, using only stored formal coordinates."""
    if not isinstance(trip, dict) or adapter is None:
        raise ValueError("trip and weather adapter are required")
    current = today or _local_today()
    if not isinstance(current, date):
        raise ValueError("today must be a date")
    latest = current + timedelta(days=15)
    result = {}
    for day in trip["days"]:
        target = date.fromisoformat(day["date"])
        common = {
            "forecast_date": day["date"],
            "source": _SOURCE,
            "attribution": _ATTRIBUTION,
        }
        if target < current or target > latest:
            result[day["id"]] = {**common, "status": "outside_forecast"}
            continue
        place = next(_day_places(trip, day), None)
        if place is None:
            result[day["id"]] = {**common, "status": "location_unknown"}
            continue
        forecast = adapter.forecast(place["location"], target)
        result[day["id"]] = {
            **common,
            "place_id": place["id"],
            "place_name": place["name"],
            **forecast,
        }
    return result
