"""CAL-owned semantic domain interface v1."""

from .errors import ConflictError, DomainError, GenerationWriteError, NotFoundError, ValidationError
from .models import UnifiedEvent
from .service import CalendarDomain as _CalendarDomain
from .trip_detail import build_local_ai_update_request, build_trip_detail_view
from .weather import OpenMeteoAdapter, build_weather_by_day


class CalendarDomain(_CalendarDomain):
    """Calendar domain with transient Goal 1 weather context on ordinary detail views."""

    def __init__(self, db_path, trip_root, *, chat_root=None, weather_adapter=None, weather_today=None):
        super().__init__(db_path, trip_root, chat_root=chat_root)
        self._weather_adapter = weather_adapter or OpenMeteoAdapter()
        self._weather_today = weather_today

    def get_trip_detail_view(self, trip_id, *, candidate_judgments=None, weather_by_day=None):
        effective = self.get_chat_context(trip_id)["trip"]
        if weather_by_day is None:
            weather_by_day = build_weather_by_day(
                effective, self._weather_adapter, today=self._weather_today,
            )
        return super().get_trip_detail_view(
            trip_id,
            candidate_judgments=candidate_judgments,
            weather_by_day=weather_by_day,
        )


__all__ = [
    "CalendarDomain",
    "ConflictError",
    "DomainError",
    "GenerationWriteError",
    "NotFoundError",
    "OpenMeteoAdapter",
    "UnifiedEvent",
    "ValidationError",
    "build_local_ai_update_request",
    "build_trip_detail_view",
    "build_weather_by_day",
]
