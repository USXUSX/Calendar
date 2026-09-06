"""CAL target binding and persistable-only enrichment candidates; never writes."""
import copy

from Sources.place_acquisition import FacilityQuery, valid_field
from .errors import ConflictError, NotFoundError, ValidationError


def target_input(domain, trip_id, target):
    if not isinstance(target, dict) or set(target) not in ({"place_id"}, {"temporary_id"}):
        raise ValidationError("one Place or temporary item identity is required")
    identity = next(iter(target.values()))
    if not isinstance(identity, str) or not identity:
        raise ValidationError("invalid enrichment identity")
    effective = domain.get_effective_trip(trip_id)
    if "place_id" in target:
        place = next((p for p in effective["places"] if p["id"] == identity), None)
        if place is None:
            raise NotFoundError("enrichment Place not found")
        return {key: copy.deepcopy(place[key]) for key in ("name", "address", "location", "urls")}
    working = domain.get_working_trip(trip_id)
    record = next((r for r in working["state"]["temporary_items"] if r["temporary_id"] == identity), None)
    if record is None:
        raise NotFoundError("enrichment temporary item not found")
    name = record["values"].get("place_name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("temporary place_name is required")
    return {"name": name, "address": None, "location": None, "urls": []}


def acquire(domain, trip_id, target, adapter, area):
    original = target_input(domain, trip_id, target)
    try:
        query = FacilityQuery(original["name"], area, original["address"] or "")
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("invalid facility hints") from error
    result = {"trip_id": trip_id, "target": copy.deepcopy(target), "input": original,
              "status": "unavailable", "candidates": []}
    try:
        acquisition = adapter.search(query)
        if acquisition.status == "no_candidates":
            result["status"] = "no_candidates"
        elif acquisition.status == "candidates":
            for candidate in acquisition.candidates[:5]:
                fields = {k: copy.deepcopy(v) for k, v in candidate.persistable.items()
                          if valid_field(k, v)}
                # Metadata is a separate transient envelope, never a Place payload.
                result["candidates"].append({"fields": fields,
                                             "context": {k: copy.deepcopy(v) for k, v in candidate.temporary.items()
                                                         if k in {"source", "retrieved_at", "license", "attribution",
                                                                  "expires", "description", "area_hint_matches",
                                                                  "address_hint_matches"}}})
            result["status"] = "ambiguous" if len(result["candidates"]) > 1 else (
                "confirmation_required" if result["candidates"] else "no_candidates")
    except Exception:
        result["status"], result["candidates"] = "unavailable", []
    return result


def prepare(domain, trip_id, target, result, candidate_index, confirmed):
    """Explicit identity confirmation yields only missing fields for existing adoption.

    Internal caller passes the unmodified acquisition result, not untrusted UI JSON.
    No provider metadata or fields with unknown persistence permission are copied.
    """
    if confirmed is not True:
        raise ValidationError("facility identity confirmation is required")
    if (not isinstance(result, dict) or result.get("trip_id") != trip_id
            or result.get("target") != target):
        raise ValidationError("enrichment target mismatch")
    original = target_input(domain, trip_id, target)
    if result.get("input") != original:
        raise ConflictError("enrichment input has changed")
    candidates = result.get("candidates", [])
    if (result.get("status") not in {"ambiguous", "confirmation_required"}
            or type(candidate_index) is not int or not 0 <= candidate_index < len(candidates)):
        raise ValidationError("invalid enrichment selection")
    fields = candidates[candidate_index]["fields"]
    if not isinstance(fields, dict) or any(not valid_field(k, v) for k, v in fields.items()):
        raise ValidationError("invalid enrichment fields")
    payload = {k: copy.deepcopy(v) for k, v in fields.items()
               if k in {"address", "location", "urls"} and not original[k]}
    return {"trip_id": trip_id, "target": copy.deepcopy(target),
            "status": "ready" if payload else "unfilled", "fields": payload}
