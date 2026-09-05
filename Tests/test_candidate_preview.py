import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from Tests import test_aig_trip_generation as fixtures
from Sources.aig_trip_generation import receive_aig_result
from Sources.calendar_domain import ConflictError, NotFoundError, ValidationError
from Sources.calendar_domain.trip_detail import build_trip_detail_view

TRIP_ID = fixtures.TRIP_ID


class CandidatePreviewTests(unittest.TestCase):
    setUp = fixtures.AIGTripGenerationTests.setUp
    tearDown = fixtures.AIGTripGenerationTests.tearDown

    def ready(self, policy='review'):
        self.domain.fail_working_trip_generation(TRIP_ID, 'generation-1', 'manual_restart')
        self.domain.start_working_trip_generation(TRIP_ID, 'generation-2', policy)
        candidate = json.loads(self.trip_path.read_bytes())
        candidate['summary'] = 'Synthetic candidate-only summary'
        candidate['days'][0]['scheduleItems'][0]['action'] = 'Synthetic preview title'
        result = receive_aig_result(self.domain, TRIP_ID, 'generation-2', {
            'status': 'succeeded', 'trip_id': TRIP_ID,
            'generation_id': 'generation-2', 'candidate': candidate,
        })
        self.assertEqual(result['status'], 'candidate_ready')
        return candidate

    def preview(self, generation='generation-2'):
        return self.domain.get_working_trip_generation_candidate_preview(TRIP_ID, generation)

    def snapshot(self):
        with sqlite3.connect(self.db_path) as connection:
            database = '\n'.join(connection.iterdump())
        return database, self.trip_path.read_bytes()

    def test_both_review_origins_share_timeline_and_are_read_only(self):
        models = []
        for policy in ('review', 'auto'):
            with self.subTest(policy=policy):
                if policy == 'auto':
                    self.tearDown()
                    self.setUp()
                candidate = self.ready(policy)
                before = self.snapshot()
                preview = self.preview()
                self.assertEqual(self.snapshot(), before)
                expected = build_trip_detail_view(candidate)
                for day in expected['days']:
                    for entry in day['entries']:
                        entry['direct_edit_paths'] = {}
                        entry['ai_local_update_target'] = None
                self.assertEqual(preview, {
                    'trip_id': TRIP_ID, 'generation_id': 'generation-2',
                    'state': 'candidate_ready', 'policy': 'review', 'view': expected,
                })
                self.assertNotIn(candidate['summary'], json.dumps(preview))
                models.append(copy.deepcopy(preview))
                preview['view']['days'].clear()
                self.assertEqual(self.snapshot(), before)
        self.assertEqual(*models)

    def test_non_ready_states_have_no_preview_and_do_not_write(self):
        for state in ('generating', 'failed', 'adopted', 'idle'):
            with self.subTest(state=state):
                if state == 'failed':
                    self.domain.fail_working_trip_generation(TRIP_ID, 'generation-1', 'synthetic')
                elif state == 'adopted':
                    self.domain.start_working_trip_generation(TRIP_ID, 'generation-1', 'auto')
                    self.domain.adopt_working_trip_generation_candidate(
                        TRIP_ID, 'generation-1', json.loads(self.trip_path.read_bytes()))
                elif state == 'idle':
                    self.domain.start_working_trip(TRIP_ID)
                before = self.snapshot()
                with self.assertRaises((ConflictError, NotFoundError)):
                    self.preview('generation-1')
                self.assertEqual(self.snapshot(), before)

    def test_identity_working_stale_obsolete_and_revision_are_rejected_read_only(self):
        for scenario in ('identity', 'working', 'stale', 'obsolete', 'revision', 'policy', 'invalid'):
            with self.subTest(scenario=scenario):
                if scenario != 'identity':
                    self.tearDown()
                    self.setUp()
                candidate = self.ready()
                generation = 'generation-2'
                if scenario == 'identity':
                    generation = 'old-generation'
                elif scenario == 'working':
                    self.domain.save_working_trip_day_instruction(
                        TRIP_ID, candidate['days'][0]['id'], 'Changed intent')
                elif scenario == 'stale':
                    self.domain.set_direct_override('override-preview', TRIP_ID,
                        candidate['days'][0]['scheduleItems'][0]['id'], '/status', 'tentative')
                elif scenario == 'obsolete':
                    self.domain.start_working_trip_generation(TRIP_ID, 'generation-3', 'review')
                elif scenario in ('revision', 'policy', 'invalid'):
                    with sqlite3.connect(self.db_path) as connection:
                        if scenario == 'revision':
                            connection.execute('UPDATE working_trip_generations SET base_trip_version = 99')
                        elif scenario == 'policy':
                            connection.execute("UPDATE working_trip_generations SET policy = 'auto'")
                        else:
                            connection.execute("UPDATE working_trip_generations SET candidate_json = '{}'")
                before = self.snapshot()
                with self.assertRaises((ConflictError, ValidationError)):
                    self.preview(generation)
                self.assertEqual(self.snapshot(), before)

    def test_working_change_during_conversion_rejects_preview(self):
        candidate = self.ready()
        def convert(value):
            self.domain.save_working_trip_day_instruction(
                TRIP_ID, candidate['days'][0]['id'], 'Concurrent intent')
            return build_trip_detail_view(value)
        with patch('Sources.calendar_domain.service.build_trip_detail_view', side_effect=convert):
            with self.assertRaises(ConflictError):
                self.preview()
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID)['state'], 'candidate_ready')

    def test_preview_then_confirmation_uses_existing_atomic_adoption(self):
        candidate = self.ready()
        self.preview()
        with patch.object(self.domain, '_adopt_candidate_atomically',
                          wraps=self.domain._adopt_candidate_atomically) as adopt:
            result = self.domain.adopt_working_trip_generation_candidate(TRIP_ID, 'generation-2')
        adopt.assert_called_once()
        self.assertEqual(result['status'], 'adopted')
        self.assertEqual(json.loads(self.trip_path.read_bytes()), candidate)
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID)['state'], 'adopted')
        with self.assertRaises(NotFoundError):
            self.domain.get_working_trip(TRIP_ID)

    def test_preview_does_not_bypass_later_confirmation_gate(self):
        candidate = self.ready()
        self.preview()
        self.domain.save_working_trip_day_instruction(TRIP_ID, candidate['days'][0]['id'], 'New intent')
        before = self.snapshot()
        with self.assertRaises(ConflictError):
            self.domain.adopt_working_trip_generation_candidate(TRIP_ID, 'generation-2')
        self.assertEqual(self.snapshot(), before)
