import copy
import json
import unittest
from unittest.mock import patch

import test_trip_chat
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError


class TripAITest(unittest.TestCase):
    def setUp(self):
        test_trip_chat.TripChatTest.setUp(self)
        self.cal.apply_trip_request(test_trip_chat.TripChatTest.create(self))
        self.context = self.cal.get_trip_command_context(self.tid)

    attempts = test_trip_chat.TripChatTest.attempts

    def generate(self, mutate=None, **kwargs):
        def transport(envelope):
            self.assertEqual(envelope['working_export_package']['effective_trip'], self.context['trip'])
            self.assertIn('generation_guide', envelope['working_export_package'])
            candidate = copy.deepcopy(envelope['working_export_package']['effective_trip'])
            if mutate: mutate(candidate)
            else: candidate['days'][0]['scheduleItems'][0]['summary'] = '合成AI変更'
            return dict(generation_id=envelope['generation_id'], trip_id=self.tid, status='succeeded', candidate=candidate)
        return self.cal.propose_trip_update(self.tid, self.context['revision'], '初日のコメントを変更', kwargs.get('transport', transport))

    def approval(self, proposal):
        return dict(request_id=proposal['request_id'], trip_id=self.tid, operation='ai', expected_revision=proposal['expected_revision'], values=dict(proposal_id=proposal['proposal_id'], confirmed=True))

    def test_preview_cancel_approval_and_replay(self):
        proposal = self.generate()
        self.assertTrue(proposal['changes'])
        self.assertEqual(self.cal.get_trip_command_context(self.tid), self.context)
        self.assertEqual(self.cal.lookup_chat_request(proposal['request_id'])['status'], 'not_found')
        request = self.approval(proposal)
        with self.assertRaises(ValidationError):
            self.cal.apply_trip_operation(dict(request, values=dict(request['values'], confirmed=False)))
        # Cancellation is discard-only. Restart and apply the exact frozen proposal.
        restarted = CalendarDomain(self.db, self.root)
        result = restarted.apply_trip_operation(request)
        self.assertEqual(result['status'], 'committed')
        expected = copy.deepcopy(self.context['trip'])
        expected['days'][0]['scheduleItems'][0]['summary'] = '合成AI変更'
        self.assertEqual(restarted.get_effective_trip(self.tid), expected)
        self.assertEqual(restarted.lookup_chat_request(request['request_id'])['receipt'], result['receipt'])
        self.assertEqual(restarted.apply_trip_operation(request)['resolution'], 'replayed')
        with self.assertRaises(ConflictError):
            restarted.apply_trip_operation(dict(request, request_id='different'))

    def test_conflict_generation_failure_and_invalid_candidate(self):
        proposal = self.generate()
        self.cal.apply_trip_operation(dict(request_id='other', trip_id=self.tid, operation='instruction', expected_revision=self.context['revision'], values={'instruction':'別の指示'}))
        with self.assertRaises(ConflictError): self.cal.apply_trip_operation(self.approval(proposal))
        with self.assertRaises(ConflictError): self.generate()
        self.context = self.cal.get_trip_command_context(self.tid)
        before = copy.deepcopy(self.context)
        def fail(_): raise RuntimeError('private transport error')
        for transport in (fail, lambda _: {}, lambda e:dict(generation_id=e['generation_id'], trip_id=self.tid, status='failed')):
            with self.assertRaises(ValidationError): self.generate(transport=transport)
        with self.assertRaises(ValidationError): self.generate(lambda t:t.update(days=[]))
        self.assertEqual(self.cal.get_trip_command_context(self.tid), before)

    def test_place_location_and_candidate_changes_preserve_other_data(self):
        def mutate(t):
            t['places'][0]['mapDisplayName'] = '合成地点'
            t['places'][0]['location'] = dict(latitude=35.1, longitude=139.2)
        proposal = self.generate(mutate)
        self.cal.apply_trip_operation(self.approval(proposal))
        expected = copy.deepcopy(self.context['trip']); mutate(expected)
        self.assertEqual(self.cal.get_effective_trip(self.tid), expected)

    def test_candidate_add_remove_and_reference_preservation(self):
        def add(t):
            place = copy.deepcopy(t['places'][0]); place['id'] = 'ai-new-place'; place['name'] = '合成追加候補'
            t['places'].append(place)
            selection = t['days'][0]['scheduleItems'][0]['placeSelection']
            selection['candidatePlaceIds'].append(place['id'])
        proposal = self.generate(add)
        self.cal.apply_trip_operation(self.approval(proposal))
        expected = copy.deepcopy(self.context['trip']); add(expected)
        self.assertEqual(self.cal.get_effective_trip(self.tid), expected)
        self.context = self.cal.get_trip_command_context(self.tid)
        def remove(t):
            t['places'] = [p for p in t['places'] if p['id'] != 'ai-new-place']
            t['days'][0]['scheduleItems'][0]['placeSelection']['candidatePlaceIds'].remove('ai-new-place')
        proposal = self.generate(remove)
        self.cal.apply_trip_operation(self.approval(proposal))
        remove(expected)
        self.assertEqual(self.cal.get_effective_trip(self.tid), expected)

    def test_generation_finishes_after_concurrent_edit(self):
        def transport(e):
            candidate = copy.deepcopy(e['working_export_package']['effective_trip'])
            candidate['title'] = '生成変更'
            self.cal.apply_trip_operation(dict(request_id='concurrent', trip_id=self.tid, operation='instruction', expected_revision=self.context['revision'], values={'instruction':'別変更'}))
            return dict(generation_id=e['generation_id'], trip_id=self.tid, status='succeeded', candidate=candidate)
        with self.assertRaises(ConflictError): self.generate(transport=transport)

    def test_response_loss_lookup_recovers_existing_journal(self):
        proposal = self.generate()
        with patch.object(self.cal, '_after_candidate_replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError): self.cal.apply_trip_operation(self.approval(proposal))
        result = self.cal.lookup_chat_request(proposal['request_id'])
        self.assertEqual(result['status'], 'committed')
        self.assertEqual(self.cal.apply_trip_operation(self.approval(proposal))['receipt'], result['receipt'])

if __name__ == '__main__': unittest.main()
