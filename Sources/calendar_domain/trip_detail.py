"""Pure Trip-detail display and local-update contracts.

The builders in this module do not read or write storage.  They transform an
effective Trip plus explicitly supplied temporary/context data into the model
required by the confirmed Phase 1 UI.
"""

from __future__ import annotations

import copy
from typing import Any

from .errors import ValidationError


_CATEGORY_ICON_KEYS = {
    "sightseeing": "sightseeing",
    "food": "food",
    "accommodation": "accommodation",
    "transport": "transport",
}
_DIRECT_EDIT_PATHS = {
    "status": "/status",
    "start": "/time/start",
    "end": "/time/end",
    "time_mode": "/time/mode",
    "title": "/action",
    "normal_comment": "/summary",
}


def _time_label(value: dict[str, Any]) -> str:
    if value["mode"] == "undecided":
        return "未定"
    start = value["start"][1:] if value["start"].startswith("0") else value["start"]
    if value["end"] is None:
        return start
    end = value["end"][1:] if value["end"].startswith("0") else value["end"]
    return f"{start}–{end}"


def _candidate_places(
    item: dict[str, Any], places: dict[str, dict[str, Any]], judgments: dict[str, Any]
) -> list[dict[str, Any]]:
    selection = item.get("placeSelection")
    if not selection:
        return []
    result = []
    item_judgments = judgments.get(item["id"], {})
    if not isinstance(item_judgments, dict):
        raise ValidationError("candidate judgments must be grouped by source item id")
    for index, place_id in enumerate(selection["candidatePlaceIds"], 1):
        judgment = item_judgments.get(place_id)
        if judgment not in {None, "ok", "ng"}:
            raise ValidationError("candidate judgment must be ok, ng, or null")
        place = places[place_id]
        result.append({
            "number": index,
            "place_id": place_id,
            "name": place["name"],
            "url": place["urls"][0] if place["urls"] else None,
            "selected_in_base": place_id in selection["selection"],
            "judgment": judgment,
        })
    return result


def _important_comments(
    item: dict[str, Any], bookings: list[dict[str, Any]]
) -> list[str]:
    booking_ids = {item.get("bookingId")} if item.get("bookingId") else set()
    selection = item.get("placeSelection")
    selected_places = set(selection["selection"]) if selection else set()
    comments = []
    for booking in bookings:
        if booking["id"] in booking_ids or booking.get("placeId") in selected_places:
            if booking["notes"]:
                comments.append(booking["notes"])
    return comments


def _entry(
    item: dict[str, Any], source_type: str, places: dict[str, dict[str, Any]],
    bookings: list[dict[str, Any]], judgments: dict[str, Any],
) -> dict[str, Any]:
    if source_type == "scheduleItem":
        title = item["action"]
        category = item["category"]
        place_ids = item["placeSelection"]["selection"]
        normal_comment = item["summary"]
        supporting_details = copy.deepcopy(item["details"])
    else:
        from_place = places[item["fromPlaceId"]]
        to_place = places[item["toPlaceId"]]
        title = f"{from_place['name']}から{to_place['name']}へ移動"
        category = "transport"
        place_ids = [item["fromPlaceId"], item["toPlaceId"]]
        normal_comment = None
        supporting_details = []
    candidates = _candidate_places(item, places, judgments)
    return {
        "source_type": source_type,
        "source_item_id": item["id"],
        "order": item["order"],
        "time": {"label": _time_label(item["time"]), **copy.deepcopy(item["time"])},
        "category": category,
        "category_icon_key": _CATEGORY_ICON_KEYS[category],
        "title": title,
        "places": [
            {"id": place_id, "name": places[place_id]["name"],
             "url": places[place_id]["urls"][0] if places[place_id]["urls"] else None}
            for place_id in place_ids
        ],
        "status": item["status"],
        "has_candidates": len(candidates) > 1,
        "candidates": candidates,
        "normal_comment": normal_comment,
        "important_comments": _important_comments(item, bookings),
        "supporting_details": supporting_details,
        "direct_edit_paths": copy.deepcopy(_DIRECT_EDIT_PATHS if source_type == "scheduleItem" else {
            "status": "/status", "start": "/time/start", "end": "/time/end", "time_mode": "/time/mode"
        }),
        "ai_local_update_target": {"source_type": source_type, "source_item_id": item["id"]},
    }


def build_trip_detail_view(
    effective_trip: dict[str, Any], *, candidate_judgments: dict[str, Any] | None = None,
    weather_by_day: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the confirmed compact-timeline model without creating a new authority."""
    judgments = candidate_judgments or {}
    weather = weather_by_day or {}
    places = {item["id"]: item for item in effective_trip["places"]}
    transports = {item["id"]: item for item in effective_trip["transports"]}
    days = []
    for day in effective_trip["days"]:
        entries = [
            _entry(item, "scheduleItem", places, effective_trip["bookings"], judgments)
            for item in day["scheduleItems"]
        ]
        entries.extend(
            _entry(transports[item_id], "transport", places, effective_trip["bookings"], judgments)
            for item_id in day["transportIds"]
        )
        days.append({
            "day_id": day["id"], "date": day["date"], "title": day["title"],
            "route_summary": day["routeSummary"], "weather": copy.deepcopy(weather.get(day["id"])),
            "entries": sorted(entries, key=lambda value: (value["order"], value["source_item_id"])),
        })
    return {
        "trip_id": effective_trip["id"], "title": effective_trip["title"],
        "date_range": copy.deepcopy(effective_trip["dateRange"]), "days": days,
        "temporary_input": {"candidate_judgments": copy.deepcopy(judgments)},
    }


def build_local_ai_update_request(
    effective_trip: dict[str, Any], source_type: str, source_item_id: str, instruction: str
) -> dict[str, Any]:
    """Create a target-scoped request; this does not enqueue whole-Trip regeneration."""
    if source_type not in {"scheduleItem", "transport"}:
        raise ValidationError("local AI updates require a scheduleItem or transport target")
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValidationError("local AI update instruction must be non-empty")
    matches = []
    values = effective_trip["transports"] if source_type == "transport" else [
        item for day in effective_trip["days"] for item in day["scheduleItems"]
    ]
    matches = [item for item in values if item["id"] == source_item_id]
    if len(matches) != 1:
        raise ValidationError("local AI update target does not exist or is not unique")
    return {
        "kind": "trip_item_local_update", "trip_id": effective_trip["id"],
        "target": {"source_type": source_type, "source_item_id": source_item_id},
        "instruction": instruction.strip(), "current_target": copy.deepcopy(matches[0]),
        "result_contract": "semantic_field_changes",
    }
