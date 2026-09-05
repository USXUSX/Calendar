#!/usr/bin/env python3
"""Validate one or more Calendar trip JSON files without external packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCHEMA = ROOT / "Schemas" / "trip.schema.json"


def type_matches(value: Any, expected: str) -> bool:
    return {
        "null": value is None,
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
    }[expected]


def schema_errors(value: Any, rule: dict[str, Any], root: dict[str, Any], path: str = "$") -> list[str]:
    if "$ref" in rule:
        target: Any = root
        for part in rule["$ref"].removeprefix("#/").split("/"):
            target = target[part]
        return schema_errors(value, target, root, path)
    if "anyOf" in rule:
        alternatives = [schema_errors(value, item, root, path) for item in rule["anyOf"]]
        return [] if any(not errors for errors in alternatives) else [f"{path}: does not match any allowed shape"]

    errors: list[str] = []
    expected = rule.get("type")
    if expected:
        expected_types = expected if isinstance(expected, list) else [expected]
        if not any(type_matches(value, item) for item in expected_types):
            return [f"{path}: expected {' or '.join(expected_types)}"]
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{path}: value is not in the allowed list")
    if isinstance(value, str):
        if len(value) < rule.get("minLength", 0):
            errors.append(f"{path}: string is too short")
        # JSON Schema `pattern` uses search semantics; anchors in the Schema
        # decide whether a prefix or the whole value must match.
        if rule.get("pattern") and not re.search(rule["pattern"], value):
            errors.append(f"{path}: string does not match {rule['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{path}: value is below minimum")
        if "maximum" in rule and value > rule["maximum"]:
            errors.append(f"{path}: value is above maximum")
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            errors.append(f"{path}: array has too few items")
        if rule.get("uniqueItems") and len({json.dumps(item, sort_keys=True, ensure_ascii=False) for item in value}) != len(value):
            errors.append(f"{path}: array items must be unique")
        if "items" in rule:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, rule["items"], root, f"{path}[{index}]"))
    if isinstance(value, dict):
        required = set(rule.get("required", []))
        for key in sorted(required - value.keys()):
            errors.append(f"{path}: missing required property {key}")
        properties = rule.get("properties", {})
        if rule.get("additionalProperties") is False:
            for key in sorted(value.keys() - properties.keys()):
                errors.append(f"{path}: unexpected property {key}")
        for key, item in value.items():
            if key in properties:
                errors.extend(schema_errors(item, properties[key], root, f"{path}.{key}"))
    return errors


def unique_ids(items: list[dict[str, Any]], label: str, errors: list[str]) -> set[str]:
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        errors.append(f"$: duplicate {label} id")
    return set(ids)


def semantic_errors(trip: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        start = date.fromisoformat(trip["dateRange"]["start"])
        end = date.fromisoformat(trip["dateRange"]["end"])
        if start > end:
            errors.append("$.dateRange: start must not be after end")
        for index, day in enumerate(trip["days"]):
            current = date.fromisoformat(day["date"])
            if not start <= current <= end:
                errors.append(f"$.days[{index}].date: outside dateRange")
    except (KeyError, TypeError, ValueError):
        return errors

    days = unique_ids(trip["days"], "Day", errors)
    places = unique_ids(trip["places"], "Place", errors)
    transports = unique_ids(trip["transports"], "Transport", errors)
    bookings = unique_ids(trip["bookings"], "Booking", errors)
    unique_ids(trip["preparation"]["tasks"], "Preparation task", errors)
    unique_ids(trip["rioPlan"]["packingItems"], "Rio packing item", errors)
    schedule_items = [item for day in trip["days"] for item in day["scheduleItems"]]
    unique_ids(schedule_items, "ScheduleItem", errors)

    transport_by_id = {item["id"]: item for item in trip["transports"]}
    for label, values in (
        ("Preparation dueDate", [item["dueDate"] for item in trip["preparation"]["tasks"]]),
        ("Booking targetDate", [item["targetDate"] for item in trip["bookings"]]),
        ("rating observedAt", [item["rating"]["observedAt"] for item in trip["places"] if item["rating"] is not None]),
    ):
        for value in values:
            try:
                date.fromisoformat(value)
            except ValueError:
                errors.append(f"$: invalid calendar date in {label}")

    for index, entry in enumerate(schedule_items + trip["transports"]):
        time = entry["time"]
        base = f"$: TimeSpec {index}"
        if time["mode"] == "fixed" and time["start"] is None:
            errors.append(f"{base}: fixed time requires start")
        if time["mode"] == "range" and (time["start"] is None or time["end"] is None):
            errors.append(f"{base}: range time requires start and end")
        if time["mode"] == "undecided" and (time["start"] is not None or time["end"] is not None):
            errors.append(f"{base}: undecided time requires null start and end")

    for day_index, day in enumerate(trip["days"]):
        entries = list(day["scheduleItems"]) + [transport_by_id[item_id] for item_id in day["transportIds"] if item_id in transport_by_id]
        orders = [item["order"] for item in entries]
        if len(orders) != len(set(orders)):
            errors.append(f"$.days[{day_index}]: order must be unique across schedules and transports")
        for item_index, item in enumerate(day["scheduleItems"]):
            base = f"$.days[{day_index}].scheduleItems[{item_index}]"
            if item["dayId"] != day["id"]:
                errors.append(f"{base}.dayId: must match parent Day")
            selection = item["placeSelection"]
            candidates = set(selection["candidatePlaceIds"])
            selected = set(selection["selection"])
            if not candidates <= places:
                errors.append(f"{base}.placeSelection: unknown candidate Place id")
            if not selected <= candidates:
                errors.append(f"{base}.placeSelection.selection: must be a subset of candidates")
            minimum, maximum = selection["minSelections"], selection["maxSelections"]
            if minimum is not None and maximum is not None and minimum > maximum:
                errors.append(f"{base}.placeSelection: minSelections exceeds maxSelections")
            if maximum is not None and maximum > len(candidates):
                errors.append(f"{base}.placeSelection: maxSelections exceeds candidate count")
        for item_id in day["transportIds"]:
            if item_id not in transports:
                errors.append(f"$.days[{day_index}].transportIds: unknown Transport id")
            elif transport_by_id[item_id]["dayId"] != day["id"]:
                errors.append(f"$.days[{day_index}].transportIds: Transport belongs to another Day")

    for index, item in enumerate(trip["transports"]):
        base = f"$.transports[{index}]"
        if item["dayId"] not in days:
            errors.append(f"{base}.dayId: unknown Day id")
        if item["fromPlaceId"] not in places or item["toPlaceId"] not in places:
            errors.append(f"{base}: unknown endpoint Place id")
        if item["bookingId"] is not None and item["bookingId"] not in bookings:
            errors.append(f"{base}.bookingId: unknown Booking id")
    for index, booking in enumerate(trip["bookings"]):
        if booking["placeId"] is not None and booking["placeId"] not in places:
            errors.append(f"$.bookings[{index}].placeId: unknown Place id")
        if booking["transportId"] is not None and booking["transportId"] not in transports:
            errors.append(f"$.bookings[{index}].transportId: unknown Transport id")
        if booking["placeId"] is not None and booking["transportId"] is not None:
            errors.append(f"$.bookings[{index}]: use at most one of placeId and transportId")
    for index, place in enumerate(trip["places"]):
        rating = place["rating"]
        expected = {"restaurant": "食べログ", "hotel": "楽天トラベル"}.get(place["category"])
        if rating is not None and expected is not None and rating["source"] != expected:
            errors.append(f"$.places[{index}].rating.source: must be {expected} for this category")
    if not trip["rioPlan"]["applicable"]:
        rio = trip["rioPlan"]
        if rio["careMode"] != "not_applicable" or rio["packingItems"]:
            errors.append("$.rioPlan: non-applicable plan must use not_applicable and an empty packingItems array")
    return errors


def validate(path: Path, schema: dict[str, Any]) -> list[str]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return [f"$: cannot read UTF-8 JSON: {error}"]
    return validate_value(value, schema)


def validate_value(value: Any, schema: dict[str, Any]) -> list[str]:
    return validation_stage_errors(value, schema)[1]


def validation_stage_errors(value: Any, schema: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Use the same ordered checks, with a fixed stage separate from private errors."""
    errors = schema_errors(value, schema, schema)
    if errors:
        return "schema", errors
    if isinstance(value, dict):
        errors = semantic_errors(value)
        if errors:
            return "semantic_reference", errors
    return None, []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()
    with args.schema.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    failed = False
    for path in args.files:
        errors = validate(path, schema)
        if errors:
            failed = True
            print(f"{path}: invalid", file=sys.stderr)
            for error in errors:
                print(f"  {error}", file=sys.stderr)
        else:
            print(f"{path}: valid")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
