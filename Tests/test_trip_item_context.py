import copy
import json
import subprocess
import sys
import unittest

import test_trip_chat
from scripts.cal_schedule import trip_item_context


class TripItemContextTest(unittest.TestCase):
    attempts = test_trip_chat.TripChatTest.attempts
    create = test_trip_chat.TripChatTest.create

    def setUp(self):
        test_trip_chat.TripChatTest.setUp(self)
        self.cal.apply_trip_request(self.create())

    def cli(self, *args, request=None):
        return subprocess.run(
            [sys.executable, '-B', 'scripts/cal_schedule.py',
             '--database', str(self.db), '--local-root', str(self.root), *args],
            input=json.dumps(request, ensure_ascii=False) if request is not None else None,
            capture_output=True, text=True, cwd=test_trip_chat.ROOT,
        )

    def read(self, item_id=None):
        args = ['trip-get', '--id', self.tid]
        if item_id is not None:
            args += ['--item-id', item_id]
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        return json.loads(result.stdout)

    def test_cli_full_output_unchanged_and_item_keeps_latest_snapshot(self):
        self.cal.set_direct_override('title-edit', self.tid, 'stay-1', '/action', '合成の画面変更')
        self.cal.add_chat_instruction('global', self.tid, '未処理の全体指示')
        self.cal.add_chat_instruction('second', self.tid, 'もう一つの未処理指示')
        context = self.cal.get_trip_command_context(self.tid)
        self.assertEqual(self.read(), dict(status='ok', **context))
        focused = self.read('stay-1')
        self.assertEqual(focused['item']['action'], '合成の画面変更')
        self.assertEqual(focused['source_type'], 'scheduleItem')
        self.assertEqual(focused['day']['id'], 'day-1')
        self.assertEqual(focused['trip_summary']['id'], self.tid)
        self.assertEqual(focused['revision'], context['revision'])
        self.assertEqual(focused['instructions'], context['instructions'])
        self.assertEqual({p['id'] for p in focused['places']}, {'hotel'})
        self.assertEqual({b['id'] for b in focused['bookings']}, {'stay-booking'})
        self.assertNotIn('trip', focused)
        self.assertNotIn('scheduleItems', focused['day'])
        self.assertNotIn('transportIds', focused['day'])
        self.assertEqual(context, self.cal.get_trip_command_context(self.tid))

    def test_transport_includes_endpoints_and_related_reservation(self):
        full = self.cal.get_trip_command_context(self.tid)
        item = next(t for t in full['trip']['transports'] if t['id'] == 'departure')
        focused = self.read('departure')
        self.assertEqual(focused['source_type'], 'transport')
        self.assertEqual(focused['item'], item)
        self.assertEqual(focused['day']['id'], item['dayId'])
        self.assertEqual({p['id'] for p in focused['places']},
                         {item['fromPlaceId'], item['toPlaceId']})
        self.assertEqual({b['id'] for b in focused['bookings']}, {'seat-return'})
        self.assertEqual(focused['revision'], full['revision'])

    def test_missing_or_ambiguous_id_rejects_without_falling_back(self):
        before = self.cal.get_trip_command_context(self.tid)
        for item_id in ('missing-id', ''):
            result = self.cli('trip-get', '--id', self.tid, '--item-id', item_id)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['status'], 'rejected')
            self.assertNotIn('trip', json.loads(result.stdout))
        ambiguous = copy.deepcopy(before)
        duplicate = copy.deepcopy(ambiguous['trip']['days'][0]['scheduleItems'][0])
        ambiguous['trip']['days'][1]['scheduleItems'].append(duplicate)
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            trip_item_context(ambiguous, duplicate['id'])
        self.assertEqual(before, self.cal.get_trip_command_context(self.tid))

    def test_focused_revision_drives_existing_save_lookup_and_stale_rejection(self):
        before = self.read()
        focused = self.read('stay-1')
        request = dict(
            request_id='focused-title-save', trip_id=self.tid, operation='item',
            expected_revision=focused['revision'],
            values=dict(source_type=focused['source_type'],
                        source_item_id=focused['source_item_id'],
                        changes={'title': '合成の局所変更'}),
        )
        result = self.cli('trip-operation', request=request)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        receipt = json.loads(result.stdout)['receipt']
        lookup = self.cli('lookup', '--request-id', request['request_id'])
        self.assertEqual(lookup.returncode, 0)
        self.assertEqual(json.loads(lookup.stdout)['receipt'], receipt)
        current = self.read('stay-1')
        self.assertEqual(current['item']['action'], '合成の局所変更')
        self.assertEqual(current['revision'], receipt['revision'])
        expected = copy.deepcopy(before['trip'])
        expected['days'][0]['scheduleItems'][1]['action'] = '合成の局所変更'
        self.assertEqual(self.read()['trip'], expected)
        stale = dict(request, request_id='focused-stale-save')
        result = self.cli('trip-operation', request=stale)
        self.assertEqual(result.returncode, 3)
        self.assertEqual(json.loads(result.stdout)['reason'], 'revision_conflict')
        self.assertEqual(self.read('stay-1'), current)

    def test_unrelated_trip_growth_does_not_expand_item_response(self):
        context = self.cal.get_trip_command_context(self.tid)
        original = copy.deepcopy(context)
        expected = trip_item_context(context, 'stay-1')
        expanded = copy.deepcopy(context)
        for n in range(200):
            item = copy.deepcopy(expanded['trip']['days'][1]['scheduleItems'][0])
            item.update(id='unrelated-item-' + str(n), action='無関係の予定' * 60)
            expanded['trip']['days'][1]['scheduleItems'].append(item)
            expanded['trip']['places'].append(dict(
                id='unrelated-place-' + str(n), name='無関係の地点' * 60))
        actual = trip_item_context(expanded, 'stay-1')
        self.assertEqual(actual, expected)
        self.assertEqual(context, original)
        size = lambda value: len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
        self.assertLess(size(actual), size(expanded) / 10)
        print('Synthetic context bytes: full=%d item=%d' % (size(expanded), size(actual)))


if __name__ == '__main__':
    unittest.main()
