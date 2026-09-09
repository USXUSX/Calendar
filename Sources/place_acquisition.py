"""Reusable, read-only facility acquisition. No CAL storage or Trip inputs."""
from __future__ import annotations

import gzip
import json
import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from email.utils import parsedate_to_datetime


def valid_field(key, value):
    if key in {"name", "address"}:
        return isinstance(value, str) and bool(value.strip()) and len(value) <= 500
    if key == "officialUrl":
        return isinstance(value, str) and valid_field("urls", [value])
    if key == "urls":
        return (isinstance(value, list) and bool(value) and len(value) <= 5
                and all(isinstance(u, str) and len(u) <= 2048
                        and u.startswith("https://") and urlsplit(u).hostname
                        and not urlsplit(u).username and not any(c.isspace() for c in u)
                        for u in value) and len(set(value)) == len(value))
    if key == "location":
        return (isinstance(value, dict) and set(value) == {"latitude", "longitude"}
                and all(type(value[k]) in (int, float) and math.isfinite(value[k])
                        and abs(value[k]) <= bound
                        for k, bound in (("latitude", 90), ("longitude", 180))))
    return False


@dataclass(frozen=True)
class FacilityQuery:
    name: str
    area: str = ""
    address: str = ""

    def __post_init__(self):
        if (any(not isinstance(v, str) or len(v) > 500
                for v in (self.name, self.area, self.address)) or not self.name.strip()):
            raise ValueError("invalid facility query")


@dataclass
class FacilityCandidate:
    # Only adapter-reviewed fields enter this mapping; default deny elsewhere.
    persistable: dict = field(default_factory=dict)
    temporary: dict = field(default_factory=dict)
    # Explicit permission for short comment extraction, never inferred from temporary.
    comment_evidence: list[dict] = field(default_factory=list)


@dataclass
class Acquisition:
    status: str
    candidates: list[FacilityCandidate] = field(default_factory=list)


class FacilityAdapter(Protocol):
    def search(self, query: FacilityQuery) -> Acquisition: ...


