"""Derived Trip lifecycle; no persisted completion flag."""
from datetime import date


def is_trip_completed(trip, *, today=None):
    return date.fromisoformat(trip["dateRange"]["end"]) < (today or date.today())
