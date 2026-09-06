"""Transient facility recommendations and one explicitly chosen schedule addition."""
import copy
import json
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from Sources.aig_candidate_recommendation import recommend
from Sources.place_acquisition import FacilityQuery, valid_field
from scripts.validate_trip import validate_value, semantic_errors
from .errors import ConflictError, NotFoundError, ValidationError


def _day(trip, day_id):
    day = next((d for d in trip["days"] if d["id"] == day_id), None)
    if day is None:
        raise NotFoundError("schedule day not found")
    return day


def _query(query):
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ValidationError("search conditions must contain 1 to 500 characters")
    return query  # Preserve the original verbatim, including whitespace.


def search(domain, trip_id, day_id, query, adapter, transport, search_queries=None):
    query = _query(query)
    trip = domain.get_effective_trip(trip_id)
    day = _day(trip, day_id)
    queries = search_queries if search_queries is not None else [FacilityQuery(query, day["routeSummary"] or "")]
    if (not isinstance(queries, list) or not 1 <= len(queries) <= 3
            or any(not isinstance(q, FacilityQuery) for q in queries)):
        raise ValidationError("provide one to three facility queries")
    result = dict(trip_id=trip_id, day_id=day_id, query=query,
                  area=day["routeSummary"], status="no_candidates", candidates=[],
                  reason="", unverified_conditions=[], failure_code=None)
    gathered, evidence, seen = [], [], set()
    try:
        for search_query in queries:
            acquisition = adapter.search(search_query)
            if acquisition.status not in {"candidates", "no_candidates"}:
                # Do not continue sending queries after provider failure/cooldown.
                result.update(status="search_failed")
                return result
            for candidate in acquisition.candidates:
                fields = {k: copy.deepcopy(v) for k, v in candidate.persistable.items() if valid_field(k, v)}
                temporary = candidate.temporary
                name = fields.get("name") or temporary.get("name")
                if not isinstance(name, str) or not name.strip():
                    continue
                # Exact evidence identity only; names alone do not merge branches.
                key = json.dumps([fields, temporary.get("source"), temporary.get("provider_id")], sort_keys=True)
                if key in seen:
                    continue
                seen.add(key)
                if len(evidence) == 10:
                    break
                identity = f"candidate-{len(evidence) + 1}"
                item = dict(id=identity, name=name, snippet=temporary.get("description", ""),
                            url=(fields.get("urls") or [temporary.get("source", "")])[0])
                if fields.get("address"):
                    item["address"] = fields["address"]
                if fields.get("location"):
                    item.update(fields["location"])
                # Region is evidence only when the adapter supplies it, never the requested area.
                if isinstance(temporary.get("region"), str):
                    item["region"] = temporary["region"]
                evidence.append(item)
                gathered.append(dict(id=identity, name=name, fields=fields,
                                     context={k: copy.deepcopy(v) for k, v in temporary.items()
                                              if k in {"source", "retrieved_at", "license", "attribution", "expires", "description"}},
                                     selectable="name" in fields))
            if len(evidence) == 10:
                break
    except Exception:
        result.update(status="search_failed")
        return result
    recommendation = recommend(query, evidence, transport)
    result.update(reason=recommendation["reason"],
                  unverified_conditions=recommendation["unverified_conditions"],
                  failure_code=recommendation["failure_code"])
    if recommendation["status"] == "failed":
        result["status"] = "recommendation_failed"
    else:
        by_id = {c["id"]: c for c in gathered}
        result["candidates"] = [by_id[i] for i in recommendation["recommended_ids"]]
        result["status"] = "recommendations" if result["candidates"] else "no_candidates"
    return result


