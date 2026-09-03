"""CAL-owned connection to the stateless AIG complete-Trip boundary."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError

AIG_CONTRACT_VERSION = "cal.aig.complete-trip-generation.v1"
_AIG_FAILURE_CODES = {"invalid_request", "generation_failed", "invalid_candidate"}

AIGTransport = Callable[[dict[str, Any]], Any]


class AIGTransportError(Exception):
    """The replaceable AIG command failed without exposing its raw output."""


def command_transport(argv: list[str], timeout: float) -> AIGTransport:
    """Connect the provider-neutral AIG envelope over JSON stdin/stdout."""
    if not argv or any(not isinstance(value, str) or not value for value in argv):
        raise ValueError("AIG argv must contain at least one non-empty argument")
    if timeout <= 0:
        raise ValueError("AIG timeout must be positive")

    def send(request: dict[str, Any]) -> Any:
        try:
            completed = subprocess.run(
                argv,
                input=json.dumps(request, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise AIGTransportError("AIG command failed") from error
        if completed.returncode != 0:
            raise AIGTransportError("AIG command returned failure")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise AIGTransportError("AIG result is not valid JSON") from error

    return send


def request_for_started_generation(
    domain: CalendarDomain, trip_id: str, generation_id: str,
) -> dict[str, Any]:
    """Build the exact provider-neutral request captured when CAL started generation."""
    generation = domain.require_current_working_trip_generation(
        trip_id, generation_id, "generating",
    )
    return {
        "contract_version": AIG_CONTRACT_VERSION,
        "generation_id": generation_id,
        "trip_id": trip_id,
        "working_export_package": generation["request_package"],
    }


def receive_aig_result(
    domain: CalendarDomain, trip_id: str, generation_id: str, result: Any,
) -> dict[str, Any]:
    """Accept one AIG result without deciding the Step 5 auto/review policy."""
    domain.require_current_working_trip_generation(trip_id, generation_id, "generating")
    if not isinstance(result, dict):
        return _fail(domain, trip_id, generation_id, "invalid_result")

    if result.get("generation_id") != generation_id or result.get("trip_id") != trip_id:
        raise ConflictError("AIG generation result identity does not match")

    status = result.get("status")
    if status == "failed":
        if set(result) != {"generation_id", "trip_id", "status", "failure_code"}:
            return _fail(domain, trip_id, generation_id, "invalid_result")
        failure_code = result.get("failure_code")
        if failure_code not in _AIG_FAILURE_CODES:
            return _fail(domain, trip_id, generation_id, "invalid_result")
        return _fail(domain, trip_id, generation_id, failure_code)

    if status != "succeeded" or set(result) != {
        "generation_id", "trip_id", "status", "candidate",
    } or not isinstance(result.get("candidate"), dict):
        return _fail(domain, trip_id, generation_id, "invalid_result")

    candidate = domain.validate_working_trip_generation_candidate(
        trip_id, generation_id, result["candidate"],
    )
    return {
        "status": "candidate_received",
        "generation_id": generation_id,
        "trip_id": trip_id,
        "candidate": candidate,
    }


def run_started_generation(
    domain: CalendarDomain, trip_id: str, generation_id: str, transport: AIGTransport,
) -> dict[str, Any]:
    """Send one frozen request once and accept one stateless AIG result."""
    request = request_for_started_generation(domain, trip_id, generation_id)
    try:
        result = transport(request)
    except Exception:
        return _fail(domain, trip_id, generation_id, "transport_failed")
    return receive_aig_result(domain, trip_id, generation_id, result)


def _fail(
    domain: CalendarDomain, trip_id: str, generation_id: str, failure_code: str,
) -> dict[str, Any]:
    generation = domain.fail_working_trip_generation(trip_id, generation_id, failure_code)
    return {
        "status": "failed",
        "generation_id": generation_id,
        "trip_id": trip_id,
        "failure_code": generation["failure_code"],
    }
