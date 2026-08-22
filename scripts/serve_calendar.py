#!/usr/bin/env python3
"""Serve Calendar web assets and adopted local trip JSON on loopback only."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCAL_DATA = REPO_ROOT.parents[1] / "LocalData" / "Calendar_Local"
TRIP_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}\Z")


class TripDataError(Exception):
    """An adopted trip file cannot be safely served."""


def load_trip_file(path: Path, expected_id: str) -> dict:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise TripDataError(f"cannot read valid JSON for trip {expected_id}") from error
    if not isinstance(value, dict):
        raise TripDataError(f"trip {expected_id} does not contain a JSON object")
    metadata = value.get("trip") if isinstance(value.get("trip"), dict) else value
    actual_id = metadata.get("id")
    if actual_id != expected_id:
        raise TripDataError(f"trip folder and JSON id do not match for {expected_id}")
    return value


def trip_summary(value: dict) -> dict:
    metadata = value.get("trip") if isinstance(value.get("trip"), dict) else value
    title = metadata.get("name", metadata.get("title"))
    date_range = metadata.get("dateRange") or {
        "start": metadata.get("startDate"),
        "end": metadata.get("endDate"),
    }
    if not isinstance(title, str) or not title or not isinstance(date_range, dict):
        raise TripDataError(f"trip {metadata.get('id', '(unknown)')} is missing list metadata")
    if not all(isinstance(date_range.get(key), str) and date_range[key] for key in ("start", "end")):
        raise TripDataError(f"trip {metadata.get('id', '(unknown)')} has an invalid date range")
    return {"id": metadata["id"], "title": title, "dateRange": date_range}


def make_handler(local_data: Path):
    trips_root = local_data / "trips"

    class CalendarHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

        def _json(self, status: HTTPStatus, value: object) -> None:
            body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _api_error(self, status: HTTPStatus, message: str) -> None:
            self._json(status, {"error": message})

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = unquote(urlsplit(self.path).path)
            if path == "/api/trips":
                try:
                    summaries = []
                    if trips_root.is_dir():
                        for folder in sorted(item for item in trips_root.iterdir() if item.is_dir()):
                            if not TRIP_ID.fullmatch(folder.name):
                                raise TripDataError("an invalid trip folder name exists")
                            current = folder / "current.json"
                            if not current.is_file():
                                continue
                            summaries.append(trip_summary(load_trip_file(current, folder.name)))
                    self._json(HTTPStatus.OK, summaries)
                except TripDataError as error:
                    print(f"Calendar data error: {error}", file=sys.stderr)
                    self._api_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return

            match = re.fullmatch(r"/api/trips/([^/]+)/(current|candidate)", path)
            if match:
                trip_id = match.group(1)
                version = match.group(2)
                if not TRIP_ID.fullmatch(trip_id):
                    self._api_error(HTTPStatus.BAD_REQUEST, "invalid trip id")
                    return
                trip_file = trips_root / trip_id / f"{version}.json"
                if not trip_file.is_file():
                    self._api_error(HTTPStatus.NOT_FOUND, f"{version} trip not found")
                    return
                try:
                    self._json(HTTPStatus.OK, load_trip_file(trip_file, trip_id))
                except TripDataError as error:
                    print(f"Calendar data error: {error}", file=sys.stderr)
                    self._api_error(HTTPStatus.INTERNAL_SERVER_ERROR, str(error))
                return

            if path.startswith("/api/"):
                self._api_error(HTTPStatus.NOT_FOUND, "API endpoint not found")
                return
            super().do_GET()

        def do_HEAD(self) -> None:  # noqa: N802 - stdlib handler API
            if urlsplit(self.path).path.startswith("/api/"):
                self.send_error(HTTPStatus.METHOD_NOT_ALLOWED)
                return
            super().do_HEAD()

        def _reject_write(self) -> None:
            self._api_error(HTTPStatus.METHOD_NOT_ALLOWED, "read-only server")

        do_POST = do_PUT = do_PATCH = do_DELETE = _reject_write

    return CalendarHandler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4174)
    parser.add_argument("--local-data", type=Path, default=Path(os.environ.get("CALENDAR_LOCAL_DATA", DEFAULT_LOCAL_DATA)))
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.local_data.resolve()))
    print(f"Calendar: http://127.0.0.1:{server.server_port}/Sources/web/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