def _normalize(value):
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def add(domain, command_id, trip_id, day_id, values, result, selected_ids, confirmed):
    """Internal caller holds the unmodified search result; UI supplies IDs only."""
    domain._require_text(command_id, "command_id")
    if confirmed is not True:
        raise ValidationError("explicit schedule confirmation is required")
    if (not isinstance(result, dict) or result.get("trip_id") != trip_id or result.get("day_id") != day_id):
        raise ValidationError("recommendation target mismatch")
    query = _query(result.get("query"))
    if (not isinstance(selected_ids, list) or len(selected_ids) > 3
            or any(not isinstance(i, str) for i in selected_ids) or len(set(selected_ids)) != len(selected_ids)):
        raise ValidationError("select zero to three distinct recommendations")
    candidates = result.get("candidates", [])
    if not isinstance(candidates, list) or len(candidates) > 3:
        raise ValidationError("invalid recommendation set")
    by_id = {c["id"]: c for c in candidates}
    if not set(selected_ids) <= set(by_id) or (selected_ids and result.get("status") != "recommendations"):
        raise ValidationError("selection must belong to the displayed recommendations")
    if (not isinstance(values, dict) or set(values) - {"title", "category", "start", "end", "normal_comment"}
            or not isinstance(values.get("title"), str) or not values["title"].strip()
            or not isinstance(values.get("category"), str)
            or values.get("category") not in {"sightseeing", "food", "accommodation"}):
        raise ValidationError("schedule title and category are required")
    identity = lambda kind, suffix: kind + "-" + uuid5(NAMESPACE_URL, f"calendar:conditioned:{trip_id}:{command_id}:{suffix}").hex
    item_id = identity("item", "item")
    with domain._command() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if domain._journal_path(trip_id).exists():
            raise ConflictError("pending Trip adoption must be recovered before adding a schedule")
        effective = domain.get_effective_trip(trip_id)
        day = _day(effective, day_id)
        if day["routeSummary"] != result.get("area"):
            raise ConflictError("search area has changed; search again")
        if domain._item_matches(effective, item_id):
            raise ConflictError("this schedule addition was already saved")
        selected = []
        places = []
        for candidate_id in selected_ids:
            fields = by_id[candidate_id]["fields"]
            if (not isinstance(fields, dict) or "name" not in fields
                    or any(not valid_field(k, v) for k, v in fields.items())):
                raise ValidationError("candidate has no persistable Place or invalid fields")
            place = dict(id=identity("place", candidate_id), name=fields["name"], summary=None,
                         category="other", address=None, location=None, urls=[], rating=None)
            place.update(copy.deepcopy(fields))
            places.append(place)
            selected.append(place["id"])
        start, end = values.get("start"), values.get("end")
        if end is not None and (start is None or not isinstance(start, str)
                                or not isinstance(end, str) or end < start):
            raise ValidationError("schedule end requires a start and cannot precede it")
        item = dict(id=item_id, dayId=day_id,
                    order=1 + max([i["order"] for i in day["scheduleItems"]] +
                                  [t["order"] for t in effective["transports"] if t["dayId"] == day_id] + [-1]),
                    status="undecided",
                    action=values["title"], category=values["category"], summary=values.get("normal_comment"), details=[],
                    time=dict(mode="fixed" if start is not None else "undecided", start=start, end=end, durationMinutes=None),
                    searchQuery=query,
                    placeSelection=dict(candidatePlaceIds=selected, selection=selected if len(selected) == 1 else [],
                                        minSelections=None, maxSelections=None))
        for existing in day["scheduleItems"]:
            same_slot = existing["time"]["start"] == start and existing["time"]["end"] == end
            same_title = _normalize(existing["action"]) == _normalize(item["action"])
            existing_places = [p for p in effective["places"] if p["id"] in existing["placeSelection"]["selection"]]
            same_place = len(places) == 1 and any(
                bool(set(places[0]["urls"]) & set(p["urls"]))
                or (_normalize(places[0]["name"]) == _normalize(p["name"])
                    and any(places[0].get(k) and places[0][k] == p.get(k)
                            for k in ("address", "location"))) for p in existing_places)
            if same_slot and (same_title or same_place):
                raise ConflictError("an obvious duplicate schedule exists in this day")
        additions = [(trip_id, "/places/@" + p["id"], p) for p in places]
        additions.append((day_id, "/scheduleItems/@" + item_id, item))
        for target, path, value in additions:
            domain._apply_value(effective, target, path, value)
        if validate_value(effective, domain._trip_schema) + semantic_errors(effective):
            raise ValidationError("schedule addition would create an invalid Trip")
        for target, path, value in additions:
            domain._store_trip_fields(connection, command_id, trip_id, target,
                                      {value["id"]: value}, {value["id"]: path})
    return dict(trip_id=trip_id, source_item_id=item_id, status="added",
                trip=domain.get_effective_trip(trip_id), view=domain.get_trip_detail_view(trip_id))


def unresolved(domain, trip_id):
    trip = domain.get_effective_trip(trip_id)
    return [dict(trip_id=trip_id, day_id=day["id"], source_item_id=item["id"], query=item["searchQuery"],
                 title=item["action"], category=item["category"],
                 candidate_place_ids=copy.deepcopy(item["placeSelection"]["candidatePlaceIds"]))
            for day in trip["days"] for item in day["scheduleItems"]
            if item.get("searchQuery") and not item["placeSelection"]["selection"]]
