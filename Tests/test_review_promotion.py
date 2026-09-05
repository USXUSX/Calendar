import copy
import json
import sqlite3
import unittest
from unittest.mock import patch

from Sources.aig_trip_generation import receive_aig_result
from Sources.calendar_domain import ConflictError, GenerationWriteError, ValidationError
from Tests import test_aig_trip_generation as fixtures

TRIP_ID = fixtures.TRIP_ID


class ReviewPromotionTests(unittest.TestCase):
    setUp = fixtures.AIGTripGenerationTests.setUp
    tearDown = fixtures.AIGTripGenerationTests.tearDown

    def candidate(self):
        return json.loads(self.trip_path.read_bytes())

    def receive(self, candidate, generation='generation-1'):
        return receive_aig_result(self.domain, TRIP_ID, generation, {
            'status':'succeeded', 'generation_id':generation, 'trip_id':TRIP_ID, 'candidate':candidate,
        })

    def restart(self, policy='auto'):
        self.domain.fail_working_trip_generation(TRIP_ID, 'generation-1', 'manual_restart')
        return self.domain.start_working_trip_generation(TRIP_ID, 'generation-2', policy)

    def test_each_rule_promotes_same_generation_and_preserves_trip(self):
        for rule in ['R1', 'R2', 'R3']:
            with self.subTest(rule=rule):
                if rule != 'R1':
                    self.tearDown(); self.setUp()
                c = self.candidate()
                item = c['days'][0]['scheduleItems'][0]
                if rule == 'R1':
                    self.domain.save_working_trip_item_change(TRIP_ID, 'scheduleItem', item['id'],
                                                            'changed', {'status':'tentative'})
                elif rule == 'R2': c['summary'] = 'synthetic changed summary'
                else: c['days'][0]['scheduleItems'].pop(0)
                self.domain.fail_working_trip_generation(TRIP_ID, 'generation-1', 'manual_restart')
                generation = 'case-'+rule
                before = self.domain.start_working_trip_generation(TRIP_ID, generation, 'auto')
                original = self.trip_path.read_bytes()
                result = self.receive(c, generation)
                self.assertEqual(result['status'], 'candidate_ready')
                ready = self.domain.get_working_trip_generation(TRIP_ID)
                self.assertEqual((ready['generation_id'],ready['policy'],ready['state']),
                                 (generation,'review','candidate_ready'))
                self.assertEqual(ready['candidate'], c)
                for key in ['request_package','base_trip_version','base_effective_hash','working_state_digest']:
                    self.assertEqual(ready[key], before[key])
                self.assertEqual(self.trip_path.read_bytes(), original)
                self.assertEqual(self.domain.get_working_trip(TRIP_ID)['state'], before['request_package']['user_intent'])

    def test_promoted_candidate_uses_existing_confirmation_and_stale_gate(self):
        c = self.candidate(); c['summary'] = 'synthetic changed summary'
        self.receive(c)
        with self.assertRaises(ValidationError):
            self.domain.adopt_working_trip_generation_candidate(TRIP_ID, 'generation-1', c)
        result = self.domain.adopt_working_trip_generation_candidate(TRIP_ID, 'generation-1')
        self.assertEqual(result['status'], 'adopted')
        self.assertEqual(self.candidate(), c)
        self.assertIsNone(self.domain.get_working_trip_generation(TRIP_ID)['candidate'])
        self.assertFalse(self.domain.get_working_trip_detail_view(TRIP_ID)['working']['present'])

    def test_promoted_candidate_cannot_adopt_changed_working(self):
        c=self.candidate(); c['summary']='changed'
        original=self.trip_path.read_bytes(); self.receive(c)
        self.domain.save_working_trip_day_instruction(TRIP_ID, c['days'][0]['id'], 'new intent')
        with self.assertRaises(ConflictError):
            self.domain.adopt_working_trip_generation_candidate(TRIP_ID,'generation-1')
        self.assertEqual(self.trip_path.read_bytes(),original)

    def test_review_bypasses_rule_evaluation_and_auto_failure_does_not_adopt(self):
        c = self.candidate()
        with patch('Sources.aig_trip_generation.candidate_review_rules', side_effect=RuntimeError('private details')):
            result = self.receive(c)
            self.assertEqual(result['failure_code'],'diff_check_failed')
            self.assertNotIn('private details',json.dumps(result))
            self.assertIsNone(self.domain.get_working_trip_generation(TRIP_ID)['candidate'])
            self.domain.start_working_trip_generation(TRIP_ID,'generation-2','review')
            self.assertEqual(self.receive(c,'generation-2')['status'],'candidate_ready')

    def test_unknown_structured_field_stops_auto(self):
        item=self.candidate()['days'][0]['scheduleItems'][0]
        self.domain.save_working_trip(TRIP_ID, {
            'item_changes':[dict(source_type='scheduleItem',source_item_id=item['id'],
                                 disposition='changed',changes={'unknown':'private'})],
            'temporary_items':[],'day_instructions':[],
        })
        self.restart()
        self.assertEqual(self.receive(self.candidate(),'generation-2')['failure_code'],'diff_check_failed')

    def test_valid_insert_does_not_promote_auto(self):
        c=self.candidate(); day=c['days'][0]
        new=copy.deepcopy(day['scheduleItems'][0]); new.update(id='schedule-added',order=5)
        day['scheduleItems'].insert(0,new)
        self.assertEqual(self.receive(c)['status'],'adopted')

    def test_competing_changes_between_validation_and_promotion(self):
        for kind in ['working','override','todo']:
            with self.subTest(kind=kind):
                # Independent domain setup to keep each race isolated.
                if kind != 'working': self.tearDown(); self.setUp()
                c=self.candidate(); removed=c['days'][0]['scheduleItems'].pop(0)
                original_transition=self.domain._transition_working_trip_generation
                def interleave(*args, **kwargs):
                    if kwargs.get('promotion_candidate') is not None:
                        if kind == 'working':
                            self.domain.save_working_trip_day_instruction(TRIP_ID,c['days'][0]['id'],'new intent')
                        elif kind == 'override':
                            self.domain.set_direct_override('override-race',TRIP_ID,removed['id'],'/status','tentative')
                        else:
                            self.domain.create_todo('todo-race',label='synthetic',trip_id=TRIP_ID,trip_item_id=removed['id'])
                    return original_transition(*args, **kwargs)
                original=self.trip_path.read_bytes()
                with patch.object(self.domain,'_transition_working_trip_generation',side_effect=interleave):
                    result=self.receive(c)
                self.assertEqual(result['failure_code'],'obsolete_working')
                self.assertEqual(self.trip_path.read_bytes(),original)
                self.assertIsNone(self.domain.get_working_trip_generation(TRIP_ID)['candidate'])

    def test_old_duplicate_and_post_check_replacement_do_not_damage_latest(self):
        c=self.candidate(); c['summary']='changed'
        self.receive(c)
        ready=self.domain.get_working_trip_generation(TRIP_ID)
        with self.assertRaises(ConflictError): self.receive(c)
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID),ready)
        new=self.domain.start_working_trip_generation(TRIP_ID,'generation-2','auto')
        with self.assertRaises(ConflictError): self.receive(c)
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID),new)

        original=self.domain._transition_working_trip_generation
        def replace(*args,**kwargs):
            if kwargs.get('promotion_candidate') is not None:
                self.domain.fail_working_trip_generation(TRIP_ID,'generation-2','manual_restart')
                self.domain.start_working_trip_generation(TRIP_ID,'generation-3','auto')
            return original(*args,**kwargs)
        with patch.object(self.domain,'_transition_working_trip_generation',side_effect=replace):
            with self.assertRaises(ConflictError): self.receive(c,'generation-2')
        latest=self.domain.get_working_trip_generation(TRIP_ID)
        self.assertEqual((latest['generation_id'],latest['state']),('generation-3','generating'))

    def test_promotion_update_zero_rows_is_conflict(self):
        c=self.candidate(); c['summary']='changed'
        before=self.domain.get_working_trip_generation(TRIP_ID)
        with sqlite3.connect(self.db_path) as db:
            db.execute("CREATE TRIGGER skip_promotion BEFORE UPDATE ON working_trip_generations "
                       "WHEN NEW.policy='review' BEGIN SELECT RAISE(IGNORE); END")
        with self.assertRaises(ConflictError):
            self.domain.promote_working_trip_generation_candidate(TRIP_ID,'generation-1',c)
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID),before)

    def test_write_failure_after_update_rolls_back_all_promotion_fields(self):
        c=self.candidate(); c['summary']='changed'
        before=self.domain.get_working_trip_generation(TRIP_ID)
        original=self.trip_path.read_bytes()
        with sqlite3.connect(self.db_path) as db:
            db.execute("CREATE TRIGGER abort_promotion AFTER UPDATE ON working_trip_generations "
                       "WHEN NEW.policy='review' BEGIN SELECT RAISE(ABORT,'private database detail'); END")
        with self.assertRaises(GenerationWriteError) as caught: self.receive(c)
        self.assertNotIn('private database detail',str(caught.exception))
        self.assertEqual(self.domain.get_working_trip_generation(TRIP_ID),before)
        self.assertEqual(self.trip_path.read_bytes(),original)