class WikidataAdapter:
    """CC0 structured values only. Up to 5 hits, two serial requests, no retry/cache.

    A hit is never an assertion of facility identity, even for an exact name.
    area/address are local comparison hints, not blindly appended to label search.
    """
    endpoint = "https://www.wikidata.org/w/api.php"
    user_agent = "Calendar/0.1 (https://github.com/USXUSX/Calendar)"

    def __init__(self, *, transport=None, timeout=10, include_comment_evidence=False):
        if not 0 < timeout <= 30:
            raise ValueError("timeout must be between 0 and 30 seconds")
        self.include_comment_evidence = include_comment_evidence
        self.timeout = timeout
        self.transport = transport or self._http
        self._next_request = 0.0
        self._blocked_until = 0.0

    def _http(self, params):
        # Serial interactive use; a fresh instance must not be used to bypass limits.
        delay = self._next_request - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        request = Request(self.endpoint + "?" + urlencode(params), headers={
            "User-Agent": self.user_agent, "Accept": "application/json",
            "Accept-Encoding": "gzip",
        })
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError("response too large")
                if response.headers.get("Content-Encoding") == "gzip":
                    import io
                    with gzip.GzipFile(fileobj=io.BytesIO(payload)) as stream:
                        payload = stream.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError("response too large")
                return json.loads(payload)
        except HTTPError as error:
            if error.code in {429, 503}:
                retry_after = error.headers.get("Retry-After", "60")
                try:
                    seconds = float(retry_after)
                except ValueError:
                    try:
                        seconds = parsedate_to_datetime(retry_after).timestamp() - time.time()
                    except (ValueError, TypeError):
                        seconds = 60
                self._blocked_until = time.monotonic() + max(60, seconds)
            raise
        finally:
            self._next_request = time.monotonic() + 1

    def _get(self, **params):
        if time.monotonic() < self._blocked_until:
            raise ValueError("provider cooling down")
        value = self.transport(dict(params, format="json", maxlag=5))
        if isinstance(value, dict) and "error" in value:
            self._blocked_until = time.monotonic() + 60
        if not isinstance(value, dict) or "error" in value:
            raise ValueError("acquisition failed")
        return value

    @staticmethod
    def _values(entity, prop):
        statements = entity.get("claims", {}).get(prop, [])
        statements = [s for s in statements if s.get("rank") != "deprecated"
                      and not s.get("qualifiers")]
        preferred = [s for s in statements if s.get("rank") == "preferred"]
        return [s["mainsnak"]["datavalue"]["value"] for s in preferred or statements
                if s.get("mainsnak", {}).get("snaktype") == "value"]

    def search(self, query):
        try:
            hits = self._get(action="wbsearchentities", search=query.name,
                             language="ja", uselang="ja", type="item", limit=5)["search"]
            ids = list(dict.fromkeys(h["id"] for h in hits
                                    if re.fullmatch(r"Q[1-9][0-9]*", h["id"])))[:5]
            if not ids:
                return Acquisition("no_candidates")
            entities = self._get(action="wbgetentities", ids="|".join(ids),
                                 props="labels|descriptions|claims", languages="ja|en")["entities"]
            candidates = []
            for entity_id in ids:
                entity = entities.get(entity_id, {})
                if "missing" in entity or entity.get("id") != entity_id:
                    continue
                labels = entity.get("labels", {})
                name = (labels.get("ja") or labels.get("en") or {}).get("value")
                fields = {"name": name}
                for prop, key in (("P6375", "address"), ("P625", "location"), ("P856", "urls")):
                    values = self._values(entity, prop)
                    # Conflicting statements do not become an arbitrary first value.
                    if len(values) != 1:
                        continue
                    value = values[0]
                    if key == "address":
                        value = value.get("text") if value.get("language") in {"ja", "en"} else None
                    elif key == "location":
                        value = ({"latitude": value.get("latitude"), "longitude": value.get("longitude")}
                                 if value.get("globe") == "http://www.wikidata.org/entity/Q2" else None)
                    else:
                        value = [value]
                    fields[key] = value
                if valid_field("urls", fields.get("urls")):
                    fields["officialUrl"] = fields["urls"][0]  # Wikidata P856 is the official website.
                fields = {k: v for k, v in fields.items() if valid_field(k, v)}
                if "name" not in fields:
                    continue
                description = (entity.get("descriptions", {}).get("ja") or
                               entity.get("descriptions", {}).get("en") or {}).get("value", "")
                candidates.append(FacilityCandidate(fields, {
                    "provider": "wikidata", "provider_id": entity_id,
                    "source": "https://www.wikidata.org/wiki/" + entity_id,
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "license": "CC0", "attribution": "Wikidata",
                    "expires": "end_of_operation", "cache": "none",
                    "description": description,
                    "area_hint_matches": bool(query.area and query.area in description),
                    "address_hint_matches": bool(query.address and query.address == fields.get("address")),
                }))
            if self.include_comment_evidence:
                self._add_comment_evidence(candidates, entities)
            return Acquisition("candidates" if candidates else "no_candidates", candidates)
        except Exception:
            # Provider error text/body/query is never surfaced or persisted.
            return Acquisition("unavailable")


    def _add_comment_evidence(self, candidates, entities):
        # Whole qualified property is omitted: do not strip seasonal/holiday exceptions.
        facts, ids = {}, []
        for candidate in candidates:
            entity = entities[candidate.temporary["provider_id"]]
            rows = []
            for prop, label in (("P3025", "営業曜日（営業期間内）"), ("P3026", "休業日")):
                statements = [s for s in entity.get("claims", {}).get(prop, [])
                              if s.get("rank") != "deprecated"]
                if any(s.get("qualifiers") or s.get("mainsnak", {}).get("snaktype") != "value"
                       for s in statements):
                    continue
                values = self._values(entity, prop)
                refs = [v.get("id") for v in values if isinstance(v, dict)]
                if len(refs) != len(values) or any(not isinstance(v, str) or not re.fullmatch(r"Q[1-9][0-9]*", v) for v in refs):
                    continue
                if refs:
                    rows.append((label, refs))
                    ids.extend(refs)
            facts[candidate.temporary["provider_id"]] = rows
        ids = list(dict.fromkeys(ids))
        # Bound the extra label lookup as one request; no truncation of a property's facts.
        labels = self._get(action="wbgetentities", ids="|".join(ids), props="labels", languages="ja|en").get("entities", {}) if 0 < len(ids) <= 50 else {}
        for candidate in candidates:
            context = candidate.temporary
            texts = []
            description = context.get("description")
            if isinstance(description, str) and description.strip() and len(description) <= 1000:
                texts.append(description)
            for label, refs in facts[context["provider_id"]]:
                names = []
                for ref in refs:
                    data = labels.get(ref, {})
                    choices = data.get("labels", {}) if data.get("id") == ref else {}
                    names.append((choices.get("ja") or choices.get("en") or {}).get("value"))
                if all(isinstance(n, str) and n.strip() for n in names):
                    text = label + ": " + "、".join(names)
                    if len(text) <= 1000:
                        texts.append(text)
            candidate.comment_evidence = [dict(text=t, source=context["source"],
                retrieved_at=context["retrieved_at"], license="CC0", attribution="Wikidata",
                storage_allowed=True) for t in texts]
