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
        """Validate a complete-JSON new candidate; only a registered Trip conflicts."""
        candidate = self._with_home(candidate)
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

    def import_trip_json(self, candidate, *, confirmed=False, coordinate_results=None):
        """Adopt complete JSON and replace only an unregistered orphan formal file."""
        if confirmed is not True:
            raise ValidationError("JSON取込には内容確認が必要です。")
        result = self.review_trip_json(candidate)
        if not result["ready"]:
            raise ValidationError("candidate Trip JSON is invalid: " + result["errors"][0])
        from .map_locations import complete
        candidate, counts = complete(result["candidate"], coordinate_results)
        trip_id = candidate["id"]
        self._trip_path(trip_id).unlink(missing_ok=True)
        return {**super()._import_new_trip(candidate), "coordinates": counts}

    def prepare_import_locations(self, candidate, *, existing_trip_id=None):
        from .map_locations import prepare
        existing = self.get_effective_trip(existing_trip_id) if existing_trip_id else None
        return prepare(self._with_home(candidate), existing)[1]

    def get_map_location(self, trip_id, place_id):
        from .map_locations import target
        return target(self, trip_id, place_id)

    def save_map_location(self, command_id, trip_id, place_id, location, expected_location, google_place_id=None, expected_name=None):
        from .map_locations import save
        return save(self, command_id, trip_id, place_id, location, expected_location, google_place_id, expected_name)

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


    def prepare_location_inputs(self, trip_id, day_id, points):
        from .map_locations import inputs
        return inputs(self, trip_id, day_id, points)


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
