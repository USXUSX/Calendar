"""Dependency-free CAL domain/service boundary over SQLite and Trip JSON."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from scripts.validate_trip import DEFAULT_SCHEMA, semantic_errors, validate_value

from .errors import ConflictError, NotFoundError, ValidationError
from .models import UnifiedEvent
from .trip_detail import build_trip_detail_view


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
_WORKING_STATE_KEYS = {"item_changes", "temporary_items", "day_instructions"}
_WORKING_ITEM_DISPOSITIONS = {"changed", "pending_delete"}
_WORKING_ITEM_FIELDS = {
    "scheduleItem": {"status", "start", "end", "time_mode", "title", "normal_comment"},
    "transport": {"status", "start", "end", "time_mode"},
}
_WORKING_TEMPORARY_FIELDS = {
    "status", "start", "end", "time_mode", "title", "normal_comment", "place_name",
}
_WORKING_GENERATION_POLICIES = {"auto", "review"}


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
    def _digest(value: bytes) -> str:
        return hashlib.sha256(value).hexdigest()

    def _validated_candidate(self, trip_id: str, candidate: str | Path | dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        try:
            if isinstance(candidate, dict):
                value = copy.deepcopy(candidate)
                payload = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
            elif isinstance(candidate, (str, Path)):
                candidate_path = Path(candidate)
                if candidate_path.resolve() == self._trip_path(trip_id).resolve():
                    raise ValidationError("candidate path must be separate from current Trip JSON")
                payload = candidate_path.read_bytes()
                value = json.loads(payload.decode("utf-8"))
            else:
                raise ValidationError("candidate must be a JSON object or file path")
        except ValidationError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise ValidationError("candidate Trip JSON cannot be read") from error
        errors = validate_value(value, self._trip_schema)
        if errors:
            raise ValidationError(f"candidate Trip JSON is invalid: {errors[0]}")
        if value.get("id") != trip_id:
            raise ValidationError("candidate Trip JSON id does not match trip_id")
        return value, payload

    def _adoption_directory(self) -> Path:
        return self.trip_root / ".adoption"

    def _journal_path(self, trip_id: str) -> Path:
        self._trip_path(trip_id)
        return self._adoption_directory() / f"{trip_id}.json"

    def _staging_path(self, trip_id: str, candidate_digest: str) -> Path:
        self._trip_path(trip_id)
        return self._adoption_directory() / f"{trip_id}.{candidate_digest}.candidate"

    @staticmethod
    def _write_file(path: Path, payload: bytes) -> None:
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                if path.read_bytes() != payload:
                    raise ConflictError("candidate adoption staging conflicts with existing state")
            temporary.unlink()
        except ConflictError:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        except OSError as error:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ConflictError("candidate adoption staging failed") from error

    @staticmethod
    def _write_journal(path: Path, journal: dict[str, Any]) -> None:
        temporary: Path | None = None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
                temporary = Path(handle.name)
                handle.write((json.dumps(journal, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temporary, path)
            temporary.unlink()
        except OSError as error:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
            raise ConflictError("candidate adoption journal cannot be written") from error

    @staticmethod
    def _remove_adoption_file(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise ConflictError("candidate adoption temporary state cannot be cleaned up") from error

    @staticmethod
    def _replace_current(staging_path: Path, current_path: Path) -> None:
        try:
            os.replace(staging_path, current_path)
        except OSError as error:
            raise ConflictError("candidate Trip JSON could not replace current Trip JSON") from error

    def _validate_adoption_constraints(
        self,
        connection: sqlite3.Connection,
        trip_id: str,
        candidate: dict[str, Any],
        instruction_ids: tuple[str, ...],
    ) -> None:
        if connection.execute("SELECT 1 FROM trips WHERE id = ?", (trip_id,)).fetchone() is None:
            raise NotFoundError(f"Trip is not registered: {trip_id}")
        for instruction_id in instruction_ids:
            row = connection.execute(
                "SELECT trip_id, state FROM ai_instructions WHERE id = ?", (instruction_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"AI Instruction not found: {instruction_id}")
            if row["trip_id"] != trip_id or row["state"] != "pending":
                raise ConflictError("adoption requires pending AI Instructions for the target Trip")

        effective = copy.deepcopy(candidate)
        overrides = connection.execute(
            "SELECT source_item_id, field_path, value_json FROM direct_overrides "
            "WHERE trip_id = ? AND active = 1 ORDER BY created_at, id",
            (trip_id,),
        ).fetchall()
        for row in overrides:
            try:
                override_value = json.loads(row["value_json"])
            except json.JSONDecodeError as error:
                raise ValidationError("stored Direct Override value is invalid") from error
            try:
                self._apply_value(effective, row["source_item_id"], row["field_path"], override_value)
            except (ValidationError, ConflictError) as error:
                raise ConflictError("candidate conflicts with an active Direct Override") from error
        effective_errors = validate_value(effective, self._trip_schema)
        if effective_errors:
            raise ValidationError(f"candidate effective Trip is invalid: {effective_errors[0]}")

        todo_item_ids = connection.execute(
            "SELECT DISTINCT trip_item_id FROM todos WHERE trip_id = ? AND trip_item_id IS NOT NULL",
            (trip_id,),
        ).fetchall()
        for row in todo_item_ids:
            if not self._item_matches(candidate, row["trip_item_id"]):
                raise ConflictError("candidate removes a Trip item referenced by a Todo")

    def _instruction_ids(self, instruction_ids: Any) -> tuple[str, ...]:
        if isinstance(instruction_ids, (str, bytes)):
            raise ValidationError("instruction_ids must be a collection")
        try:
            values = tuple(instruction_ids)
        except TypeError as error:
            raise ValidationError("instruction_ids must be a collection") from error
        for value in values:
            self._require_text(value, "instruction_id")
        if len(values) != len(set(values)):
            raise ValidationError("instruction_ids must be unique")
        return values

    def _adopt_validated_candidate(
        self,
        trip_id: str,
        candidate: dict[str, Any],
        request_id: str,
        instruction_id: str,
        expected_version: int,
        expected_hash: str,
    ) -> dict[str, Any]:
        """Adopt an AI Patch candidate through the common atomic layer."""
        return self._adopt_candidate_atomically(
            trip_id, candidate, expected_version, expected_hash,
            kind="generation_request", request_id=request_id,
            instruction_id=instruction_id,
        )

    def _adopt_candidate_atomically(
        self,
        trip_id: str,
        candidate: dict[str, Any],
        expected_version: int,
        expected_hash: str,
        *,
        kind: str,
        request_id: str | None = None,
        instruction_id: str | None = None,
        working_revision: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generator-neutral complete-candidate atomic adoption layer."""
        self._trip_path(trip_id)
        recovered = self.recover_trip_adoption(trip_id)
        if recovered is not None:
            return recovered
        if kind not in {"generation_request", "working_trip"}:
            raise ValidationError("candidate adoption kind is invalid")
        instruction_ids = (instruction_id,) if instruction_id is not None else ()
        candidate_value, candidate_payload = self._validated_candidate(trip_id, candidate)
        current_path = self._trip_path(trip_id)
        try:
            current_payload = current_path.read_bytes()
        except FileNotFoundError as error:
            raise NotFoundError(f"Trip JSON not found: {trip_id}") from error
        except OSError as error:
            raise ValidationError("current Trip JSON cannot be read") from error
        candidate_digest = self._digest(candidate_payload)
        old_digest = self._digest(current_payload)
        staging_path = self._staging_path(trip_id, candidate_digest)
        journal_path = self._journal_path(trip_id)
        journal = {
            "version": 3,
            "kind": kind,
            "trip_id": trip_id,
            "request_id": request_id,
            "instruction_id": instruction_id,
            "old_version": expected_version,
            "old_hash": old_digest,
            "candidate_hash": candidate_digest,
        }
        self._write_file(staging_path, candidate_payload)
        replaced = False
        journal_written = False
        try:
            with self._command() as connection:
                connection.execute("BEGIN IMMEDIATE")
                self._validate_adoption_constraints(connection, trip_id, candidate_value, instruction_ids)
                trip = connection.execute("SELECT version FROM trips WHERE id = ?", (trip_id,)).fetchone()
                if trip is None or trip["version"] != expected_version or old_digest != expected_hash:
                    message = (
                        "generation request base changed before adoption"
                        if kind == "generation_request"
                        else "Working Trip is stale against the current effective Trip"
                    )
                    raise ConflictError(message)
                if kind == "generation_request":
                    request = connection.execute(
                        "SELECT instruction_id, trip_id, state FROM generation_requests WHERE id = ?",
                        (request_id,),
                    ).fetchone()
                    instruction = connection.execute(
                        "SELECT base_version, base_hash FROM ai_instructions WHERE id = ?",
                        (instruction_id,),
                    ).fetchone()
                    if (
                        request is None or request["instruction_id"] != instruction_id
                        or request["trip_id"] != trip_id or request["state"] != "processing"
                        or instruction is None or instruction["base_version"] != expected_version
                        or instruction["base_hash"] != expected_hash
                    ):
                        raise ConflictError("generation request base changed before adoption")
                else:
                    working = connection.execute(
                        "SELECT base_trip_version, base_effective_hash FROM working_trips WHERE trip_id = ?",
                        (trip_id,),
                    ).fetchone()
                    if working is None or working_revision is None or {
                        "trip_version": working["base_trip_version"],
                        "effective_hash": working["base_effective_hash"],
                    } != working_revision or self._effective_revision(trip_id) != working_revision:
                        raise ConflictError("Working Trip is stale against the current effective Trip")
                self._write_journal(journal_path, journal)
                journal_written = True
                if (
                    connection.execute("SELECT version FROM trips WHERE id = ?", (trip_id,)).fetchone()["version"]
                    != expected_version
                    or self._digest(current_path.read_bytes()) != expected_hash
                ):
                    message = (
                        "generation request base changed immediately before adoption"
                        if kind == "generation_request"
                        else "Working Trip is stale against the current effective Trip"
                    )
                    raise ConflictError(message)
                self._replace_current(staging_path, current_path)
                replaced = True
                self._after_candidate_replace()
                timestamp = _now()
                if connection.execute(
                    "UPDATE trips SET version = version + 1, updated_at = ? WHERE id = ? AND version = ?",
                    (timestamp, trip_id, expected_version),
                ).rowcount != 1:
                    raise ConflictError("Trip version changed during candidate adoption")
                if kind == "generation_request":
                    if connection.execute(
                        "UPDATE ai_instructions SET state = 'applied', updated_at = ? "
                        "WHERE id = ? AND trip_id = ? AND state = 'pending'",
                        (timestamp, instruction_id, trip_id),
                    ).rowcount != 1:
                        raise ConflictError("AI Instruction state changed during candidate adoption")
                    if connection.execute(
                        "UPDATE generation_requests SET state = 'completed', updated_at = ? "
                        "WHERE id = ? AND instruction_id = ? AND state = 'processing'",
                        (timestamp, request_id, instruction_id),
                    ).rowcount != 1:
                        raise ConflictError("generation request state changed during candidate adoption")
                elif connection.execute(
                    "DELETE FROM working_trips WHERE trip_id = ?", (trip_id,),
                ).rowcount != 1:
                    raise ConflictError("Working Trip changed during candidate adoption")
        except Exception:
            if not replaced:
                self._remove_adoption_file(staging_path)
                if journal_written:
                    self._remove_adoption_file(journal_path)
            raise
        self._remove_adoption_file(journal_path)
        self._remove_adoption_file(staging_path)
        result = {
            "trip_id": trip_id,
            "status": "adopted",
            "candidate_digest": candidate_digest,
            "version": expected_version + 1,
            "recovered": False,
        }
        if kind == "generation_request":
            result.update({"request_id": request_id, "instruction_id": instruction_id})
        return result

    def _after_candidate_replace(self) -> None:
        """Test seam for a process stop after replacement and before SQLite update."""

    def recover_trip_adoption(self, trip_id: str) -> dict[str, Any] | None:
        """Converge one interrupted adoption from its private digest journal."""
        journal_path = self._journal_path(trip_id)
        if not journal_path.exists():
            return None
        with self._command() as connection:
            connection.execute("BEGIN IMMEDIATE")
            if not journal_path.exists():
                return None
            try:
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
                legacy_required = {
                    "version", "trip_id", "request_id", "instruction_id",
                    "old_version", "old_hash", "candidate_hash",
                }
                current_required = legacy_required | {"kind"}
                if set(journal) == legacy_required and journal.get("version") == 2:
                    kind = "generation_request"
                elif set(journal) == current_required and journal.get("version") == 3:
                    kind = journal.get("kind")
                else:
                    raise ValueError
                if journal["trip_id"] != trip_id or kind not in {"generation_request", "working_trip"}:
                    raise ValueError
                request_id = journal["request_id"]
                instruction_id = journal["instruction_id"]
                if kind == "generation_request":
                    request_id = self._require_text(request_id, "request_id")
                    instruction_id = self._require_text(instruction_id, "instruction_id")
                elif request_id is not None or instruction_id is not None:
                    raise ValueError
                old_version = journal["old_version"]
                candidate_digest = journal["candidate_hash"]
                old_digest = journal["old_hash"]
                if not isinstance(old_version, int) or isinstance(old_version, bool) or old_version < 1:
                    raise ValueError
                if not all(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) for value in (candidate_digest, old_digest)):
                    raise ValueError
                current_digest = self._digest(self._trip_path(trip_id).read_bytes())
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError, ValidationError) as error:
                raise ConflictError("candidate adoption journal is invalid or unreadable") from error

            if current_digest == candidate_digest:
                if kind == "generation_request":
                    row = connection.execute(
                        "SELECT i.trip_id, i.state AS instruction_state, r.state AS request_state, "
                        "t.version AS trip_version FROM ai_instructions i "
                        "JOIN generation_requests r ON r.instruction_id = i.id "
                        "JOIN trips t ON t.id = i.trip_id WHERE i.id = ? AND r.id = ?",
                        (instruction_id, request_id),
                    ).fetchone()
                    if (
                        row is None or row["trip_id"] != trip_id
                        or row["instruction_state"] not in {"pending", "applied"}
                        or row["request_state"] not in {"processing", "completed"}
                        or row["trip_version"] not in {old_version, old_version + 1}
                    ):
                        raise ConflictError("journal conflicts with request pipeline state")
                    trip_version = row["trip_version"]
                else:
                    row = connection.execute(
                        "SELECT version FROM trips WHERE id = ?", (trip_id,),
                    ).fetchone()
                    if row is None or row["version"] not in {old_version, old_version + 1}:
                        raise ConflictError("journal conflicts with Working Trip state")
                    trip_version = row["version"]
                timestamp = _now()
                if trip_version == old_version:
                    connection.execute(
                        "UPDATE trips SET version = ?, updated_at = ? WHERE id = ?",
                        (old_version + 1, timestamp, trip_id),
                    )
                if kind == "generation_request":
                    connection.execute(
                        "UPDATE ai_instructions SET state = 'applied', updated_at = ? WHERE id = ?",
                        (timestamp, instruction_id),
                    )
                    connection.execute(
                        "UPDATE generation_requests SET state = 'completed', updated_at = ? WHERE id = ?",
                        (timestamp, request_id),
                    )
                else:
                    connection.execute("DELETE FROM working_trips WHERE trip_id = ?", (trip_id,))
                status = "adopted"
            elif current_digest == old_digest:
                if kind == "generation_request":
                    row = connection.execute(
                        "SELECT i.trip_id, i.state AS instruction_state, r.state AS request_state, "
                        "t.version AS trip_version FROM ai_instructions i "
                        "JOIN generation_requests r ON r.instruction_id = i.id "
                        "JOIN trips t ON t.id = i.trip_id WHERE i.id = ? AND r.id = ?",
                        (instruction_id, request_id),
                    ).fetchone()
                    if (
                        row is None or row["trip_id"] != trip_id or row["instruction_state"] != "pending"
                        or row["request_state"] not in {"processing", "queued"}
                        or row["trip_version"] != old_version
                    ):
                        raise ConflictError("journal conflicts with request pipeline state")
                    connection.execute(
                        "UPDATE generation_requests SET state = 'queued', updated_at = ? WHERE id = ?",
                        (_now(), request_id),
                    )
                else:
                    row = connection.execute(
                        "SELECT version FROM trips WHERE id = ?", (trip_id,),
                    ).fetchone()
                    if row is None or row["version"] != old_version:
                        raise ConflictError("journal conflicts with Working Trip state")
                status = "not_adopted"
            else:
                raise ConflictError("current Trip JSON matches neither journal digest")

        self._remove_adoption_file(self._staging_path(trip_id, candidate_digest))
        self._remove_adoption_file(journal_path)
        result = {
            "trip_id": trip_id,
            "status": status,
            "candidate_digest": candidate_digest,
            "version": old_version + 1 if status == "adopted" else old_version,
            "recovered": True,
        }
        if kind == "generation_request":
            result.update({"request_id": request_id, "instruction_id": instruction_id})
        return result

    def recover_pending_adoptions(self) -> list[dict[str, Any]]:
        """Converge every adoption journal before a worker claims new work."""
        directory = self._adoption_directory()
        if not directory.exists():
            return []
        results = []
        for journal_path in sorted(directory.glob("*.json")):
            trip_id = journal_path.stem
            self._trip_path(trip_id)
            recovered = self.recover_trip_adoption(trip_id)
            if recovered is not None:
                results.append(recovered)
        return results

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
    def _item_pointer_paths(value: Any, source_item_id: str, path: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
        paths = []
        if isinstance(value, dict):
            if value.get("id") == source_item_id:
                paths.append(path)
            for key, child in value.items():
                paths.extend(CalendarDomain._item_pointer_paths(child, source_item_id, (*path, key)))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                paths.extend(CalendarDomain._item_pointer_paths(child, source_item_id, (*path, str(index))))
        return paths

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

    def _effective_revision(self, trip_id: str) -> dict[str, Any]:
        effective = self.get_effective_trip(trip_id)
        with self._read() as connection:
            version = connection.execute(
                "SELECT version FROM trips WHERE id = ?", (trip_id,)
            ).fetchone()["version"]
        payload = json.dumps(
            effective, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return {"trip_version": version, "effective_hash": self._digest(payload)}

    def save_working_trip(self, trip_id: str, state: dict[str, Any]) -> dict[str, Any]:
        """Replace the latest Working state without rebasing its effective revision."""
        self._registered_trip(trip_id)
        if not isinstance(state, dict):
            raise ValidationError("Working Trip state must be a JSON object")
        if set(state) != _WORKING_STATE_KEYS:
            raise ValidationError(
                "Working Trip state must contain only item_changes, temporary_items, "
                "and day_instructions"
            )
        for key in _WORKING_STATE_KEYS:
            records = state[key]
            if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
                raise ValidationError(f"Working Trip {key} must be an array of JSON objects")
        try:
            state_json = json.dumps(
                state, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as error:
            raise ValidationError("Working Trip state must be valid JSON") from error
        revision = self._effective_revision(trip_id)
        timestamp = _now()
        with self._command() as connection:
            row = connection.execute(
                "SELECT 1 FROM working_trips WHERE trip_id = ?", (trip_id,)
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO working_trips VALUES (?, ?, ?, ?, ?, ?)",
                    (trip_id, revision["trip_version"], revision["effective_hash"], state_json,
                     timestamp, timestamp),
                )
            else:
                connection.execute(
                    "UPDATE working_trips SET state_json = ?, updated_at = ? WHERE trip_id = ?",
                    (state_json, timestamp, trip_id),
                )
        return self.get_working_trip(trip_id)

    def get_working_trip(self, trip_id: str) -> dict[str, Any]:
        """Return Working state even when its captured effective revision is stale."""
        self._registered_trip(trip_id)
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM working_trips WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Working Trip not found: {trip_id}")
        current = self._effective_revision(trip_id)
        base = {
            "trip_version": row["base_trip_version"],
            "effective_hash": row["base_effective_hash"],
        }
        return {
            "trip_id": trip_id,
            "state": json.loads(row["state_json"]),
            "base_effective_revision": base,
            "current_effective_revision": current,
            "stale": base != current,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def require_current_working_trip(self, trip_id: str) -> dict[str, Any]:
        """Confirmation boundary: stale Working state remains editable but cannot proceed."""
        working = self.get_working_trip(trip_id)
        if working["stale"]:
            raise ConflictError("Working Trip is stale against the current effective Trip")
        return working

    def get_working_trip_generation(self, trip_id: str) -> dict[str, Any]:
        """Return the latest CAL-owned generation, or an idle read model when absent."""
        self._registered_trip(trip_id)
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM working_trip_generations WHERE trip_id = ?", (trip_id,)
            ).fetchone()
        if row is None:
            return {"trip_id": trip_id, "state": "idle"}
        result = dict(row)
        candidate_json = result.pop("candidate_json")
        request_package_json = result.pop("request_package_json")
        result["candidate"] = json.loads(candidate_json) if candidate_json else None
        result["request_package"] = json.loads(request_package_json)
        return result

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")

    def start_working_trip_generation(
        self, trip_id: str, generation_id: str, policy: str,
    ) -> dict[str, Any]:
        """Replace a terminal latest generation and capture the current Working revision."""
        self._require_text(generation_id, "generation_id")
        if policy not in _WORKING_GENERATION_POLICIES:
            raise ValidationError("Working Trip generation policy must be auto or review")
        request_package = self.export_working_trip_for_chat(trip_id)
        working = self.require_current_working_trip(trip_id)
        revision = working["base_effective_revision"]
        request_package_json = self._canonical_json(request_package).decode("utf-8")
        working_state_digest = self._digest(self._canonical_json(request_package["user_intent"]))
        timestamp = _now()
        with self._command() as connection:
            current = connection.execute(
                "SELECT state FROM working_trip_generations WHERE trip_id = ?", (trip_id,)
            ).fetchone()
            if current is not None and current["state"] == "generating":
                raise ConflictError("Working Trip generation is already generating")
            current_working = connection.execute(
                "SELECT base_trip_version, base_effective_hash, state_json FROM working_trips WHERE trip_id = ?",
                (trip_id,),
            ).fetchone()
            if current_working is None or (
                current_working["base_trip_version"], current_working["base_effective_hash"]
            ) != (revision["trip_version"], revision["effective_hash"]) or self._digest(
                self._canonical_json(json.loads(current_working["state_json"]))
            ) != working_state_digest:
                raise ConflictError("Working Trip changed while generation was starting")
            connection.execute("DELETE FROM working_trip_generations WHERE trip_id = ?", (trip_id,))
            connection.execute(
                "INSERT INTO working_trip_generations "
                "(trip_id, generation_id, policy, base_trip_version, base_effective_hash, "
                "working_state_digest, request_package_json, state, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'generating', ?, ?)",
                (trip_id, generation_id, policy, revision["trip_version"],
                 revision["effective_hash"], working_state_digest, request_package_json,
                 timestamp, timestamp),
            )
        return self.get_working_trip_generation(trip_id)

    def require_current_working_trip_generation(
        self, trip_id: str, generation_id: str, expected_state: str | None = None,
    ) -> dict[str, Any]:
        """Gate result receipt and later adoption against the exact exported Working state."""
        self._registered_trip(trip_id)
        self._require_text(generation_id, "generation_id")
        with self._read() as connection:
            row = connection.execute(
                "SELECT * FROM working_trip_generations WHERE trip_id = ?", (trip_id,),
            ).fetchone()
            working = connection.execute(
                "SELECT state_json FROM working_trips WHERE trip_id = ?", (trip_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Working Trip generation not found: {trip_id}")
        if row["generation_id"] != generation_id:
            raise ConflictError("Working Trip generation identity does not match")
        if expected_state is not None and row["state"] != expected_state:
            raise ConflictError(f"Working Trip generation is not {expected_state}")
        if working is None or self._digest(
            self._canonical_json(json.loads(working["state_json"]))
        ) != row["working_state_digest"]:
            raise ConflictError("Working Trip generation content does not match")
        return self.get_working_trip_generation(trip_id)

    def store_working_trip_generation_candidate(
        self, trip_id: str, generation_id: str, candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Keep one untrusted candidate for the matching latest generation."""
        if not isinstance(candidate, dict):
            raise ValidationError("Working Trip generation candidate must be a JSON object")
        try:
            candidate_json = json.dumps(
                candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
            )
        except (TypeError, ValueError) as error:
            raise ValidationError("Working Trip generation candidate must be valid JSON") from error
        self._transition_working_trip_generation(
            trip_id, generation_id, "candidate_ready", candidate_json=candidate_json,
        )
        return self.get_working_trip_generation(trip_id)

    def fail_working_trip_generation(
        self, trip_id: str, generation_id: str, failure_code: str,
    ) -> dict[str, Any]:
        """Record a safe failure classification without retrying or retaining history.

        Failure terminalization intentionally does not require the captured Working
        digest to remain current: a changed Working makes the old generation obsolete,
        and failed must still free the latest-only slot for a manual replacement.
        """
        self._require_text(failure_code, "failure_code")
        self._transition_working_trip_generation(
            trip_id, generation_id, "failed", failure_code=failure_code,
            require_matching_working=False,
        )
        return self.get_working_trip_generation(trip_id)

    def _transition_working_trip_generation(
        self, trip_id: str, generation_id: str, state: str, *,
        candidate_json: str | None = None, failure_code: str | None = None,
        require_matching_working: bool = True,
    ) -> None:
        self._registered_trip(trip_id)
        self._require_text(generation_id, "generation_id")
        with self._command() as connection:
            row = connection.execute(
                "SELECT generation_id, policy, state, base_trip_version, base_effective_hash, working_state_digest "
                "FROM working_trip_generations WHERE trip_id = ?", (trip_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"Working Trip generation not found: {trip_id}")
            if row["generation_id"] != generation_id:
                raise ConflictError("Working Trip generation identity does not match")
            if row["state"] != "generating":
                raise ConflictError("Working Trip generation is not generating")
            if state == "candidate_ready" and row["policy"] != "review":
                raise ConflictError("only review generation can keep a candidate")
            working = connection.execute(
                "SELECT base_trip_version, base_effective_hash, state_json FROM working_trips WHERE trip_id = ?",
                (trip_id,),
            ).fetchone()
            if require_matching_working and (working is None or (
                working["base_trip_version"], working["base_effective_hash"]
            ) != (row["base_trip_version"], row["base_effective_hash"]) or self._digest(
                self._canonical_json(json.loads(working["state_json"]))
            ) != row["working_state_digest"]):
                raise ConflictError("Working Trip generation content does not match")
            connection.execute(
                "UPDATE working_trip_generations SET state = ?, candidate_json = ?, failure_code = ?, updated_at = ? "
                "WHERE trip_id = ? AND generation_id = ?",
                (state, candidate_json, failure_code, _now(), trip_id, generation_id),
            )

    def adopt_working_trip_candidate(
        self, trip_id: str, candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Accept one generator-neutral complete candidate for a Working Trip."""
        self._registered_trip(trip_id)
        validated_candidate = self._validate_working_trip_candidate(trip_id, candidate)
        working = self.require_current_working_trip(trip_id)
        with self._read() as connection:
            trip = connection.execute(
                "SELECT version FROM trips WHERE id = ?", (trip_id,),
            ).fetchone()
        try:
            current_hash = self._digest(self._trip_path(trip_id).read_bytes())
        except OSError as error:
            raise ValidationError("current Trip JSON cannot be read") from error
        return self._adopt_candidate_atomically(
            trip_id, validated_candidate, trip["version"], current_hash,
            kind="working_trip",
            working_revision=working["base_effective_revision"],
        )

    def validate_working_trip_generation_candidate(
        self, trip_id: str, generation_id: str, candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Recheck the captured Working digest, then reuse Phase 5 formal Validation."""
        self.require_current_working_trip_generation(
            trip_id, generation_id, "generating",
        )
        return self._validate_working_trip_candidate(trip_id, candidate)

    def _validate_working_trip_candidate(
        self, trip_id: str, candidate: dict[str, Any],
    ) -> dict[str, Any]:
        """Shared pre-adoption boundary for manual and AIG complete candidates."""
        self._registered_trip(trip_id)
        if not isinstance(candidate, dict):
            raise ValidationError("Working Trip candidate must be a JSON object")
        try:
            accepted_candidate = json.loads(json.dumps(
                candidate, ensure_ascii=False, allow_nan=False,
            ))
        except (TypeError, ValueError) as error:
            raise ValidationError("Working Trip candidate must be a JSON object") from error
        with self._read() as connection:
            rows = connection.execute(
                "SELECT trip_id FROM working_trips WHERE trip_id = ?", (trip_id,)
            ).fetchall()
        if not rows:
            raise NotFoundError(f"Working Trip not found: {trip_id}")
        if len(rows) != 1:
            raise ConflictError("Working Trip candidate target is not unique")
        self.require_current_working_trip(trip_id)
        validated_candidate, _ = self._validated_candidate(trip_id, accepted_candidate)
        with self._read() as connection:
            self._validate_adoption_constraints(
                connection, trip_id, validated_candidate, (),
            )
        return validated_candidate

    def clear_working_trip(self, trip_id: str) -> None:
        self._registered_trip(trip_id)
        with self._command() as connection:
            if connection.execute(
                "DELETE FROM working_trips WHERE trip_id = ?", (trip_id,)
            ).rowcount == 0:
                raise NotFoundError(f"Working Trip not found: {trip_id}")

    def save_working_trip_item_change(
        self, trip_id: str, source_type: str, source_item_id: str,
        disposition: str, changes: dict[str, Any],
    ) -> dict[str, Any]:
        """Upsert one existing-item Working record without changing Trip authority."""
        if source_type not in _WORKING_ITEM_FIELDS:
            raise ValidationError("Working item change requires a scheduleItem or transport target")
        self._require_text(source_item_id, "source_item_id")
        if disposition not in _WORKING_ITEM_DISPOSITIONS:
            raise ValidationError("Working item disposition must be changed or pending_delete")
        if not isinstance(changes, dict):
            raise ValidationError("Working item changes must be a JSON object")
        unknown = set(changes) - _WORKING_ITEM_FIELDS[source_type]
        if unknown:
            raise ValidationError(f"Working item field is not allowed: {sorted(unknown)[0]}")
        if disposition == "changed" and not changes:
            raise ValidationError("changed Working item requires at least one field change")
        try:
            json.dumps(changes, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValidationError("Working item changes must be valid JSON") from error

        try:
            working = self.get_working_trip(trip_id)
            state = working["state"]
        except NotFoundError:
            self._registered_trip(trip_id)
            state = {"item_changes": [], "temporary_items": [], "day_instructions": []}
        existing = next((
            record for record in state["item_changes"]
            if record.get("source_type") == source_type
            and record.get("source_item_id") == source_item_id
        ), None)
        if existing is None:
            effective = self.get_effective_trip(trip_id)
            matches = self._item_matches(effective, source_item_id)
            if len(matches) != 1 or (source_type == "transport") != (
                matches[0] in effective["transports"]
            ):
                raise ValidationError("Working item target type does not match the stable ID")
        record = {
            "source_type": source_type,
            "source_item_id": source_item_id,
            "disposition": disposition,
            "changes": copy.deepcopy(changes),
        }
        state["item_changes"] = [
            item for item in state["item_changes"]
            if not (
                item.get("source_type") == source_type
                and item.get("source_item_id") == source_item_id
            )
        ]
        state["item_changes"].append(record)
        return self.save_working_trip(trip_id, state)

    def clear_working_trip_item_change(
        self, trip_id: str, source_type: str, source_item_id: str,
    ) -> dict[str, Any]:
        """Return one existing item to normal by removing its Working record."""
        if source_type not in _WORKING_ITEM_FIELDS:
            raise ValidationError("Working item change requires a scheduleItem or transport target")
        self._require_text(source_item_id, "source_item_id")
        working = self.get_working_trip(trip_id)
        state = working["state"]
        retained = [
            item for item in state["item_changes"]
            if not (
                item.get("source_type") == source_type
                and item.get("source_item_id") == source_item_id
            )
        ]
        if len(retained) == len(state["item_changes"]):
            raise NotFoundError("Working item change not found")
        state["item_changes"] = retained
        return self.save_working_trip(trip_id, state)

    def save_working_trip_temporary_item(
        self, trip_id: str, temporary_id: str, day_id: str, values: dict[str, Any],
        position: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Upsert one manually editable temporary item at an existing-item anchor."""
        self._require_text(temporary_id, "temporary_id")
        self._require_text(day_id, "day_id")
        if not isinstance(values, dict):
            raise ValidationError("Working temporary item values must be a JSON object")
        unknown = set(values) - _WORKING_TEMPORARY_FIELDS
        if unknown:
            raise ValidationError(f"Working temporary item field is not allowed: {sorted(unknown)[0]}")
        try:
            json.dumps(values, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise ValidationError("Working temporary item values must be valid JSON") from error

        try:
            working = self.get_working_trip(trip_id)
            state = working["state"]
        except NotFoundError:
            self._registered_trip(trip_id)
            state = {"item_changes": [], "temporary_items": [], "day_instructions": []}
        existing = next((
            record for record in state["temporary_items"]
            if record.get("temporary_id") == temporary_id
        ), None)
        position_supplied = position is not None
        if position is None:
            if existing is None:
                raise ValidationError("Working temporary item position is required")
            position = copy.deepcopy(existing.get("position"))
        if not isinstance(position, dict) or set(position) != {
            "anchor_source_type", "anchor_source_item_id", "edge",
        }:
            raise ValidationError("Working temporary item position is invalid")
        anchor_type = position["anchor_source_type"]
        anchor_id = position["anchor_source_item_id"]
        if anchor_type not in _WORKING_ITEM_FIELDS or position["edge"] not in {"before", "after"}:
            raise ValidationError("Working temporary item position is invalid")
        self._require_text(anchor_id, "anchor_source_item_id")
        validate_location = (
            existing is None or existing.get("day_id") != day_id
            or (position_supplied and existing.get("position") != position)
        )
        if validate_location:
            effective = self.get_effective_trip(trip_id)
            if not any(day.get("id") == day_id for day in effective["days"]):
                raise ValidationError("Working temporary item day does not exist")
        if existing is None:
            if self._item_matches(effective, temporary_id):
                raise ConflictError("temporary_id conflicts with an existing Trip item ID")
        if validate_location:
            anchor_day = next((day for day in effective["days"] if day.get("id") == day_id), None)
            if anchor_day is None:
                raise ValidationError("Working temporary item day does not exist")
            anchor_ids = (
                set(anchor_day["transportIds"]) if anchor_type == "transport"
                else {item["id"] for item in anchor_day["scheduleItems"]}
            )
            if anchor_id not in anchor_ids:
                raise ValidationError("Working temporary item anchor does not match the day and type")
        record = {
            "temporary_id": temporary_id,
            "day_id": day_id,
            "values": copy.deepcopy(values),
            "position": copy.deepcopy(position),
        }
        state["temporary_items"] = [
            item for item in state["temporary_items"]
            if item.get("temporary_id") != temporary_id
        ]
        state["temporary_items"].append(record)
        return self.save_working_trip(trip_id, state)

    def clear_working_trip_temporary_item(
        self, trip_id: str, temporary_id: str,
    ) -> dict[str, Any]:
        """Remove one temporary item while preserving the rest of the Working envelope."""
        self._require_text(temporary_id, "temporary_id")
        working = self.get_working_trip(trip_id)
        state = working["state"]
        retained = [
            item for item in state["temporary_items"]
            if item.get("temporary_id") != temporary_id
        ]
        if len(retained) == len(state["temporary_items"]):
            raise NotFoundError("Working temporary item not found")
        state["temporary_items"] = retained
        return self.save_working_trip(trip_id, state)

    def save_working_trip_day_instruction(
        self, trip_id: str, day_id: str, instruction: str,
    ) -> dict[str, Any]:
        """Upsert one opaque natural-language instruction for a Trip day."""
        self._require_text(day_id, "day_id")
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValidationError("Working day instruction must be non-empty")
        normalized = instruction.strip()
        try:
            working = self.get_working_trip(trip_id)
            state = working["state"]
        except NotFoundError:
            self._registered_trip(trip_id)
            state = {"item_changes": [], "temporary_items": [], "day_instructions": []}
        existing = next((
            record for record in state["day_instructions"]
            if record.get("day_id") == day_id
        ), None)
        if existing is None:
            effective = self.get_effective_trip(trip_id)
            if not any(day.get("id") == day_id for day in effective["days"]):
                raise ValidationError("Working day instruction target does not exist")
        state["day_instructions"] = [
            record for record in state["day_instructions"]
            if record.get("day_id") != day_id
        ]
        state["day_instructions"].append({"day_id": day_id, "instruction": normalized})
        return self.save_working_trip(trip_id, state)

    def clear_working_trip_day_instruction(
        self, trip_id: str, day_id: str,
    ) -> dict[str, Any]:
        """Remove one day-level instruction without interpreting or applying it."""
        self._require_text(day_id, "day_id")
        working = self.get_working_trip(trip_id)
        state = working["state"]
        retained = [
            record for record in state["day_instructions"]
            if record.get("day_id") != day_id
        ]
        if len(retained) == len(state["day_instructions"]):
            raise NotFoundError("Working day instruction not found")
        state["day_instructions"] = retained
        return self.save_working_trip(trip_id, state)

    def get_trip_detail_view(
        self, trip_id: str, *, candidate_judgments: dict[str, Any] | None = None,
        weather_by_day: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return the Phase 1 Trip-detail model derived from the effective Trip."""
        return build_trip_detail_view(
            self.get_effective_trip(trip_id),
            candidate_judgments=candidate_judgments,
            weather_by_day=weather_by_day,
        )

    @staticmethod
    def _working_time_label(time: dict[str, Any]) -> str:
        if time.get("mode") == "undecided":
            return "未定"
        start = time.get("start") or "未定"
        end = time.get("end")
        return f"{start}–{end}" if end else start

    @classmethod
    def _apply_working_entry_changes(cls, entry: dict[str, Any], changes: Any) -> None:
        if not isinstance(changes, dict):
            return
        for field in ("status", "title", "normal_comment"):
            if field in changes:
                entry[field] = copy.deepcopy(changes[field])
        for field in ("start", "end", "time_mode"):
            if field in changes:
                entry["time"]["mode" if field == "time_mode" else field] = copy.deepcopy(changes[field])
        entry["time"]["label"] = cls._working_time_label(entry["time"])

    @classmethod
    def _working_temporary_entry(cls, record: dict[str, Any]) -> dict[str, Any]:
        values = record.get("values") if isinstance(record.get("values"), dict) else {}
        time = {
            "mode": values.get("time_mode", "undecided"),
            "start": values.get("start"),
            "end": values.get("end"),
            "durationMinutes": None,
        }
        time["label"] = cls._working_time_label(time)
        place_name = values.get("place_name")
        return {
            "source_type": "temporaryItem",
            "source_item_id": record.get("temporary_id"),
            "order": None,
            "time": time,
            "category": "temporary",
            "category_icon_key": "temporary",
            "title": values.get("title") or "名称未入力",
            "places": [{"id": None, "name": place_name, "url": None}] if place_name else [],
            "status": values.get("status", "undecided"),
            "has_candidates": False,
            "candidates": [],
            "normal_comment": values.get("normal_comment"),
            "important_comments": [],
            "supporting_details": [],
            "direct_edit_paths": {},
            "ai_local_update_target": None,
            "working_state": "temporary",
            "working_values": copy.deepcopy(values),
            "working_position": copy.deepcopy(record.get("position")),
        }

    def get_working_trip_detail_view(
        self, trip_id: str, *, candidate_judgments: dict[str, Any] | None = None,
        weather_by_day: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Compose effective Trip then overlay latest Working state for display only."""
        view = self.get_trip_detail_view(
            trip_id, candidate_judgments=candidate_judgments, weather_by_day=weather_by_day,
        )
        try:
            working = self.get_working_trip(trip_id)
        except NotFoundError:
            view["working"] = {"present": False, "stale": False}
            return view

        state = working["state"]
        days = {day["day_id"]: day for day in view["days"]}
        entries = {
            (entry["source_type"], entry["source_item_id"]): entry
            for day in view["days"] for entry in day["entries"]
        }
        for record in state["item_changes"]:
            if not isinstance(record, dict):
                continue
            entry = entries.get((record.get("source_type"), record.get("source_item_id")))
            if entry is None or record.get("disposition") not in _WORKING_ITEM_DISPOSITIONS:
                continue
            self._apply_working_entry_changes(entry, record.get("changes"))
            entry["working_state"] = record["disposition"]

        for day in view["days"]:
            base_entries = day["entries"]
            ordered: list[dict[str, Any]] = []
            unresolved: list[dict[str, Any]] = []
            day_records = [record for record in state["temporary_items"]
                           if isinstance(record, dict) and record.get("day_id") == day["day_id"]
                           and isinstance(record.get("position"), dict)]
            used: set[str] = set()
            for anchor in base_entries:
                matches = [record for record in day_records
                           if record["position"].get("anchor_source_type") == anchor["source_type"]
                           and record["position"].get("anchor_source_item_id") == anchor["source_item_id"]]
                for record in matches:
                    if record["position"].get("edge") == "before":
                        ordered.append(self._working_temporary_entry(record))
                        used.add(record.get("temporary_id"))
                ordered.append(anchor)
                for record in matches:
                    if record["position"].get("edge") == "after":
                        ordered.append(self._working_temporary_entry(record))
                        used.add(record.get("temporary_id"))
            for record in day_records:
                if record.get("temporary_id") not in used:
                    entry = self._working_temporary_entry(record)
                    entry["working_position_unresolved"] = True
                    unresolved.append(entry)
            day["entries"] = ordered + unresolved

        for record in state["day_instructions"]:
            if isinstance(record, dict) and record.get("day_id") in days \
                    and isinstance(record.get("instruction"), str):
                days[record["day_id"]]["working_instruction"] = record["instruction"]
        view["working"] = {"present": True, "stale": working["stale"]}
        return view

    def export_working_trip_for_chat(self, trip_id: str) -> dict[str, Any]:
        """Return the minimal CAL semantic package for manual complete-Trip regeneration."""
        authoritative = self._load_trip(trip_id)
        effective = self.get_effective_trip(trip_id)
        working = self.get_working_trip(trip_id)
        return {
            "format": "cal.complete-trip-regeneration.v1",
            "task": {
                "intent": "Reconcile the effective Trip with all user Working intent.",
                "required_output": "One complete formal CAL Trip JSON object only.",
                "rules": [
                    "Preserve existing effective Trip data unless user intent requires a change.",
                    "Apply changed items, remove pending_delete items, turn temporary items into formal items, and reconcile day instructions across the complete Trip.",
                    "Keep stable IDs for retained data and produce internally consistent references.",
                    "Do not return a patch, partial Trip, explanation, or CAL adoption instruction.",
                ],
            },
            "trip_id": trip_id,
            "authoritative_trip": authoritative,
            "effective_trip": effective,
            "working": {
                "base_effective_revision": copy.deepcopy(working["base_effective_revision"]),
                "current_effective_revision": copy.deepcopy(working["current_effective_revision"]),
                "stale": working["stale"],
            },
            "user_intent": copy.deepcopy(working["state"]),
        }

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

    @staticmethod
    def _json_pointer_tokens(path: Any) -> list[str]:
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValidationError("Patch path must be a non-root JSON Pointer")
        tokens = []
        for raw in path[1:].split("/"):
            index = 0
            decoded = ""
            while index < len(raw):
                if raw[index] != "~":
                    decoded += raw[index]
                    index += 1
                elif index + 1 < len(raw) and raw[index + 1] in {"0", "1"}:
                    decoded += "~" if raw[index + 1] == "0" else "/"
                    index += 2
                else:
                    raise ValidationError("Patch path contains an invalid JSON Pointer escape")
            tokens.append(decoded)
        return tokens

    @classmethod
    def _apply_json_patch(cls, base: dict[str, Any], operations: Any) -> dict[str, Any]:
        if not isinstance(operations, list) or not operations:
            raise ValidationError("Patch must be a non-empty array")
        candidate = copy.deepcopy(base)
        for operation in operations:
            if not isinstance(operation, dict) or set(operation) - {"op", "path", "value"}:
                raise ValidationError("Patch operation has unsupported members")
            op = operation.get("op")
            if op not in {"add", "remove", "replace"}:
                raise ValidationError("Patch operation is unsupported")
            if (op in {"add", "replace"}) != ("value" in operation):
                raise ValidationError("Patch operation value is invalid")
            tokens = cls._json_pointer_tokens(operation.get("path"))
            parent: Any = candidate
            for token in tokens[:-1]:
                if isinstance(parent, dict):
                    if token not in parent:
                        raise ValidationError("Patch path does not exist")
                    parent = parent[token]
                elif isinstance(parent, list):
                    if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                        raise ValidationError("Patch array index is invalid")
                    index = int(token)
                    if index >= len(parent):
                        raise ValidationError("Patch array index is out of range")
                    parent = parent[index]
                else:
                    raise ValidationError("Patch path traverses a scalar")
            token = tokens[-1]
            value = copy.deepcopy(operation.get("value"))
            if isinstance(parent, dict):
                if op in {"remove", "replace"} and token not in parent:
                    raise ValidationError("Patch path does not exist")
                if op == "remove":
                    del parent[token]
                else:
                    parent[token] = value
            elif isinstance(parent, list):
                if token == "-" and op == "add":
                    parent.append(value)
                    continue
                if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                    raise ValidationError("Patch array index is invalid")
                index = int(token)
                if op == "add":
                    if index > len(parent):
                        raise ValidationError("Patch array index is out of range")
                    parent.insert(index, value)
                else:
                    if index >= len(parent):
                        raise ValidationError("Patch array index is out of range")
                    if op == "remove":
                        del parent[index]
                    else:
                        parent[index] = value
            else:
                raise ValidationError("Patch target is a scalar")
        return candidate

    def _reject_active_override_patch_conflicts(
        self, trip_id: str, base: dict[str, Any], operations: list[dict[str, Any]]
    ) -> None:
        patch_paths = [tuple(self._json_pointer_tokens(operation["path"])) for operation in operations]
        with self._read() as connection:
            overrides = connection.execute(
                "SELECT source_item_id, field_path FROM direct_overrides "
                "WHERE trip_id = ? AND active = 1",
                (trip_id,),
            ).fetchall()
        for override in overrides:
            item_paths = self._item_pointer_paths(base, override["source_item_id"])
            if len(item_paths) != 1:
                continue
            override_path = (*item_paths[0], *self._path_parts(override["field_path"]))
            for patch_path in patch_paths:
                shared = min(len(patch_path), len(override_path))
                if patch_path[:shared] == override_path[:shared]:
                    raise ConflictError("JSON Patch conflicts with an active Direct Override")

    def claim_generation_request(self) -> dict[str, Any] | None:
        """Claim the oldest eligible request and return a CAL-owned semantic payload."""
        with self._command() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT r.id AS request_id, r.instruction_id, r.trip_id, i.instruction, t.version "
                "FROM generation_requests r "
                "JOIN ai_instructions i ON i.id = r.instruction_id "
                "JOIN trips t ON t.id = r.trip_id "
                "WHERE r.state = 'queued' AND i.state = 'pending' "
                "AND NOT EXISTS (SELECT 1 FROM generation_requests active "
                "  WHERE active.trip_id = r.trip_id AND active.state = 'processing') "
                "AND NOT EXISTS (SELECT 1 FROM generation_requests earlier "
                "  WHERE earlier.trip_id = r.trip_id AND earlier.state = 'queued' "
                "  AND (earlier.created_at < r.created_at OR "
                "       (earlier.created_at = r.created_at AND earlier.id < r.id))) "
                "ORDER BY r.created_at, r.id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            trip = self._load_trip(row["trip_id"])
            base_hash = self._digest(self._trip_path(row["trip_id"]).read_bytes())
            timestamp = _now()
            if connection.execute(
                "UPDATE generation_requests SET state = 'processing', updated_at = ? "
                "WHERE id = ? AND state = 'queued'",
                (timestamp, row["request_id"]),
            ).rowcount != 1:
                raise ConflictError("generation request changed while being claimed")
            connection.execute(
                "UPDATE ai_instructions SET base_version = ?, base_hash = ?, updated_at = ? WHERE id = ?",
                (row["version"], base_hash, timestamp, row["instruction_id"]),
            )
        return {
            "request_id": row["request_id"],
            "instruction_id": row["instruction_id"],
            "trip_id": row["trip_id"],
            "instruction": row["instruction"],
            "base_version": row["version"],
            "base_hash": base_hash,
            "trip": trip,
        }

    def release_generation_request(self, request_id: str) -> dict[str, Any]:
        """Return a processing request to the queue without failing its Instruction."""
        self._require_text(request_id, "request_id")
        with self._command() as connection:
            if connection.execute(
                "UPDATE generation_requests SET state = 'queued', updated_at = ? "
                "WHERE id = ? AND state = 'processing'",
                (_now(), request_id),
            ).rowcount != 1:
                raise ConflictError("only a processing generation request can be released")
            row = connection.execute("SELECT * FROM generation_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row)

    def stop_generation_request(self, request_id: str) -> dict[str, Any]:
        """Stop automatic retries while leaving the Instruction pending for review."""
        self._require_text(request_id, "request_id")
        with self._command() as connection:
            if connection.execute(
                "UPDATE generation_requests SET state = 'cancelled', updated_at = ? "
                "WHERE id = ? AND state = 'processing'",
                (_now(), request_id),
            ).rowcount != 1:
                raise ConflictError("only a processing generation request can be stopped")
            row = connection.execute("SELECT * FROM generation_requests WHERE id = ?", (request_id,)).fetchone()
        return dict(row)

    def _requeue_stale_request(self, request_id: str, instruction_id: str) -> dict[str, Any]:
        with self._command() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM generation_requests WHERE id = ? AND instruction_id = ?",
                (request_id, instruction_id),
            ).fetchone()
            if row is None or row["state"] not in {"processing", "queued"}:
                raise ConflictError("stale request cannot be requeued")
            connection.execute(
                "UPDATE generation_requests SET state = 'queued', updated_at = ? WHERE id = ?",
                (_now(), request_id),
            )
        return {"request_id": request_id, "status": "stale", "state": "queued"}

    def submit_json_patch(
        self,
        request_id: str,
        instruction_id: str,
        trip_id: str,
        patch: Any,
        base_version: int,
        base_hash: str,
    ) -> dict[str, Any]:
        """Apply a claimed request's JSON Patch to memory, validate, and safely adopt it."""
        self._require_text(request_id, "request_id")
        self._require_text(instruction_id, "instruction_id")
        self._trip_path(trip_id)
        if not isinstance(base_version, int) or isinstance(base_version, bool) or base_version < 1:
            raise ValidationError("base_version must be a positive integer")
        if not isinstance(base_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", base_hash):
            raise ValidationError("base_hash must be a SHA-256 digest")
        with self._read() as connection:
            row = connection.execute(
                "SELECT r.state, r.trip_id, r.instruction_id, i.state AS instruction_state, "
                "i.base_version, i.base_hash, t.version "
                "FROM generation_requests r JOIN ai_instructions i ON i.id = r.instruction_id "
                "JOIN trips t ON t.id = r.trip_id WHERE r.id = ?",
                (request_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"generation request not found: {request_id}")
        if row["trip_id"] != trip_id or row["instruction_id"] != instruction_id:
            raise ConflictError("generation request identity does not match")
        if row["state"] != "processing" or row["instruction_state"] != "pending":
            raise ConflictError("generation request is not processing")
        current_payload = self._trip_path(trip_id).read_bytes()
        current_hash = self._digest(current_payload)
        if (
            row["base_version"] != base_version
            or row["base_hash"] != base_hash
            or row["version"] != base_version
            or current_hash != base_hash
        ):
            return self._requeue_stale_request(request_id, instruction_id)
        current = self._load_trip(trip_id)
        candidate = self._apply_json_patch(current, patch)
        self._reject_active_override_patch_conflicts(trip_id, current, patch)
        try:
            return self._adopt_validated_candidate(
                trip_id, candidate, request_id, instruction_id, base_version, base_hash
            )
        except ConflictError as error:
            if str(error) in {
                "generation request base changed before adoption",
                "generation request base changed immediately before adoption",
            }:
                return self._requeue_stale_request(request_id, instruction_id)
            raise

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
            connection.execute(
                "INSERT INTO generation_requests "
                "(id, instruction_id, trip_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (instruction_id, instruction_id, trip_id, timestamp, timestamp),
            )
        result = self._get_instruction(instruction_id)
        result["request_id"] = instruction_id
        result["request_state"] = "queued"
        return result

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
            row = connection.execute(
                "SELECT i.state, r.state AS request_state FROM ai_instructions i "
                "JOIN generation_requests r ON r.instruction_id = i.id WHERE i.id = ?",
                (instruction_id,),
            ).fetchone()
            if row is None:
                raise NotFoundError(f"AI Instruction not found: {instruction_id}")
            if row["state"] != "pending" or row["request_state"] != "queued":
                raise ConflictError("only a queued pending AI Instruction can be cancelled")
            timestamp = _now()
            connection.execute(
                "UPDATE ai_instructions SET state = 'cancelled', updated_at = ? WHERE id = ?",
                (timestamp, instruction_id),
            )
            if connection.execute(
                "UPDATE generation_requests SET state = 'cancelled', updated_at = ? "
                "WHERE instruction_id = ? AND state = 'queued'",
                (timestamp, instruction_id),
            ).rowcount != 1:
                raise ConflictError("generation request changed during cancellation")
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

    def edit_trip_item(self, command_id: str, trip_id: str, source_type: str,
                       source_item_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Validate and persist one target's semantic field changes atomically."""
        self._require_text(command_id, "command_id")
        if source_type not in {"scheduleItem", "transport"}:
            raise ValidationError("direct edit requires a scheduleItem or transport target")
        if not isinstance(changes, dict) or not changes:
            raise ValidationError("direct edit changes must be a non-empty object")
        paths = {
            "status": "/status", "start": "/time/start", "end": "/time/end",
            "time_mode": "/time/mode",
        }
        if source_type == "scheduleItem":
            paths.update({"title": "/action", "normal_comment": "/summary"})
        unknown = set(changes) - set(paths)
        if unknown:
            raise ValidationError(f"direct edit field is not allowed: {sorted(unknown)[0]}")
        effective = self.get_effective_trip(trip_id)
        matches = self._item_matches(effective, source_item_id)
        if len(matches) != 1 or (source_type == "transport") != (matches[0] in effective["transports"]):
            raise ValidationError("direct edit target type does not match the stable ID")
        for field, value in changes.items():
            self._apply_value(effective, source_item_id, paths[field], value)
        errors = validate_value(effective, self._trip_schema) + semantic_errors(effective)
        if errors:
            raise ValidationError(f"direct edit is invalid: {errors[0]}")
        timestamp = _now()
        with self._command() as connection:
            for field, value in changes.items():
                field_path = paths[field]
                value_json = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                row = connection.execute(
                    "SELECT id FROM direct_overrides WHERE trip_id = ? AND source_item_id = ? AND field_path = ?",
                    (trip_id, source_item_id, field_path),
                ).fetchone()
                override_id = row["id"] if row else f"{command_id}-{source_item_id}-{field}"
                if row:
                    connection.execute(
                        "UPDATE direct_overrides SET value_json = ?, active = 1, updated_at = ? WHERE id = ?",
                        (value_json, timestamp, override_id),
                    )
                else:
                    connection.execute(
                        "INSERT INTO direct_overrides VALUES (?, ?, ?, ?, ?, 1, ?, ?)",
                        (override_id, trip_id, source_item_id, field_path, value_json, timestamp, timestamp),
                    )
        return {
            "trip": self.get_effective_trip(trip_id),
            "view": self.get_trip_detail_view(trip_id),
            "updated_fields": sorted(changes),
        }

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
