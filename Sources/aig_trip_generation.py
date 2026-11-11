"""CAL-owned connection to the stateless AIG complete-Trip boundary."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from typing import Any

from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from Sources.calendar_domain.candidate_diff import candidate_review_rules

AIG_CONTRACT_VERSION = "cal.aig.complete-trip-generation.v1"
_AIG_FAILURE_CODES = {"invalid_request", "generation_failed", "invalid_candidate"}

AIGTransport = Callable[[dict[str, Any]], Any]


_AIG_REASON_MESSAGES = {
    "timeout": "AIの応答待ちが制限時間を超えました。変更を分けるか、時間をおいて再生成してください。",
    "credentials": "AI接続の資格情報を読み取れません。Mac側の接続設定を確認してください。",
    "access_denied": "AIサービスへのアクセスが拒否されました。利用モデルと権限を確認してください。",
    "rate_limit": "AIサービスの利用制限に達しました。時間をおいて再生成してください。",
    "quota": "AIサービスの利用枠または残高が不足しています。契約・利用枠を確認してください。",
    "provider_unavailable": "AIサービスで一時的な障害が発生しました。時間をおいて再生成してください。",
    "invalid_response": "AI応答を旅程として読み取れませんでした。指示を見直して再生成してください。",
    "command_failed": "AI生成に失敗しました。詳しい原因は取得できませんでした。",
}


class AIGTransportError(Exception):
    """Only a fixed reason crosses the command boundary; raw stderr stays private."""
    def __init__(self, *, reason="command_failed"):
        self.reason = reason if reason in _AIG_REASON_MESSAGES else "command_failed"
        super().__init__(_AIG_REASON_MESSAGES[self.reason])


def _command_failure_reason(stderr):
    for line in (stderr or "").splitlines():
        prefix = "cal-trip-ai-error: "
        if line.startswith(prefix) and line[len(prefix):] in _AIG_REASON_MESSAGES:
            return line[len(prefix):]
    return "command_failed"


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
        except subprocess.TimeoutExpired:
            raise AIGTransportError(reason="timeout") from None
        except OSError:
            raise AIGTransportError() from None
        if completed.returncode != 0:
            raise AIGTransportError(reason=_command_failure_reason(completed.stderr))
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            raise AIGTransportError(reason="invalid_response") from None
        if isinstance(result, dict) and result.get("status") == "failed":
            raise AIGTransportError(reason=_command_failure_reason(completed.stderr))
        return result

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
    """Validate a result and raise auto to review for limited preservation signals."""
    try:
        domain.require_current_working_trip_generation(trip_id, generation_id, "generating")
    except ConflictError:
        return _fail(domain, trip_id, generation_id, "obsolete_working")
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

    try:
        candidate = domain.validate_working_trip_generation_candidate(
            trip_id, generation_id, result["candidate"],
        )
    except ValidationError:
        return _fail(domain, trip_id, generation_id, "invalid_candidate")
    except ConflictError:
        return _fail(domain, trip_id, generation_id, "obsolete_working")
    generation = domain.require_current_working_trip_generation(trip_id, generation_id, "generating")
    if generation["policy"] == "review":
        ready = domain.store_working_trip_generation_candidate(
            trip_id, generation_id, candidate,
        )
        return {
            "status": "candidate_ready",
            "generation_id": generation_id,
            "trip_id": trip_id,
            "candidate": ready["candidate"],
        }
    try:
        package = generation["request_package"]
        rules = candidate_review_rules(package["effective_trip"], package["user_intent"], candidate)
    except Exception:
        # Partial evaluation and exceptions never mean no review signals.
        return _fail(domain, trip_id, generation_id, "diff_check_failed")
    if rules:
        try:
            ready = domain.promote_working_trip_generation_candidate(trip_id, generation_id, candidate)
        except ValidationError:
            return _fail(domain, trip_id, generation_id, "invalid_candidate")
        except ConflictError:
            return _fail(domain, trip_id, generation_id, "obsolete_working")
        # Never fall through to auto adoption after promotion.
        return {
            "status": "candidate_ready", "generation_id": generation_id,
            "trip_id": trip_id, "candidate": ready["candidate"],
        }
    try:
        return domain.adopt_working_trip_generation_candidate(
            trip_id, generation_id, candidate,
        )
    except ValidationError:
        return _fail(domain, trip_id, generation_id, "invalid_candidate")
    except ConflictError:
        return _fail(domain, trip_id, generation_id, "obsolete_working")


def run_started_generation(
    domain: CalendarDomain, trip_id: str, generation_id: str, transport: AIGTransport,
) -> dict[str, Any]:
    """Send one frozen request once and accept one stateless AIG result."""
    try:
        request = request_for_started_generation(domain, trip_id, generation_id)
    except ConflictError:
        return _fail(domain, trip_id, generation_id, "obsolete_working")
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
