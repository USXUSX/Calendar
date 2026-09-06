"""AFM one-shot client. Contract authority: AI-Gateway, aig.comment-extraction.v1."""
import copy
import json
import subprocess

CONTRACT = "aig.comment-extraction.v1"
FAILURES = {"invalid_request", "afm_unavailable", "generation_failed", "invalid_extraction"}


def result(status, text="", ids=None, code=None):
    return dict(contract_version=CONTRACT, status=status, text=text,
                evidence_ids=ids or [], failure_code=code)


def command_transport(executable, *, timeout=60):
    if not isinstance(executable, str) or not executable.startswith("/") or not 0 < timeout <= 240:
        raise ValueError("explicit AFM executable and valid timeout required")
    def send(request):
        response = subprocess.run([executable, "--provider", "afm"],
            input=json.dumps(request, ensure_ascii=False), text=True, capture_output=True,
            timeout=timeout, check=False)
        if response.returncode:
            raise ValueError("AFM extraction failed")
        return json.loads(response.stdout)
    return send


def extract(instruction, evidence, transport):
    request = dict(contract_version=CONTRACT, instruction=instruction, evidence=copy.deepcopy(evidence))
    text_valid = lambda t, n: isinstance(t, str) and bool(t.strip()) and len(t) <= n
    try:
        if (not text_valid(instruction, 500) or not isinstance(evidence, list) or len(evidence) > 8
                or any(set(e) != {"id", "text"} or not text_valid(e["id"], 80)
                       or not text_valid(e["text"], 1000) for e in evidence)
                or len({e["id"] for e in evidence}) != len(evidence)
                or len(json.dumps(request, ensure_ascii=False).encode()) > 12000):
            return result("failed", code="invalid_request")
    except (TypeError, KeyError):
        return result("failed", code="invalid_request")
    if not evidence:
        return result("no_information")
    try:
        response = transport(request)
    except Exception:
        return result("failed", code="generation_failed")
    try:
        if not isinstance(response, dict) or set(response) != set(result("failed")) or response["contract_version"] != CONTRACT:
            raise ValueError()
        if response == result("no_information"):
            return response
        if response["status"] == "failed" and response["failure_code"] in FAILURES and response == result("failed", code=response["failure_code"]):
            return copy.deepcopy(response)
        ids = response["evidence_ids"]
        if (response["status"] != "extracted" or response["failure_code"] is not None
                or not text_valid(response["text"], 300) or not isinstance(ids, list) or not 1 <= len(ids) <= 8
                or any(not isinstance(i, str) for i in ids) or len(set(ids)) != len(ids)
                or not set(ids) <= {e["id"] for e in evidence}):
            raise ValueError()
        return copy.deepcopy(response)
    except (ValueError, TypeError, KeyError):
        return result("failed", code="invalid_extraction")
