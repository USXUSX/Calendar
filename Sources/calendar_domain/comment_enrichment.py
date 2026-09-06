"""Transient evidence, confirmed extraction and a single schedule summary override."""
import copy
from datetime import datetime

from Sources.aig_comment_extraction import extract
from Sources.place_acquisition import FacilityQuery, valid_field
from scripts.validate_trip import validate_value, semantic_errors
from .conditioned_schedule import _schedule, _query
from .errors import ConflictError, NotFoundError, ValidationError


def target_input(domain, trip_id, item_id, place_id):
    trip = domain.get_effective_trip(trip_id)
    day, item = _schedule(trip, item_id)
    if place_id not in item["placeSelection"]["candidatePlaceIds"] + item["placeSelection"]["selection"]:
        raise ValidationError("comment Place must belong to this schedule")
    place = next((p for p in trip["places"] if p["id"] == place_id), None)
    if place is None:
        raise NotFoundError("comment Place not found")
    return copy.deepcopy(dict(day_id=day["id"], area=day["routeSummary"], item=item, place=place))


def permitted(e):
    try:
        stamp = datetime.fromisoformat(e["retrieved_at"])
        return (e.get("storage_allowed") is True and e.get("license") == "CC0"
                and isinstance(e["text"], str) and bool(e["text"].strip()) and len(e["text"]) <= 1000
                and valid_field("urls", [e["source"]]) and stamp.tzinfo is not None
                and isinstance(e["attribution"], str) and 0 < len(e["attribution"]) <= 100)
    except (KeyError, TypeError, ValueError):
        return False


def acquire(domain, trip_id, item_id, place_id, instruction, adapter):
    instruction = _query(instruction)
    original = target_input(domain, trip_id, item_id, place_id)
    output = dict(trip_id=trip_id, source_item_id=item_id, place_id=place_id,
                  instruction=instruction, input=original, status="unavailable", candidates=[])
    place = original["place"]
    try:
        found = adapter.search(FacilityQuery(place["name"], original["area"] or "", place["address"] or ""))
        if found.status == "no_candidates":
            output["status"] = "no_information"
        elif found.status == "candidates":
            for candidate in found.candidates[:5]:
                fields = {k: copy.deepcopy(v) for k, v in candidate.persistable.items() if valid_field(k, v)}
                if not fields.get("name"):
                    continue
                evidence = [copy.deepcopy(e) for e in candidate.comment_evidence if permitted(e)][:8]
                output["candidates"].append(dict(fields=fields, evidence=evidence))
            output["status"] = "confirmation_required" if output["candidates"] else "no_information"
    except Exception:
        output.update(status="unavailable", candidates=[])
    return output


def check(domain, trip_id, item_id, result):
    if not isinstance(result, dict) or result.get("trip_id") != trip_id or result.get("source_item_id") != item_id:
        raise ValidationError("comment target mismatch")
    if target_input(domain, trip_id, item_id, result.get("place_id")) != result.get("input"):
        raise ConflictError("comment target changed; acquire again")


def prepare(domain, trip_id, item_id, acquisition, index, transport, confirmed):
    """Internal caller holds unchanged acquisition; UI supplies index/confirmation only."""
    if confirmed is not True:
        raise ValidationError("facility identity confirmation required")
    check(domain, trip_id, item_id, acquisition)
    candidates = acquisition.get("candidates", [])
    if acquisition.get("status") != "confirmation_required" or type(index) is not int or not 0 <= index < len(candidates):
        raise ValidationError("invalid facility selection")
    evidence = candidates[index]["evidence"]
    if any(not permitted(e) for e in evidence):
        raise ValidationError("comment evidence permission invalid")
    inputs = [dict(id=f"e{n}", text=e["text"]) for n, e in enumerate(evidence)]
    answer = extract(acquisition["instruction"], inputs, transport)
    # A slow extraction does not make an old target eligible for saving.
    check(domain, trip_id, item_id, acquisition)
    output = {k: copy.deepcopy(acquisition[k]) for k in
              ("trip_id", "source_item_id", "place_id", "instruction", "input")}
    output.update(status=answer["status"], text=answer["text"], sources=[], failure_code=answer["failure_code"])
    for identity in answer["evidence_ids"]:
        e = evidence[int(identity[1:])]
        source = {k: e[k] for k in ("source", "retrieved_at", "license", "attribution")}
        if source not in output["sources"]:
            output["sources"].append(source)
    return output


def append(domain, command_id, trip_id, item_id, preview, confirmed):
    """Confirm caller-held preview. Only /summary changes; retry conflicts, never duplicates."""
    domain._require_text(command_id, "command_id")
    if confirmed is not True:
        raise ValidationError("comment preview confirmation required")
    with domain._command() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if domain._journal_path(trip_id).exists():
            raise ConflictError("pending Trip adoption must be recovered before comment append")
        check(domain, trip_id, item_id, preview)
        if preview.get("status") not in {"extracted", "no_information", "failed"}:
            raise ValidationError("invalid comment preview")
        if preview["status"] != "extracted":
            return dict(status=preview["status"], trip_id=trip_id, source_item_id=item_id, updated_fields=[])
        text, sources = preview.get("text"), preview.get("sources")
        if (not isinstance(text, str) or not text.strip() or len(text) > 300
                or not isinstance(sources, list) or not 1 <= len(sources) <= 8
                or any(not permitted(dict(s, text=text, storage_allowed=True)) for s in sources)):
            raise ValidationError("invalid extracted comment or citations")
        instruction = _query(preview.get("instruction"))
        citation = "\n".join(f"出典: {s['attribution']} {s['source']}（取得: {s['retrieved_at']}、{s['license']}）" for s in sources)
        block = f"【{instruction}】\n{text}\n{citation}\n取得時点の情報です。営業日等は訪問前に確認してください。"
        effective = domain.get_effective_trip(trip_id)
        _, item = _schedule(effective, item_id)
        existing = item["summary"]
        value = existing + "\n\n" + block if existing else block
        domain._apply_value(effective, item_id, "/summary", value)
        if validate_value(effective, domain._trip_schema) + semantic_errors(effective):
            raise ValidationError("comment append would create an invalid Trip")
        domain._store_trip_fields(connection, command_id, trip_id, item_id,
                                  {"normal_comment": value}, {"normal_comment": "/summary"})
    return dict(status="appended", trip_id=trip_id, source_item_id=item_id,
                updated_fields=["normal_comment"], trip=domain.get_effective_trip(trip_id),
                view=domain.get_trip_detail_view(trip_id))
