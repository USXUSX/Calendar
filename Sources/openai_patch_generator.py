"""OpenAI Responses API adapter for CAL semantic payload -> JSON Patch."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any, TextIO

RESPONSES_URL = "https://api.openai.com/v1/responses"
CLAIM_FIELDS = {
    "request_id", "instruction_id", "trip_id", "instruction",
    "base_version", "base_hash", "trip",
}


class OpenAIPatchError(Exception):
    """Safe diagnostic for adapter input, transport, or response failure."""


PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "patch": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "op": {"type": "string", "enum": ["add", "remove", "replace"]},
                    "path": {"type": "string"},
                    "value": {},
                },
                "required": ["op", "path"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["patch"],
    "additionalProperties": False,
}

SYSTEM_INSTRUCTION = """Generate the smallest JSON Patch that applies the user's instruction to the supplied complete Trip.
Return only the structured patch. Use only add, remove, and replace with paths against the supplied base Trip.
Do not change unrelated fields or stable IDs. Do not replace the whole Trip; for large changes replace only the necessary day or object.
Preserve the Trip contract. CAL performs final JSON Pointer, Schema, semantic, conflict, and adoption validation."""


def validate_claim(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not CLAIM_FIELDS <= set(value):
        raise OpenAIPatchError("stdin must contain one CAL semantic claim payload")
    for field in ("request_id", "instruction_id", "trip_id", "instruction", "base_hash"):
        if not isinstance(value[field], str) or not value[field]:
            raise OpenAIPatchError(f"claim field is invalid: {field}")
    if not isinstance(value["base_version"], int) or isinstance(value["base_version"], bool):
        raise OpenAIPatchError("claim field is invalid: base_version")
    if not isinstance(value["trip"], dict):
        raise OpenAIPatchError("claim field is invalid: trip")
    return value


def build_request(claim: dict[str, Any], model: str) -> dict[str, Any]:
    if not isinstance(model, str) or not model:
        raise OpenAIPatchError("model must be explicitly specified")
    semantic_input = {
        "request_id": claim["request_id"],
        "instruction_id": claim["instruction_id"],
        "trip_id": claim["trip_id"],
        "instruction": claim["instruction"],
        "base_version": claim["base_version"],
        "base_hash": claim["base_hash"],
        "trip": claim["trip"],
    }
    return {
        "model": model,
        "store": False,
        "input": [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": json.dumps(semantic_input, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "calendar_json_patch",
                # JSON Patch value accepts arbitrary JSON and is absent for remove.
                # Keep the API schema helpful but rely on validate_patch and CAL for authority.
                "strict": False,
                "schema": PATCH_SCHEMA,
            }
        },
    }


def validate_patch(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise OpenAIPatchError("OpenAI output must be a non-empty JSON Patch array")
    for operation in value:
        if not isinstance(operation, dict) or set(operation) - {"op", "path", "value"}:
            raise OpenAIPatchError("OpenAI output contains an invalid Patch operation")
        op = operation.get("op")
        if op not in {"add", "remove", "replace"} or not isinstance(operation.get("path"), str):
            raise OpenAIPatchError("OpenAI output contains an unsupported Patch operation")
        if op in {"add", "replace"} and "value" not in operation:
            raise OpenAIPatchError("OpenAI add/replace operation is missing value")
        if op == "remove" and "value" in operation:
            raise OpenAIPatchError("OpenAI remove operation has an unexpected value")
    return value


def extract_patch(response: Any) -> list[dict[str, Any]]:
    if not isinstance(response, dict) or response.get("status") != "completed":
        raise OpenAIPatchError("OpenAI response is incomplete")
    output = response.get("output")
    if not isinstance(output, list):
        raise OpenAIPatchError("OpenAI response has no output")
    texts = []
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "refusal":
                raise OpenAIPatchError("OpenAI refused to generate a Patch")
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                texts.append(content["text"])
    if len(texts) != 1:
        raise OpenAIPatchError("OpenAI response must contain exactly one text output")
    try:
        structured = json.loads(texts[0])
    except json.JSONDecodeError as error:
        raise OpenAIPatchError("OpenAI output is not valid JSON") from error
    if not isinstance(structured, dict) or set(structured) != {"patch"}:
        raise OpenAIPatchError("OpenAI structured output has an invalid shape")
    return validate_patch(structured["patch"])


Transport = Callable[[urllib.request.Request, float], bytes]


def _urlopen_transport(request: urllib.request.Request, timeout: float) -> bytes:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        raise OpenAIPatchError("OpenAI API request failed") from error


def generate_patch(
    claim: dict[str, Any], *, api_key: str, model: str, timeout: float,
    transport: Transport = _urlopen_transport,
) -> list[dict[str, Any]]:
    if not api_key:
        raise OpenAIPatchError("OPENAI_API_KEY is not set")
    if timeout <= 0:
        raise OpenAIPatchError("timeout must be positive")
    payload = json.dumps(build_request(validate_claim(claim), model), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        RESPONSES_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        response = json.loads(transport(request, timeout).decode("utf-8"))
    except OpenAIPatchError:
        raise
    except (UnicodeError, json.JSONDecodeError) as error:
        raise OpenAIPatchError("OpenAI API response is not valid JSON") from error
    return extract_patch(response)


def main(
    argv: list[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    transport: Transport = _urlopen_transport,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=environ.get("OPENAI_MODEL"))
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        claim = json.load(stdin)
        patch = generate_patch(
            claim,
            api_key=environ.get("OPENAI_API_KEY", ""),
            model=args.model,
            timeout=args.timeout,
            transport=transport,
        )
    except (OpenAIPatchError, json.JSONDecodeError) as error:
        print(f"OpenAI Patch generator failed: {error}", file=stderr)
        return 1
    json.dump(patch, stdout, ensure_ascii=False, separators=(",", ":"))
    stdout.write("\n")
    return 0
