"""CAL-owned one-shot generation-request worker."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError

Generator = Callable[[dict[str, Any]], Any]


class GeneratorError(Exception):
    """The replaceable Patch generator failed before CAL submission."""


def command_generator(argv: list[str], timeout: float) -> Generator:
    """Connect a semantic JSON payload to an external argv command."""
    if not argv or any(not isinstance(value, str) or not value for value in argv):
        raise ValueError("generator argv must contain at least one non-empty argument")
    if timeout <= 0:
        raise ValueError("generator timeout must be positive")

    def generate(payload: dict[str, Any]) -> Any:
        try:
            completed = subprocess.run(
                argv,
                input=json.dumps(payload, ensure_ascii=False),
                text=True,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise GeneratorError("generator command failed") from error
        if completed.returncode != 0:
            raise GeneratorError(f"generator exited with status {completed.returncode}")
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise GeneratorError("generator output is not valid JSON") from error

    return generate


def run_once(domain: CalendarDomain, generator: Generator) -> dict[str, Any]:
    """Recover interrupted adoption and process at most one queued request."""
    recovered = domain.recover_pending_adoptions()
    claim = domain.claim_generation_request()
    if claim is None:
        return {"status": "no-op", "recovered": recovered}

    request_id = claim["request_id"]
    try:
        patch = generator(claim)
    except Exception as error:
        domain.release_generation_request(request_id)
        return {
            "status": "generator_failed",
            "request_id": request_id,
            "error": type(error).__name__,
            "recovered": recovered,
        }

    try:
        result = domain.submit_json_patch(
            request_id,
            claim["instruction_id"],
            claim["trip_id"],
            patch,
            claim["base_version"],
            claim["base_hash"],
        )
    except (ValidationError, ConflictError) as error:
        domain.stop_generation_request(request_id)
        return {
            "status": "review_required",
            "request_id": request_id,
            "error": type(error).__name__,
            "recovered": recovered,
        }

    return {"status": result["status"], "result": result, "recovered": recovered}
