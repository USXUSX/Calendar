import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from Sources.aig_trip_generation import receive_aig_result
from Sources.calendar_domain import CalendarDomain, ConflictError
from scripts.init_calendar_db import initialize


class CandidateDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.trip_id = 'trip-setouchi-2027'
        trip_root = root / 'data'
        (trip_root / 'trips').mkdir(parents=True)
        self.path = trip_root / 'trips' / (self.trip_id + '.json')
        shutil.copy(Path(__file__).resolve().parents[1] / 'Samples/synthetic-trip.json', self.path)
        self.original = self.path.read_bytes()
        self.candidate = json.loads(self.original)
        db = root / 'calendar.sqlite3'
        initialize(db)
        self.domain = CalendarDomain(db, trip_root)
        self.domain.register_trip(self.trip_id, 'participants')
        self.domain.start_working_trip(self.trip_id)
        self.domain.start_working_trip_generation(self.trip_id, 'diagnostic-1', 'auto')

    def diagnose(self, candidate, expected):
        before = self.domain.get_working_trip_generation(self.trip_id)
        working = self.domain.get_working_trip(self.trip_id)
        untouched = copy.deepcopy(candidate)
        stage = self.domain.diagnose_working_trip_generation_candidate(
            self.trip_id, 'diagnostic-1', candidate,
        )
        self.assertEqual(stage, expected)
        self.assertTrue(candidate == untouched)
        self.assertTrue(self.domain.get_working_trip_generation(self.trip_id) == before)
        self.assertTrue(self.domain.get_working_trip(self.trip_id) == working)
        self.assertTrue(self.path.read_bytes() == self.original)

    def receive(self, candidate, code):
        result = receive_aig_result(self.domain, self.trip_id, 'diagnostic-1', {
            'generation_id': 'diagnostic-1', 'trip_id': self.trip_id,
            'status': 'succeeded', 'candidate': candidate,
        })
        self.assertEqual(result, {
            'generation_id': 'diagnostic-1', 'trip_id': self.trip_id,
            'status': 'failed', 'failure_code': code,
        })
        self.assertIsNone(self.domain.get_working_trip_generation(self.trip_id)['candidate'])
        self.assertTrue(self.path.read_bytes() == self.original)

    def test_schema_precedes_semantic_and_does_not_leak_property_or_value(self):
        self.candidate['secret-candidate-key'] = 'secret-candidate-value'
        self.candidate['days'][0]['transportIds'].append('secret-missing-reference')
        self.diagnose(self.candidate, 'schema')
        self.receive(self.candidate, 'invalid_candidate')

    def test_semantic_reference_does_not_leak_identifier(self):
        self.candidate['days'][0]['transportIds'].append('secret-missing-reference')
        self.diagnose(self.candidate, 'semantic_reference')
        self.receive(self.candidate, 'invalid_candidate')

    def test_identity_constraint_preserves_normal_failure(self):
        self.candidate['id'] = 'secret-other-trip'
        self.diagnose(self.candidate, 'constraint')
        self.receive(self.candidate, 'invalid_candidate')

    def test_todo_constraint_preserves_existing_conflict_mapping(self):
        item = self.candidate['days'][0]['scheduleItems'][0]
        self.domain.create_todo('diagnostic-todo', label='synthetic',
                                trip_id=self.trip_id, trip_item_id=item['id'])
        self.candidate['days'][0]['scheduleItems'].remove(item)
        self.diagnose(self.candidate, 'constraint')
        self.receive(self.candidate, 'obsolete_working')

    def test_explanatory_split_activity_can_validate_without_participant_schema(self):
        items = self.candidate['days'][1]['scheduleItems']
        items[0]['action'] = '一部参加者は既存の予定へ行く'
        items[1]['action'] = '残りの参加者は別の既存予定で過ごす'
        self.diagnose(self.candidate, 'valid')

    def test_obsolete_working_is_not_a_candidate_stage(self):
        self.domain.save_working_trip_day_instruction(
            self.trip_id, self.candidate['days'][0]['id'], 'changed after start',
        )
        with self.assertRaises(ConflictError):
            self.domain.diagnose_working_trip_generation_candidate(
                self.trip_id, 'diagnostic-1', self.candidate,
            )

    def test_non_json_candidate_is_schema(self):
        self.diagnose([], 'schema')
        self.candidate['summary'] = float('inf')
        self.diagnose(self.candidate, 'schema')


if __name__ == '__main__':
    unittest.main()
