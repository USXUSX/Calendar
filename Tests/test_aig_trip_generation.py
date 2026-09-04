import json
import shutil
import tempfile
import unittest
from pathlib import Path

from Sources.aig_trip_generation import command_transport, run_started_generation
from Sources.calendar_domain import CalendarDomain, ConflictError
from scripts.init_calendar_db import initialize

REPO_ROOT = Path(__file__).resolve().parents[1]
TRIP_ID = "trip-setouchi-2027"


class AIGTripGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.db_path = root / "calendar.sqlite3"
        self.trip_root = root / "trip-data"
        (self.trip_root / "trips").mkdir(parents=True)
        self.trip_path = self.trip_root / "trips" / f"{TRIP_ID}.json"
        shutil.copy(REPO_ROOT / "Samples/synthetic-trip.json", self.trip_path)
        initialize(self.db_path)
        self.domain = CalendarDomain(self.db_path, self.trip_root)
        self.domain.register_trip(TRIP_ID, "participants")
        self.domain.save_working_trip(TRIP_ID, {
            "item_changes": [], "temporary_items": [], "day_instructions": [],
        })
        self.started = self.domain.start_working_trip_generation(
            TRIP_ID, "generation-1", "auto",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_auto_policy_rechecks_and_adopts_through_phase_5(self):
        candidate = json.loads(self.trip_path.read_bytes())
        seen = []

        def transport(request):
            seen.append(request)
            return {
                "generation_id": "generation-1", "trip_id": TRIP_ID,
                "status": "succeeded", "candidate": candidate,
            }

        result = run_started_generation(
            self.domain, TRIP_ID, "generation-1", transport,
        )
        self.assertEqual((result["status"], result["generation_state"]), ("adopted", "adopted"))
        self.assertEqual(seen, [{
            "contract_version": "cal.aig.complete-trip-generation.v1",
            "generation_id": "generation-1",
            "trip_id": TRIP_ID,
            "working_export_package": self.started["request_package"],
        }])
        generation = self.domain.get_working_trip_generation(TRIP_ID)
        self.assertEqual((generation["state"], generation["adopted_version"]), ("adopted", 2))
        self.assertEqual(generation["adopted_digest"], result["candidate_digest"])
        self.assertIsNone(generation["candidate"])
        self.assertEqual(json.loads(self.trip_path.read_bytes()), candidate)
        restarted = self.domain.start_working_trip(TRIP_ID)
        self.assertEqual(restarted["state"], {
            "item_changes": [], "temporary_items": [], "day_instructions": [],
        })
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID)["state"], "idle")

    def test_review_policy_retains_candidate_then_confirms_through_same_gate(self):
        self.domain.fail_working_trip_generation(TRIP_ID, "generation-1", "manual_restart")
        self.domain.start_working_trip_generation(TRIP_ID, "generation-2", "review")
        candidate = json.loads(self.trip_path.read_bytes())
        result = run_started_generation(self.domain, TRIP_ID, "generation-2", lambda _: {
            "generation_id": "generation-2", "trip_id": TRIP_ID,
            "status": "succeeded", "candidate": candidate,
        })
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID)["state"], "candidate_ready")
        confirmed = self.domain.adopt_working_trip_generation_candidate(TRIP_ID, "generation-2")
        self.assertEqual((confirmed["status"], confirmed["generation_state"]),
                         ("adopted", "adopted"))
        generation = self.domain.get_working_trip_generation(TRIP_ID)
        self.assertEqual((generation["state"], generation["candidate"]), ("adopted", None))

    def test_review_confirmation_rechecks_working_content_without_mutating_trip(self):
        self.domain.fail_working_trip_generation(TRIP_ID, "generation-1", "manual_restart")
        self.domain.start_working_trip_generation(TRIP_ID, "generation-2", "review")
        candidate = json.loads(self.trip_path.read_bytes())
        original = self.trip_path.read_bytes()
        run_started_generation(self.domain, TRIP_ID, "generation-2", lambda _: {
            "generation_id": "generation-2", "trip_id": TRIP_ID,
            "status": "succeeded", "candidate": candidate,
        })
        self.domain.save_working_trip_day_instruction(
            TRIP_ID, candidate["days"][0]["id"], "edited after review candidate",
        )
        with self.assertRaisesRegex(ConflictError, "content does not match"):
            self.domain.adopt_working_trip_generation_candidate(TRIP_ID, "generation-2")
        self.assertEqual(self.trip_path.read_bytes(), original)
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID)["state"],
                         "candidate_ready")
        self.assertIn("edited after review candidate",
                      json.dumps(self.domain.get_working_trip(TRIP_ID)["state"]))

    def test_rechecks_digest_before_candidate_enters_phase_5_validation(self):
        candidate = json.loads(self.trip_path.read_bytes())

        def transport(_):
            self.domain.save_working_trip_day_instruction(
                TRIP_ID, candidate["days"][0]["id"], "changed after AIG request",
            )
            return {
                "generation_id": "generation-1", "trip_id": TRIP_ID,
                "status": "succeeded", "candidate": candidate,
            }

        result = run_started_generation(
            self.domain, TRIP_ID, "generation-1", transport,
        )
        self.assertEqual((result["status"], result["failure_code"]),
                         ("failed", "obsolete_working"))
        replacement = self.domain.start_working_trip_generation(
            TRIP_ID, "generation-2", "auto",
        )
        self.assertEqual((replacement["generation_id"], replacement["state"]),
                         ("generation-2", "generating"))

    def test_phase_5_validation_rejects_invalid_candidate(self):
        candidate = json.loads(self.trip_path.read_bytes())
        candidate["days"][0]["transportIds"] = ["missing-transport"]
        result = run_started_generation(self.domain, TRIP_ID, "generation-1", lambda _: {
            "generation_id": "generation-1", "trip_id": TRIP_ID,
            "status": "succeeded", "candidate": candidate,
        })
        self.assertEqual((result["status"], result["failure_code"]),
                         ("failed", "invalid_candidate"))
        replacement = self.domain.start_working_trip_generation(
            TRIP_ID, "generation-2", "review",
        )
        self.assertEqual((replacement["generation_id"], replacement["state"]),
                         ("generation-2", "generating"))

    def test_safe_failure_and_transport_failure_enter_failed_state_once(self):
        result = run_started_generation(self.domain, TRIP_ID, "generation-1", lambda _: {
            "generation_id": "generation-1", "trip_id": TRIP_ID,
            "status": "failed", "failure_code": "generation_failed",
        })
        self.assertEqual((result["status"], result["failure_code"]),
                         ("failed", "generation_failed"))

        self.domain.start_working_trip_generation(TRIP_ID, "generation-2", "review")
        result = run_started_generation(
            self.domain, TRIP_ID, "generation-2",
            lambda _: (_ for _ in ()).throw(RuntimeError("provider secret")),
        )
        self.assertEqual(result["failure_code"], "transport_failed")
        self.assertNotIn("provider secret", json.dumps(result))

    def test_mismatched_identity_does_not_change_latest_generation(self):
        with self.assertRaisesRegex(ConflictError, "identity does not match"):
            run_started_generation(self.domain, TRIP_ID, "generation-1", lambda _: {
                "generation_id": "late-generation", "trip_id": TRIP_ID,
                "status": "failed", "failure_code": "generation_failed",
            })
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID)["state"], "generating")

    def test_command_transport_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            command_transport([], 60)
        with self.assertRaises(ValueError):
            command_transport(["aig-trip-generation"], 0)


if __name__ == "__main__":
    unittest.main()
