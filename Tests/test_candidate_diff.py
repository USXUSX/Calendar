import copy
import json
import unittest
from pathlib import Path

from Sources.calendar_domain.candidate_diff import candidate_review_rules


class CandidateDiffTests(unittest.TestCase):
    def setUp(self):
        self.base = json.loads((Path(__file__).resolve().parents[1] / 'Samples/synthetic-trip.json').read_text())
        self.working = {'item_changes': [], 'temporary_items': [], 'day_instructions': []}

    def rules(self, candidate):
        return candidate_review_rules(self.base, self.working, candidate)

    def test_each_field_mapping_types_null_and_missing(self):
        for source, item, mappings in [
            ('scheduleItem', self.base['days'][0]['scheduleItems'][0], {
                'status': ('status',), 'title': ('action',), 'normal_comment': ('summary',),
                'start': ('time', 'start'), 'end': ('time', 'end'), 'time_mode': ('time', 'mode'),
            }),
            ('transport', self.base['transports'][0], {
                'status': ('status',), 'start': ('time', 'start'),
                'end': ('time', 'end'), 'time_mode': ('time', 'mode'),
            }),
        ]:
            for field, path in mappings.items():
                for expected, actual, match in [(None, None, True), (None, '', False),
                                                 ('1', 1, False), (True, 1, False), ('fixed', 'fixed', True)]:
                    with self.subTest(source=source, field=field, expected=expected, actual=actual):
                        self.working['item_changes'] = [dict(source_type=source, source_item_id=item['id'],
                                                           disposition='changed', changes={field: expected})]
                        c = copy.deepcopy(self.base)
                        obj = c['days'][0]['scheduleItems'][0] if source == 'scheduleItem' else c['transports'][0]
                        for key in path[:-1]: obj = obj[key]
                        obj[path[-1]] = actual
                        self.assertEqual('EXPLICIT_INTENT_MISMATCH' in self.rules(c), not match)
                        del obj[path[-1]]
                        self.assertIn('EXPLICIT_INTENT_MISMATCH', self.rules(c))

    def test_removal_and_pending_delete_are_source_qualified(self):
        for source in ['scheduleItem', 'transport']:
            c = copy.deepcopy(self.base)
            items = c['days'][0]['scheduleItems'] if source == 'scheduleItem' else c['transports']
            removed = items.pop(0)
            self.working['item_changes'] = []
            self.assertEqual(self.rules(c), ('UNREQUESTED_ITEM_REMOVAL',))
            self.working['item_changes'] = [dict(source_type=source, source_item_id=removed['id'],
                                               disposition='pending_delete', changes={})]
            self.assertEqual(self.rules(c), ())
            self.assertEqual(self.rules(self.base), ('EXPLICIT_INTENT_MISMATCH',))
            self.working['item_changes'][0].update(disposition='changed', changes={'status':'tentative'})
            self.assertEqual(self.rules(c), ('EXPLICIT_INTENT_MISMATCH', 'UNREQUESTED_ITEM_REMOVAL'))

    def test_summary_and_all_rules_without_mutation(self):
        c = copy.deepcopy(self.base)
        c['summary'] = None
        removed = c['days'][0]['scheduleItems'].pop(0)
        self.working['item_changes'] = [dict(source_type='scheduleItem', source_item_id=removed['id'],
                                           disposition='changed', changes={'status':'tentative'})]
        before = copy.deepcopy((self.base, self.working, c))
        self.assertEqual(self.rules(c), ('EXPLICIT_INTENT_MISMATCH', 'TRIP_SUMMARY_CHANGED',
                                        'UNREQUESTED_ITEM_REMOVAL'))
        self.assertEqual((self.base, self.working, c), before)

    def test_insert_move_reorder_and_key_order_do_not_imply_removal(self):
        c = copy.deepcopy(self.base)
        new = copy.deepcopy(c['days'][0]['scheduleItems'][0]); new['id'] = 'schedule-fresh'
        c['days'][0]['scheduleItems'].insert(0, new)
        moved = c['days'][0]['scheduleItems'].pop(1); moved['dayId'] = c['days'][1]['id']
        c['days'][1]['scheduleItems'].append(moved)
        c['days'][1]['scheduleItems'].reverse()
        self.assertEqual(self.rules(json.loads(json.dumps(c, sort_keys=True))), ())
        c['days'][1]['scheduleItems'][-1]['id'] = 'replacement-id'
        self.assertEqual(self.rules(c), ('UNREQUESTED_ITEM_REMOVAL',))

    def test_unsupported_intent_is_failure_even_after_other_signals(self):
        c = copy.deepcopy(self.base); c['summary'] = None
        self.working['item_changes'] = [dict(source_type='scheduleItem',
            source_item_id=self.base['days'][0]['scheduleItems'][0]['id'],
            disposition='changed', changes={'unsupported':'private value'})]
        with self.assertRaises(ValueError): self.rules(c)

    def test_out_of_scope_changes_are_not_full_intent_validation(self):
        c = copy.deepcopy(self.base); c['places'][0]['name'] = 'synthetic new name'
        self.working['day_instructions'] = [{'day_id': c['days'][0]['id'], 'instruction': 'add an item'}]
        self.assertEqual(self.rules(c), ())
