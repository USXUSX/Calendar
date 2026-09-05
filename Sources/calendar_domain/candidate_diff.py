"""Limited, deterministic review signals; not a complete intent validator."""

import json
from typing import Any


_FIELDS = {
    "scheduleItem": {
        "status": ("status",), "start": ("time", "start"),
        "end": ("time", "end"), "time_mode": ("time", "mode"),
        "title": ("action",), "normal_comment": ("summary",),
    },
    "transport": {
        "status": ("status",), "start": ("time", "start"),
        "end": ("time", "end"), "time_mode": ("time", "mode"),
    },
}
_MISSING = object()


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))


def _items(trip: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    result = {}
    groups = [("scheduleItem", d["scheduleItems"]) for d in trip["days"]]
    groups.append(("transport", trip["transports"]))
    for source_type, items in groups:
        for item in items:
            identity = item["id"]
            if not isinstance(identity, str) or not identity:
                raise ValueError("invalid diff input")
            key = (source_type, identity)
            if key in result:
                raise ValueError("invalid diff input")
            result[key] = item
    return result


def candidate_review_rules(
    baseline: dict[str, Any], working: dict[str, Any], candidate: dict[str, Any],
) -> tuple[str, ...]:
    """Return only fixed rule names; raise on unevaluable structured intent.

    Inputs come from the frozen generation package and CAL-validated candidate.
    No model calls, repair, array-index matching, or persistence is performed.
    """
    before, after = _items(baseline), _items(candidate)
    deletions = set()
    seen = set()
    mismatch = False
    changes = working["item_changes"]
    if not isinstance(changes, list):
        raise ValueError("invalid diff input")
    for change in changes:
        source_type, identity = change["source_type"], change["source_item_id"]
        key = (source_type, identity)
        fields = change["changes"]
        disposition = change["disposition"]
        if (source_type not in _FIELDS or key not in before or key in seen
                or not isinstance(fields, dict) or set(fields) - _FIELDS[source_type].keys()
                or disposition not in {"changed", "pending_delete"}):
            raise ValueError("invalid diff input")
        seen.add(key)
        # Also reject non-JSON intent values rather than silently skipping them.
        _json(fields)
        if disposition == "pending_delete":
            deletions.add(key)
            mismatch |= key in after
            continue
        if not fields:
            raise ValueError("invalid diff input")
        if key not in after:
            mismatch = True
            continue
        for field, expected in fields.items():
            actual = after[key]
            for part in _FIELDS[source_type][field]:
                actual = actual.get(part, _MISSING) if isinstance(actual, dict) else _MISSING
            mismatch |= actual is _MISSING or _json(actual) != _json(expected)

    rules = []
    if mismatch:
        rules.append("EXPLICIT_INTENT_MISMATCH")
    if _json(baseline["summary"]) != _json(candidate["summary"]):
        rules.append("TRIP_SUMMARY_CHANGED")
    if before.keys() - after.keys() - deletions:
        rules.append("UNREQUESTED_ITEM_REMOVAL")
    return tuple(rules)
