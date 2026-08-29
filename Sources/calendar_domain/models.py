"""Meaning-based read models returned by the CAL boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UnifiedEvent:
    identity: str
    source_kind: str
    title: str
    summary: str | None
    start_date: str
    start_time: str | None
    end_date: str | None
    end_time: str | None
    visibility: str
    ordinary_event_id: str | None = None
    trip_id: str | None = None
    source_type: str | None = None
    source_item_id: str | None = None
