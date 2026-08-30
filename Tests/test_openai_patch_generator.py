import io
import json
import shutil
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from Sources.calendar_domain import CalendarDomain
from Sources.calendar_worker import run_once
from Sources.openai_patch_generator import (
    OpenAIPatchError, build_request, extract_patch, generate_patch, main, validate_patch,
)
from scripts.init_calendar_db import initialize

ROOT = Path(__file__).resolve().parents[1]
TRIP_ID = "trip-setouchi-2027"
ACTION_PATH = "/days/0/scheduleItems/0/action"


def claim_payload():
    return {
        "request_id": "request-1",
        "instruction_id": "instruction-1",
        "trip_id": TRIP_ID,
        "instruction": "Change breakfast to lunch",
        "base_version": 1,
        "base_hash": "a" * 64,
        "trip": {"id": TRIP_ID, "days": []},
    }


def response_for(patch):
    return {
        "status": "completed",
        "output": [{
            "type": "message",
            "content": [{"type": "output_text", "text": json.dumps({"patch": patch})}],
        }],
    }


class OpenAIPatchGeneratorTests(unittest.TestCase):
    def test_request_contains_semantic_input_and_structured_output_only(self):
        request = build_request(claim_payload(), "explicit-model")
        self.assertEqual(request["model"], "explicit-model")
        self.assertFalse(request["store"])
        self.assertNotIn("tools", request)
        semantic = json.loads(request["input"][1]["content"])
        self.assertEqual(set(semantic), set(claim_payload()))
        self.assertEqual(semantic["instruction"], "Change breakfast to lunch")
        self.assertEqual(semantic["trip"]["id"], TRIP_ID)
        self.assertEqual(request["text"]["format"]["type"], "json_schema")
        self.assertFalse(request["text"]["format"]["strict"])

    def test_single_and_multi_patch_response(self):
        single = [{"op": "replace", "path": ACTION_PATH, "value": "Lunch"}]
        self.assertEqual(extract_patch(response_for(single)), single)
        multi = [*single, {"op": "remove", "path": "/days/0/note"}]
        self.assertEqual(extract_patch(response_for(multi)), multi)

    def test_invalid_response_and_patch_shapes_are_rejected(self):
        invalid_values = (
            "not-json",
            json.dumps({"patch": [{"op": "move", "path": "/a"}]}),
            json.dumps({"patch": [{"op": "add", "path": "/a"}]}),
            json.dumps({"patch": [{"op": "remove", "path": "/a", "value": 1}]}),
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(OpenAIPatchError):
                extract_patch({
                    "status": "completed",
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": value}]}],
                })
        for response in (
            {"status": "incomplete", "output": []},
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]},
        ):
            with self.assertRaises(OpenAIPatchError):
                extract_patch(response)

    def test_transport_request_uses_key_without_leaking_it(self):
        observed = {}
        patch = [{"op": "replace", "path": ACTION_PATH, "value": "Lunch"}]
        def transport(request, timeout):
            observed["url"] = request.full_url
            observed["authorization"] = request.get_header("Authorization")
            observed["payload"] = json.loads(request.data)
            observed["timeout"] = timeout
            return json.dumps(response_for(patch)).encode()
        self.assertEqual(generate_patch(
            claim_payload(), api_key="test-secret", model="test-model", timeout=3, transport=transport
        ), patch)
        self.assertEqual(observed["authorization"], "Bearer test-secret")
        self.assertNotIn("test-secret", json.dumps(observed["payload"]))

    def test_cli_stdout_is_patch_only_and_failures_are_nonzero(self):
        patch = [{"op": "replace", "path": ACTION_PATH, "value": "Lunch"}]
        def success(request, timeout):
            return json.dumps(response_for(patch)).encode()
        stdout, stderr = io.StringIO(), io.StringIO()
        code = main(
            ["--model", "test-model"],
            environ={"OPENAI_API_KEY": "test-secret"},
            stdin=io.StringIO(json.dumps(claim_payload())), stdout=stdout, stderr=stderr,
            transport=success,
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(stdout.getvalue()), patch)
        self.assertEqual(stderr.getvalue(), "")

        for environment, transport in (
            ({}, success),
            ({"OPENAI_API_KEY": "test-secret"}, lambda request, timeout: (_ for _ in ()).throw(OpenAIPatchError("request failed"))),
        ):
            stdout, stderr = io.StringIO(), io.StringIO()
            code = main(
                ["--model", "test-model"], environ=environment,
                stdin=io.StringIO(json.dumps(claim_payload())), stdout=stdout, stderr=stderr,
                transport=transport,
            )
            self.assertEqual(code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertNotIn("test-secret", stderr.getvalue())

    def test_default_transport_maps_http_network_and_timeout_without_response_body(self):
        failures = (
            urllib.error.HTTPError("https://api.openai.com/v1/responses", 500, "failed", {}, io.BytesIO(b"private body")),
            urllib.error.URLError("offline"),
            TimeoutError("slow"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__), patch(
                "urllib.request.urlopen", side_effect=failure
            ), self.assertRaisesRegex(OpenAIPatchError, "OpenAI API request failed") as raised:
                generate_patch(
                    claim_payload(), api_key="test-secret", model="test-model", timeout=2
                )
            self.assertNotIn("test-secret", str(raised.exception))
            self.assertNotIn("private body", str(raised.exception))

    def test_fake_openai_adapter_drives_existing_worker_pipeline(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            db_path = root / "calendar.sqlite3"
            trip_root = root / "trip-data"
            (trip_root / "trips").mkdir(parents=True)
            shutil.copyfile(ROOT / "Samples" / "synthetic-trip.json", trip_root / "trips" / f"{TRIP_ID}.json")
            initialize(db_path)
            domain = CalendarDomain(db_path, trip_root)
            domain.register_trip(TRIP_ID)
            domain.add_ai_instruction("instruction-1", TRIP_ID, "Change breakfast")
            patch = [{"op": "replace", "path": ACTION_PATH, "value": "OpenAI fake"}]
            result = run_once(domain, lambda claim: generate_patch(
                claim, api_key="test-secret", model="test-model", timeout=2,
                transport=lambda request, timeout: json.dumps(response_for(patch)).encode(),
            ))
            self.assertEqual(result["status"], "adopted")
            with sqlite3.connect(db_path) as connection:
                self.assertEqual(connection.execute(
                    "SELECT state FROM generation_requests WHERE id = 'instruction-1'"
                ).fetchone()[0], "completed")
            self.assertNotIn("Calendar_Local", str(db_path))


if __name__ == "__main__":
    unittest.main()
