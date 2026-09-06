"""One-shot AFM recommendation client; the authoritative contract lives in AIG."""
import copy
import json
import subprocess

CONTRACT = "aig.candidate-recommendation.v1"
FAILURES = {"invalid_request", "afm_unavailable", "generation_failed", "invalid_recommendation"}


def failure(code):
    return dict(contract_version=CONTRACT, status="failed", recommended_ids=[],
                reason="", unverified_conditions=[], failure_code=code)


def command_transport(executable, *, timeout=60):
    """Call the prebuilt AIG recommendation executable, explicitly selecting AFM."""
    if not isinstance(executable, str) or not executable or not 0 < timeout <= 240:
        raise ValueError("invalid AFM command configuration")

    def send(request):
        result = subprocess.run([executable, "--provider", "afm"],
                                input=json.dumps(request, ensure_ascii=False),
                                capture_output=True, text=True, timeout=timeout, check=False)
        if result.returncode:
            raise ValueError("AFM command failed")
        return json.loads(result.stdout)
    return send


def recommend(query, candidates, transport):
    request = dict(contract_version=CONTRACT, query=query, candidates=copy.deepcopy(candidates))
    try:
        if len(candidates) > 10 or len(json.dumps(request, ensure_ascii=False).encode()) > 12000:
            return failure("invalid_request")
        if not candidates:
            return dict(contract_version=CONTRACT, status="succeeded", recommended_ids=[],
                        reason="候補がありません。", unverified_conditions=[], failure_code=None)
        result = transport(request)
    except Exception:
        return failure("generation_failed")
    try:
        if not isinstance(result, dict) or set(result) != set(failure("invalid_request")):
            return failure("invalid_recommendation")
        if result["contract_version"] != CONTRACT:
            return failure("invalid_recommendation")
        if result["status"] == "failed":
            if result["failure_code"] in FAILURES and result == failure(result["failure_code"]):
                return copy.deepcopy(result)
            return failure("invalid_recommendation")
        ids, reason, unverified = (result[k] for k in ("recommended_ids", "reason", "unverified_conditions"))
        if (result["status"] != "succeeded" or result["failure_code"] is not None
                or not isinstance(ids, list) or len(ids) > 3
                or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids)
                or not set(ids) <= {c["id"] for c in candidates}
                or not isinstance(reason, str) or not reason.strip() or len(reason) > 500
                or not isinstance(unverified, list) or len(unverified) > 20
                or any(not isinstance(s, str) or not s.strip() or len(s) > 500 for s in unverified)):
            return failure("invalid_recommendation")
        return copy.deepcopy(result)
    except Exception:
        return failure("invalid_recommendation")
