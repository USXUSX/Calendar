"""Resolve CAL location plans through the existing Frame Google Maps connection."""
import json
import urllib.error
import urllib.request

DEFAULT_MAP_CONFIG_URL = "http://127.0.0.1:8080/api/calendar/map-config"
PLACES_URL = "https://places.googleapis.com/v1/places:searchText"
FRAME_REFERRER = "https://frame.usxtools.com/"


def _read_json(response):
    return json.loads(response.read().decode("utf-8"))


def _map_key(map_config_url=DEFAULT_MAP_CONFIG_URL, *, opener=urllib.request.urlopen):
    try:
        with opener(map_config_url, timeout=3) as response:
            data = _read_json(response)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError) as error:
        raise ValueError("map_connection_unavailable") from error
    key = data.get("key") if isinstance(data, dict) else None
    if not isinstance(key, str) or not key:
        raise ValueError("map_connection_unavailable")
    return key


def _search(query, key, *, opener=urllib.request.urlopen):
    body = json.dumps(
        {"textQuery": query, "languageCode": "ja", "maxResultCount": 1},
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        PLACES_URL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": "places.id,places.location",
            "Referer": FRAME_REFERRER,
        },
    )
    try:
        with opener(request, timeout=10) as response:
            data = _read_json(response)
    except (OSError, ValueError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
        return None
    places = data.get("places") if isinstance(data, dict) else None
    first = places[0] if isinstance(places, list) and places else None
    location = first.get("location") if isinstance(first, dict) else None
    if not isinstance(location, dict):
        return None
    latitude, longitude = location.get("latitude"), location.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        return None
    place_id = first.get("id")
    return {
        "location": {"latitude": latitude, "longitude": longitude},
        "googlePlaceId": place_id if isinstance(place_id, str) and place_id else None,
    }


def resolve_location_plan(plan, map_config_url=DEFAULT_MAP_CONFIG_URL, *, opener=urllib.request.urlopen):
    if not isinstance(plan, list):
        raise ValueError("location_plan_required")
    targets = [
        point for point in plan
        if isinstance(point, dict)
        and point.get("location") is None
        and not point.get("skip_search")
    ]
    if not targets:
        return {
            "coordinate_results": {},
            "coordinates": {
                "attempted": 0,
                "filled": 0,
                "missing": 0,
                "existing": sum(
                    isinstance(point, dict) and point.get("location") is not None
                    for point in plan
                ),
            },
        }
    key = _map_key(map_config_url, opener=opener)
    cache = {}
    results = {}
    for point in targets:
        query = point.get("query")
        if not isinstance(query, str) or not query.strip():
            results[point["place_id"]] = None
            continue
        if query not in cache:
            cache[query] = _search(query, key, opener=opener)
        results[point["place_id"]] = cache[query]
    filled = sum(value is not None for value in results.values())
    return {
        "coordinate_results": results,
        "coordinates": {
            "attempted": len(results),
            "filled": filled,
            "missing": len(results) - filled,
            "existing": sum(
                isinstance(point, dict) and point.get("location") is not None
                for point in plan
            ),
        },
    }
