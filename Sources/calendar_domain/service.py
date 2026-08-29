"""Dependency-free CAL domain/service boundary over SQLite and Trip JSON."""

from __future__ import annotations

import copy
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from scripts.validate_trip import DEFAULT_SCHEMA, validate_value

from .errors import ConflictError, NotFoundError, ValidationError
from .models import UnifiedEvent


_TRIP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$")
_VISIBILITIES = {"owner", "participants"}
_EVENT_FIELDS = {
    "title", "start_date", "start_time", "end_date", "end_time",
    "time_zone", "notes", "visibility",
}
_TODO_FIELDS = {
    "label", "due_date", "due_time", "trip_id", "event_id",
    "trip_item_id", "visibility",
}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class CalendarDomain:
    """Semantic CAL interface; both storage roots must be explicitly supplied."""

    def __init__(self, db_path: str | Path, trip_root: str | Path):
        if db_path is None or trip_root is None:
            raise ValidationError("db_path and trip_root are required")
        self.db_path = Path(db_path)
        self.trip_root = Path(trip_root)
        try:
            with DEFAULT_SCHEMA.open(encoding="utf-8") as handle:
                self._trip_schema = json.load(handle)
        except (OSError, json.JSONDecodeError) as error:
            raise ValidationError("Trip Schema is unavailable or invalid") from error

    def _connect(self) -> sqlite3.Connection:
        try:
            connection = sqlite3.connect(self.db_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            return connection
        except sqlite3.Error as error:
            raise ValidationError("Calendar database cannot be opened") from error

    @contextmanager
    def _command(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        except sqlite3.IntegrityError as error:
            raise ValidationError("command violates the Calendar data contract") from error
        except sqlite3.Error as error:
            raise ValidationError("Calendar database command failed") from error
        finally:
            connection.close()

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
        except sqlite3.Error as error:
            raise ValidationError("Calendar database read failed") from error
        finally:
            connection.close()

    def _trip_path(self, trip_id: str) -> Path:
        if not isinstance(trip_id, str) or not _TRIP_ID.fullmatch(trip_id):
            raise ValidationError("invalid trip_id")
        return self.trip_root / "trips" / f"{trip_id}.json"

    def _load_trip(self, trip_id: str) -> dict[str, Any]:
        path = self._trip_path(trip_id)
        try:
            with path.open(encoding="utf-8") as handle:
                trip = json.load(handle)
        except FileNotFoundError as error:
            raise NotFoundError(f"Trip JSON not found: {trip_id}") from error
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValidationError(f"Trip JSON cannot be read: {trip_id}") from error
        errors = validate_value(trip, self._trip_schema)
        if errors:
            raise ValidationError(f"Trip JSON is invalid: {errors[0]}")
        if trip.get("id") != trip_id:
            raise ValidationError("Trip JSON id does not match the registered trip_id")
        return trip

    @staticmethod
    def _require_text(value: Any, name: str) -> str:
        if not isinstance(value, str) or not value:
            raise ValidationError(f"{name} must be a non-empty string")
        return value

    @staticmethod
    def _ordinary_id(value: str) -> str:
        CalendarDomain._require_text(value, "event_id")
        if value.startswith("trip:"):
            raise ConflictError("Trip-derived Events must be changed through a Direct Override or AI Instruction")
        return value

    def register_trip(self, trip_id: str, visibility: str = "owner") -> dict[str, Any]:
        self._load_trip(trip_id)
        if visibility not in _VISIBILITIES:
            raise ValidationError("invalid visibility")
        timestamp = _now()
        with self._command() as connection:
            if connection.execute("SELECT 1 FROM trips WHERE id = ?", (trip_id,)).fetchone():
                raise ConflictError(f"Trip is already registered: {trip_id}")
            connection.execute(
                "INSERT INTO trips (id, visibility, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (trip_id, visibility, timestamp, timestamp),
            )
        return {"id": trip_id, "visibility": visibility}

    def _registered_trip(self, trip_id: str) -> sqlite3.Row:
        with self._read() as connection:
            row = connection.execute("SELECT id, visibility FROM trips WHERE id = ?", (trip_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Trip is not registered: {trip_id}")
        return row

    @staticmethod
    def _item_matches(value: Any, source_item_id: str) -> list[dict[str, Any]]:
        matches: list[dict[str, Any]] = []
        if isinstance(value, dict):
            if value.get("id") == source_item_id:
                matches.append(value)
            for child in value.values():
                matches.extend(CalendarDomain._item_matches(child, source_item_id))
        elif isinstance(value, list):
            for child in value:
                matches.extend(CalendarDomain._item_matches(child, source_item_id))
        return matches

    @staticmethod
    def _path_parts(field_path: str) -> list[str]:
        if not isinstance(field_path, str) or not field_path.startswith("/") or field_path == "/":
            raise ValidationError("field_path must be a non-root JSON Pointer")
        parts = field_path[1:].split("/")
        decoded: list[str] = []
        for part in parts:
            if re.search(r"~(?![01])", part):
                raise ValidationError("field_path contains an invalid JSON Pointer escape")
            decoded.append(part.replace("~1", "/").replace("~0", "~"))
        return decoded

    @classmethod
    def _apply_value(cls, trip: dict[str, Any], source_item_id: str, field_path: str, value: Any) -> None:
        matches = cls._item_matches(trip, source_item_id)
        if not matches:
            raise ValidationError(f"source_item_id does not exist: {source_item_id}")
        if len(matches) != 1:
            raise ConflictError(f"source_item_id is not unique in Trip JSON: {source_item_id}")
        target: Any = matches[0]
        parts = cls._path_parts(field_path)
        for part in parts[:-1]:
            if isinstance(target, dict) and part in target:
                target = target[part]
            elif isinstance(target, list) and part.isdigit() and int(part) < len(target):
                target = target[int(part)]
            else:
                raise ValidationError(f"field_path does not exist: {field_path}")
        leaf = parts[-1]
        if isinstance(target, dict):
            if leaf not in target:
                raise ValidationError(f"field_path does not exist: {field_path}")
            target[leaf] = copy.deepcopy(value)
        elif isinstance(target, list) and leaf.isdigit() and int(leaf) < len(target):
            target[int(leaf)] = copy.deepcopy(value)
        else:
            raise ValidationError(f"field_path does not exist: {field_path}")

    def get_effective_trip(self, trip_id: str) -> dict[str, Any]:
        self._registered_trip(trip_id)
        trip = self._load_trip(trip_id)
        with self._read() as connection:
            rows = connection.execute(
                "SELECT source_item_id, field_path, value_json FROM direct_overrides "
                "WHERE trip_id = ? AND active = 1 ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        effective = copy.deepcopy(trip)
        for row in rows:
            try:
                value = json.loads(row["value_json"])
            except json.JSONDecodeError as error:
                raise ValidationError("stored Direct Override value is invalid") from error
            self._apply_value(effective, row["source_item_id"], row["field_path"], value)
        errors = validate_value(effective, self._trip_schema)
        if errors:
            raise ValidationError(f"effective Trip is invalid: {errors[0]}")
        return effective

    def list_events(self, start_date: str, end_date: str) -> list[UnifiedEvent]:
        try:
            range_start = date.fromisoformat(start_date)
            range_end = date.fromisoformat(end_date)
        except (TypeError, ValueError) as error:
            raise ValidationError("invalid Event date range") from error
        if range_start > range_end:
            raise ValidationError("invalid Event date range")
        with self._read() as connection:
            ordinary = connection.execute(
                "SELECT * FROM events WHERE start_date <= ? AND COALESCE(end_date, start_date) >= ?",
                (end_date, start_date),
            ).fetchall()
            trips = connection.execute("SELECT id, visibility FROM trips").fetchall()
        events = [
            UnifiedEvent(
                identity=f"ordinary:{row['id']}", source_kind="ordinary", title=row["title"],
                summary=row["notes"], start_date=row["start_date"], start_time=row["start_time"],
                end_date=row["end_date"], end_time=row["end_time"], visibility=row["visibility"],
                ordinary_event_id=row["id"],
            )
            for row in ordinary
        ]
        for registry in trips:
            trip = self.get_effective_trip(registry["id"])
            places = {place["id"]: place["name"] for place in trip["places"]}
            transports = {item["id"]: item for item in trip["transports"]}
            for day in trip["days"]:
                if not start_date <= day["date"] <= end_date:
                    continue
                for item in day["scheduleItems"]:
                    events.append(self._trip_event(registry, day["date"], "scheduleItem", item, item["action"], item["summary"]))
                for transport_id in day["transportIds"]:
                    item = transports[transport_id]
                    origin = places[item["fromPlaceId"]]
                    destination = places[item["toPlaceId"]]
                    title = f"{origin} → {destination} ({item['mode']})"
                    events.append(self._trip_event(registry, day["date"], "transport", item, title, None))
        return sorted(events, key=lambda item: (item.start_date, item.start_time or "", item.identity))

    @staticmethod
    def _trip_event(registry: sqlite3.Row, date: str, source_type: str, item: dict[str, Any], title: str, summary: str | None) -> UnifiedEvent:
        return UnifiedEvent(
            identity=f"trip:{registry['id']}:{source_type}:{item['id']}", source_kind="trip",
            title=title, summary=summary, start_date=date, start_time=item["time"]["start"],
            end_date=date if item["time"]["end"] is not None else None, end_time=item["time"]["end"],
            visibility=registry["visibility"], trip_id=registry["id"], source_type=source_type,
            source_item_id=item["id"],
        )

    def create_event(self, event_id: str, *, title: str, start_date: str, start_time: str | None = None,
                     end_date: str | None = None, end_time: str | None = None, time_zone: str | None = None,
                     notes: str | None = None, visibility: str = "owner") -> dict[str, Any]:
        event_id = self._ordinary_id(event_id)
        self._require_text(title, "title")
        timestamp = _now()
        with self._command() as connection:
            if connection.execute("SELECT 1 FROM events WHERE id = ?", (event_id,)).fetchone():
                raise ConflictError(f"Event already exists: {event_id}")
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event_id, title, start_date, start_time, end_date, end_time, time_zone, notes,
                 visibility, timestamp, timestamp),
            )
        return self.get_event(event_id)

    def get_event(self, event_id: str) -> dict[str, Any]:
        event_id = self._ordinary_id(event_id)
        with self._read() as connection:
            row = connection.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Event not found: {event_id}")
        return dict(row)

    def update_event(self, event_id: str, **changes: Any) -> dict[str, Any]:
        event_id = self._ordinary_id(event_id)
        self._update("events", event_id, changes, _EVENT_FIELDS)
        return self.get_event(event_id)

    def delete_event(self, event_id: str) -> None:
        event_id = self._ordinary_id(event_id)
        with self._command() as connection:
            if connection.execute("DELETE FROM events WHERE id = ?", (event_id,)).rowcount == 0:
                raise NotFoundError(f"Event not found: {event_id}")

    def create_todo(self, todo_id: str, *, label: str, due_date: str | None = None,
                    due_time: str | None = None, trip_id: str | None = None,
                    event_id: str | None = None, trip_item_id: str | None = None,
                    visibility: str = "owner") -> dict[str, Any]:
        self._require_text(todo_id, "todo_id")
        self._require_text(label, "label")
        timestamp = _now()
        with self._command() as connection:
            if connection.execute("SELECT 1 FROM todos WHERE id = ?", (todo_id,)).fetchone():
                raise ConflictError(f"Todo already exists: {todo_id}")
            connection.execute(
                "INSERT INTO todos (id, label, due_date, due_time, trip_id, event_id, trip_item_id, visibility, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (todo_id, label, due_date, due_time, trip_id, event_id, trip_item_id, visibility, timestamp, timestamp),
            )
        return self.get_todo(todo_id)

    def get_todo(self, todo_id: str) -> dict[str, Any]:
        with self._read() as connection:
            row = connection.execute("SELECT * FROM todos WHERE id = ?", (todo_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Todo not found: {todo_id}")
        return dict(row)

    def list_todos(self, *, trip_id: str | None = None, event_id: str | None = None,
                   completed: bool | None = None) -> list[dict[str, Any]]:
        clauses, values = [], []
        if trip_id is not None:
            clauses.append("trip_id = ?")
            values.append(trip_id)
        if event_id is not None:
            clauses.append("event_id = ?")
            values.append(event_id)
        if completed is not None:
            clauses.append("completed_at IS NOT NULL" if completed else "completed_at IS NULL")
        query = "SELECT * FROM todos" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY created_at, id"
        with self._read() as connection:
            return [dict(row) for row in connection.execute(query, values)]

    def update_todo(self, todo_id: str, **changes: Any) -> dict[str, Any]:
        self._update("todos", todo_id, changes, _TODO_FIELDS)
        return self.get_todo(todo_id)

    def set_todo_completed(self, todo_id: str, completed: bool = True) -> dict[str, Any]:
        if not isinstance(completed, bool):
            raise ValidationError("completed must be boolean")
        self._update("todos", todo_id, {"completed_at": _now() if completed else None}, {"completed_at"})
        return self.get_todo(todo_id)

    def delete_todo(self, todo_id: str) -> None:
        with self._command() as connection:
            if connection.execute("DELETE FROM todos WHERE id = ?", (todo_id,)).rowcount == 0:
                raise NotFoundError(f"Todo not found: {todo_id}")

    def _update(self, table: str, entity_id: str, changes: dict[str, Any], allowed: set[str]) -> None:
        self._require_text(entity_id, "id")
        if not changes or not set(changes) <= allowed:
            raise ValidationError("update contains no fields or unsupported fields")
        assignments = ", ".join(f"{field} = ?" for field in changes) + ", updated_at = ?"
        values = [*changes.values(), _now(), entity_id]
        with self._command() as connection:
            if connection.execute(f"UPDATE {table} SET {assignments} WHERE id = ?", values).rowcount == 0:
                raise NotFoundError(f"{table[:-1].title()} not found: {entity_id}")

    def add_ai_instruction(self, instruction_id: str, trip_id: str, instruction: str) -> dict[str, Any]:
        self._require_text(instruction_id, "instruction_id")
        self._require_text(instruction, "instruction")
        timestamp = _now()
        with self._command() as connection:
            if connection.execute("SELECT 1 FROM ai_instructions WHERE id = ?", (instruction_id,)).fetchone():
                raise ConflictError(f"AI Instruction already exists: {instruction_id}")
            connection.execute(
                "INSERT INTO ai_instructions (id, trip_id, instruction, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (instruction_id, trip_id, instruction, timestamp, timestamp),
            )
        return self._get_instruction(instruction_id)

    def _get_instruction(self, instruction_id: str) -> dict[str, Any]:
        with self._read() as connection:
            row = connection.execute("SELECT * FROM ai_instructions WHERE id = ?", (instruction_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"AI Instruction not found: {instruction_id}")
        return dict(row)

    def list_pending_ai_instructions(self, trip_id: str) -> list[dict[str, Any]]:
        self._registered_trip(trip_id)
        with self._read() as connection:
            rows = connection.execute(
                "SELECT * FROM ai_instructions WHERE trip_id = ? AND state = 'pending' ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def cancel_ai_instruction(self, instruction_id: str) -> dict[str, Any]:
        with self._command() as connection:
            row = connection.execute("SELECT state FROM ai_instructions WHERE id = ?", (instruction_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"AI Instruction not found: {instruction_id}")
            if row["state"] != "pending":
                raise ConflictError("only a pending AI Instruction can be cancelled")
            connection.execute(
                "UPDATE ai_instructions SET state = 'cancelled', updated_at = ? WHERE id = ?",
                (_now(), instruction_id),
            )
        return self._get_instruction(instruction_id)

    def set_direct_override(self, override_id: str, trip_id: str, source_item_id: str,
                            field_path: str, value: Any) -> dict[str, Any]:
        self._require_text(override_id, "override_id")
        self._registered_trip(trip_id)
        candidate = self.get_effective_trip(trip_id)
        self._apply_value(candidate, source_item_id, field_path, value)
        errors = validate_value(candidate, self._trip_schema)
        if errors:
            raise ValidationError(f"Direct Override value is invalid: {errors[0]}")
        try:
            value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValidationError("Direct Override value is not valid JSON") from error
        timestamp = _now()
        with self._command() as connection:
            row = connection.execute(
                "SELECT id FROM direct_overrides WHERE trip_id = ? AND source_item_id = ? AND field_path = ?",
                (trip_id, source_item_id, field_path),
            ).fetchone()
            if row is not None and row["id"] != override_id:
                raise ConflictError("override_id does not match the existing Direct Override target")
            if row is None:
                connection.execute(
                    "INSERT INTO direct_overrides VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                    (override_id, trip_id, source_item_id, field_path, value_json, timestamp, timestamp),
                )
            else:
                connection.execute(
                    "UPDATE direct_overrides SET value_json = ?, active = 1, updated_at = ? WHERE id = ?",
                    (value_json, timestamp, override_id),
                )
        return self._get_override(override_id)

    def _get_override(self, override_id: str) -> dict[str, Any]:
        with self._read() as connection:
            row = connection.execute("SELECT * FROM direct_overrides WHERE id = ?", (override_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Direct Override not found: {override_id}")
        result = dict(row)
        result["value"] = json.loads(result.pop("value_json"))
        result["active"] = bool(result["active"])
        return result

    def list_active_direct_overrides(self, trip_id: str) -> list[dict[str, Any]]:
        self._registered_trip(trip_id)
        with self._read() as connection:
            rows = connection.execute(
                "SELECT id FROM direct_overrides WHERE trip_id = ? AND active = 1 ORDER BY created_at, id",
                (trip_id,),
            ).fetchall()
        return [self._get_override(row["id"]) for row in rows]

    def clear_direct_override(self, override_id: str) -> dict[str, Any]:
        with self._command() as connection:
            row = connection.execute("SELECT active FROM direct_overrides WHERE id = ?", (override_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"Direct Override not found: {override_id}")
            if not row["active"]:
                raise ConflictError("Direct Override is already inactive")
            connection.execute(
                "UPDATE direct_overrides SET active = 0, updated_at = ? WHERE id = ?", (_now(), override_id)
            )
        return self._get_override(override_id)
