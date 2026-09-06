"""Ephemeral Chat paste interpretation; no persistence or external services."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from uuid import NAMESPACE_URL, uuid5

from .errors import ValidationError


def _value(text):
    text = text.strip()
    return None if text in ("", "未定") else text


def _place(name):
    return {"name": _value(name), "address": None, "location": None, "urls": []}


def check_draft_shape(draft):
    """Reject unknown fields so corrections cannot be silently dropped."""
    def keys(value, expected):
        if not isinstance(value, dict) or set(value) != set(expected.split()):
            raise ValidationError("invalid paste draft fields")

    def string(value, nullable=True):
        if (value is None and nullable) or (isinstance(value, str) and value.strip()):
            return
        raise ValidationError("invalid paste draft text")

    def array(value):
        if not isinstance(value, list):
            raise ValidationError("invalid paste draft array")

    def place(value):
        keys(value, "name address location urls")
        string(value["name"])
        string(value["address"])
        array(value["urls"])
        for url in value["urls"]:
            string(url, False)
        if value["location"] is not None:
            keys(value["location"], "latitude longitude")
        if value["name"] is None and (value["address"] or value["location"] or value["urls"]):
            raise ValidationError("a place with metadata requires a name")

    keys(draft, "title days")
    string(draft["title"])
    array(draft["days"])
    for day in draft["days"]:
        keys(day, "date route_summary items")
        string(day["date"])
        string(day["route_summary"])
        array(day["items"])
        for item in day["items"]:
            if not isinstance(item, dict) or item.get("kind") not in ("schedule", "transport"):
                raise ValidationError("invalid paste item kind")
            common = "kind time status comment "
            keys(item, common + ("title category place candidates" if item["kind"] == "schedule"
                                 else "from_place to_place mode"))
            keys(item["time"], "mode start end durationMinutes")
            string(item["comment"])
            if item["kind"] == "schedule":
                string(item["title"])
                if item["place"] is not None:
                    place(item["place"])
                array(item["candidates"])
                for candidate in item["candidates"]:
                    place(candidate)
            else:
                for field in ("from_place", "to_place"):
                    if item[field] is not None:
                        place(item[field])


def parse_chat_paste(text: str) -> dict:
    """Return an editable, ID-free draft and every uninterpreted source line."""
    if not isinstance(text, str):
        raise ValidationError("paste must be text")
    draft = {"title": None, "days": []}
    unresolved = []
    day = item = place = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"```[A-Za-z0-9_-]*", line):
            continue
        match = re.match(r"^([^:：]+)[:：](.*)$", line)
        reason = "解釈できない行"
        if match:
            label, value = match[1].strip(), match[2].strip()
            if label == "旅行名" and not draft["title"] and not draft["days"]:
                draft["title"] = _value(value)
                continue
            if label == "日付":
                day = {"date": _value(unicodedata.normalize("NFKC", value)),
                       "route_summary": None, "items": []}
                draft["days"].append(day)
                item = place = None
                continue
            if label == "代表エリア" and day is not None and day["route_summary"] is None:
                day["route_summary"] = _value(value)
                continue
            if label in ("予定", "移動"):
                place = None
                item = None
                if day is not None:
                    parts = [part.strip() for part in re.split(r"[|｜]", value)]
                    time = {"mode": "undecided", "start": None, "end": None,
                            "durationMinutes": None}
                    item = {"kind": "schedule" if label == "予定" else "transport",
                            "time": time, "status": "undecided", "comment": None}
                    day["items"].append(item)
                    if label == "予定":
                        item.update(title=_value(parts[1]) if len(parts) > 1 else None,
                                    category=None, place=None, candidates=[])
                    else:
                        route = re.split(r"(?:→|->|➡)", parts[1]) if len(parts) > 1 else []
                        modes = {"徒歩": "walk", "鉄道": "train", "電車": "train",
                                 "バス": "bus", "車": "car", "フェリー": "ferry",
                                 "船": "ferry", "飛行機": "flight", "航空": "flight",
                                 "その他": "other"}
                        item.update(from_place=_place(route[0]) if len(route) == 2 else None,
                                    to_place=_place(route[1]) if len(route) == 2 else None,
                                    mode=modes.get(parts[2]) if len(parts) > 2 else None)
                    clock = unicodedata.normalize("NFKC", parts[0]).replace("〜", "~")
                    clock_match = re.fullmatch(r"(\d{1,2}):([0-5]\d)(?:\s*[~\-]\s*(\d{1,2}):([0-5]\d))?", clock)
                    valid_time = _value(clock) is None
                    if clock_match and int(clock_match[1]) < 24 and (clock_match[3] is None or int(clock_match[3]) < 24):
                        time["start"] = f"{int(clock_match[1]):02}:{clock_match[2]}"
                        if clock_match[3] is not None:
                            time["end"] = f"{int(clock_match[3]):02}:{clock_match[4]}"
                        time["mode"] = "fixed"
                        valid_time = time["end"] is None or time["end"] >= time["start"]
                    expected = 2 if label == "予定" else 3
                    valid_route = label == "予定" or (len(route) == 2 and item["mode"] is not None)
                    if valid_time and len(parts) == expected and valid_route:
                        continue
                    reason = "時刻・項目の区切り・移動経路／手段を確認してください（日跨ぎは推測しません）"
            elif label in ("場所", "候補") and item is not None and item["kind"] == "schedule":
                if label == "候補" or item["place"] is None:
                    place = _place(value)
                    if label == "場所":
                        item["place"] = place
                    else:
                        item["candidates"].append(place)
                    continue
                place = None
            elif label == "コメント" and item is not None:
                if _value(value):
                    item["comment"] = "\n".join(filter(None, [item["comment"], value]))
                continue
            elif label in ("URL", "住所", "座標") and place is not None:
                if _value(value) is None:
                    continue
                if label == "URL" and value.startswith("https://"):
                    if value not in place["urls"]:
                        place["urls"].append(value)
                    continue
                if label == "住所" and place["address"] is None:
                    place["address"] = value
                    continue
                if label == "座標" and place["location"] is None:
                    try:
                        lat, lon = map(float, unicodedata.normalize("NFKC", value).split(","))
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            place["location"] = {"latitude": lat, "longitude": lon}
                            continue
                    except ValueError:
                        pass
                reason = "地点の補足を確認してください"
        unresolved.append({"line": number, "text": raw, "reason": reason})
    return {"draft": draft, "unresolved": unresolved, "requirements": draft_requirements(draft)}


def draft_requirements(draft: dict) -> list[dict]:
    """Return required corrections and optional unknowns without guessing values."""
    results = []

    def add(path, message, required=True):
        results.append({"path": path, "message": message, "required": required})

    if not draft.get("title"):
        add("title", "旅行名が必要です")
    if not draft.get("days"):
        add("days", "日付が必要です")
    for di, day in enumerate(draft.get("days", [])):
        dp = f"days.{di}"
        try:
            value = day.get("date")
            if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError
            date.fromisoformat(value)
        except ValueError:
            add(dp + ".date", "年を含む有効な日付が必要です")
        if not day.get("route_summary"):
            add(dp + ".route_summary", "代表エリアは未定です", False)
        for ii, item in enumerate(day.get("items", [])):
            ip = f"{dp}.items.{ii}"
            start, end = item["time"]["start"], item["time"]["end"]
            if isinstance(start, str) and isinstance(end, str) and end < start:
                add(ip + ".time", "日跨ぎ・時差を推測できないため時刻の補正が必要です")
            if item["time"]["start"] is None:
                add(ip + ".time", "時刻は未定です", False)
            elif item["time"]["end"] is None:
                add(ip + ".time.end", "終了時刻は未定です", False)
            if item["kind"] == "schedule":
                if not item.get("title"):
                    add(ip + ".title", "予定内容が必要です")
                if item.get("category") not in ("sightseeing", "food", "accommodation"):
                    add(ip + ".category", "現行カテゴリ（観光・食事・宿泊）を確認してください")
                places = ([item["place"]] if item.get("place") else []) + item["candidates"]
                if not any(place.get("name") for place in places):
                    add(ip + ".place", "現行Schemaでは場所または候補が1件必要です")
                for pi, place in enumerate(item["candidates"]):
                    if not place.get("name"):
                        add(f"{ip}.candidates.{pi}.name", "候補名が必要です")
            else:
                for field in ("from_place", "to_place"):
                    if not item.get(field) or not item[field].get("name"):
                        add(ip + "." + field, "現行Schemaでは出発地・到着地が必要です")
                if item.get("mode") not in ("walk", "train", "bus", "car", "ferry", "flight", "other"):
                    add(ip + ".mode", "移動手段を確認してください")
                if item.get("comment"):
                    add(ip + ".comment", "現行Transportには通常コメントの保存先がありません。補正が必要です")
    return results


def build_import_trip(draft: dict, command_id: str) -> dict:
    """Construct a complete candidate after correction; formal validation is separate."""
    if any(item["required"] for item in draft_requirements(draft)):
        raise ValidationError("paste draft requires correction")

    sequence = 0

    def identity(prefix):
        nonlocal sequence
        sequence += 1
        return prefix + "-" + uuid5(NAMESPACE_URL, f"calendar:chat-paste:{command_id}:{sequence}").hex

    trip = {"id": identity("trip"), "title": draft["title"], "summary": None,
            "dateRange": {"start": min(d["date"] for d in draft["days"]),
                          "end": max(d["date"] for d in draft["days"])},
            "days": [], "places": [], "transports": [], "bookings": [],
            "preparation": {"id": identity("preparation"), "tasks": []},
            "rioPlan": {"id": identity("rio"), "applicable": False,
                        "careMode": "not_applicable", "careDecisionDueDate": None,
                        "careDetails": None, "packingTemplate": None, "packingItems": []}}

    def place_id(place):
        result = {"id": identity("place"), "name": place["name"], "summary": None,
                  "category": "other", "rating": None, "address": place["address"],
                  "location": place["location"], "urls": place["urls"]}
        trip["places"].append(result)
        return result["id"]

    for source in draft["days"]:
        day = {"id": identity("day"), "date": source["date"], "title": source["date"],
               "routeSummary": source["route_summary"], "scheduleItems": [], "transportIds": []}
        trip["days"].append(day)
        for order, item in enumerate(source["items"]):
            result = {"id": identity("item"), "dayId": day["id"], "order": order,
                      "status": item["status"], "time": item["time"]}
            if item["kind"] == "schedule":
                selected = [place_id(item["place"])] if item.get("place") and item["place"]["name"] else []
                candidates = selected + [place_id(place) for place in item["candidates"]]
                result.update(action=item["title"], category=item["category"],
                              summary=item["comment"], details=[],
                              placeSelection={"candidatePlaceIds": candidates, "selection": selected,
                                              "minSelections": None, "maxSelections": None})
                day["scheduleItems"].append(result)
            else:
                result.update(mode=item["mode"], fromPlaceId=place_id(item["from_place"]),
                              toPlaceId=place_id(item["to_place"]), bookingId=None)
                trip["transports"].append(result)
                day["transportIds"].append(result["id"])
    return trip
