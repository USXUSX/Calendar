"""CAL-owned semantic domain interface v1."""

from .errors import ConflictError, DomainError, NotFoundError, ValidationError
from .models import UnifiedEvent
from .service import CalendarDomain
from .trip_detail import build_local_ai_update_request, build_trip_detail_view

__all__ = [
    "CalendarDomain",
    "ConflictError",
    "DomainError",
    "NotFoundError",
    "UnifiedEvent",
    "ValidationError",
    "build_local_ai_update_request",
    "build_trip_detail_view",
]
