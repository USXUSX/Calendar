"""Derived Trip lifecycle; no persisted completion flag."""
from datetime import date


def is_trip_completed(trip, *, today=None):
    return date.fromisoformat(trip["dateRange"]["end"]) < (today or date.today())


def lodging_nights(trip):
    """Count saved lodging days, not calendar gaps or flight nights."""
    excluded = ("チェックアウト", "check-out", "check out", "checkout", "機内泊")
    return len({day["date"] for day in trip["days"]
                if day["date"] < trip["dateRange"]["end"]
                and any(item["category"] == "accommodation"
                        and not any(word in item["action"].casefold() for word in excluded)
                        for item in day["scheduleItems"])})
