"""CAL-owned semantic domain interface v1."""

import copy

from scripts.validate_trip import validation_stage_errors

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

    def review_trip_json(self, candidate):
        """Validate a new candidate; only a registered Trip is an overwrite conflict."""
        candidate = copy.deepcopy(candidate)
        stage, errors = validation_stage_errors(candidate, self._trip_schema)
        if errors:
            return {"ready": False, "stage": stage, "errors": errors, "view": None}
        candidate, _ = self._validated_candidate(candidate["id"], candidate)
        with self._read() as connection:
            exists = connection.execute("SELECT 1 FROM trips WHERE id = ?", (candidate["id"],)).fetchone()
        if exists:
            raise ConflictError("同じTrip IDの登録先が既に存在します。上書きはできません。")
        view = build_trip_detail_view(candidate)
        for day in view["days"]:
            for entry in day["entries"]:
                entry["direct_edit_paths"] = {}
                entry["ai_local_update_target"] = None
        return {"ready": True, "errors": [], "view": view, "candidate": candidate}

    def _import_new_trip(self, candidate):
        """Replace an unregistered orphan Trip JSON, while never overwriting a registered Trip."""
        trip_id = candidate["id"]
        with self._read() as connection:
            registered = connection.execute("SELECT 1 FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if not registered:
            self._trip_path(trip_id).unlink(missing_ok=True)
        return super()._import_new_trip(candidate)

    def load_trip_detail_view(self, trip_id):
        """Ordinary screen load: validate/adopt the latest Chat candidate, then display."""
        review = self.review_chat_candidate(trip_id)
        status = review["status"]
        message = review.get("message") or "\n".join(review.get("errors", []))
        if review["ready"]:
            try:
                self.adopt_chat_candidate(trip_id, review["candidate"], confirmed=True)
                status, message = "adopted", ""
            except DomainError as error:
                status, message = "invalid", str(error)
        result = self.get_trip_detail_view(trip_id)
        result["chat"] = {"status": status, "message": message if status in {"invalid", "stale"} else ""}
        return result

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
