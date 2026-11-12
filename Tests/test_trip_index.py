import copy
import json
import sys
import unittest
from unittest.mock import patch
import test_trip_chat as fixture
from scripts.publish_trip_index import build_files, publish_files, publish, blob_sha
from Sources.calendar_domain.trip_index import queue_publication


class TravelIndexTest(unittest.TestCase):
    attempts = fixture.TripChatTest.attempts
    create = fixture.TripChatTest.create
    update = fixture.TripChatTest.update

    def setUp(self):
        fixture.TripChatTest.setUp(self)
        self.launcher = patch('Sources.calendar_domain.trip_index.queue_publication')
        self.launcher.start()
        self.addCleanup(self.launcher.stop)
        self.cal.apply_trip_request(self.create())

    def settings(self):
        folder = self.root / 'settings'
        folder.mkdir(exist_ok=True)
        (folder / 'trip-index-publisher.json').write_text(json.dumps(
            dict(database=str(self.db), gh='/synthetic/gh')))
        return folder

    def test_index_only_and_metadata_changes(self):
        files = build_files(self.cal)
        self.assertEqual(set(files), {'trip-index.json'})
        index = files['trip-index.json']
        self.assertEqual(set(index), {'schema', 'travels'})
        self.assertEqual(index['schema'], 'cal-trip-index-v1')
        self.assertEqual(set(index['travels'][0]), {'id', 'title', 'dateRange', 'has_itinerary'})
        self.cal.add_chat_instruction('pending', self.tid, '合成未処理指示')
        self.cal.set_direct_override('item-change', self.tid, 'stay-1', '/action', '合成項目変更')
        self.assertEqual(build_files(self.cal), files)
        self.cal.apply_trip_request(self.update())
        self.assertEqual(build_files(self.cal)['trip-index.json']['travels'][0]['title'], '合成変更')
        travel = self.cal.change_travel(dict(title='合成未定旅行', date_status='undecided',
                                             start_date=None, end_date=None))['receipt']['item']
        index = build_files(self.cal)['trip-index.json']
        entry = next(t for t in index['travels'] if t['id']==travel['id'])
        self.assertFalse(entry['has_itinerary'])
        self.assertEqual(entry['dateRange'], dict(start=None, end=None))
        self.cal.change_travel(dict(start_date='2099-01-01', end_date='2099-01-02', date_status='confirmed'),
                               item_id=travel['id'], expected_revision=travel['revision'])
        entry = next(t for t in build_files(self.cal)['trip-index.json']['travels'] if t['id']==travel['id'])
        self.assertEqual(entry['dateRange']['start'], '2099-01-01')

    def test_atomic_cleanup_preserves_source(self):
        files = {'trip-index.json': '{}\n'}
        tree = dict(tree=[dict(path='AGENTS.md', type='blob', sha='source'),
                          dict(path='chat-data/trips/old/context.json', type='blob', sha='old'),
                          dict(path='chat-data/schedule.json', type='blob', sha='old-schedule'),
                          dict(path='item-index/by-date/2099-01-01.json', type='blob', sha='old-date'),
                          dict(path='item-index/by-trip/old.json', type='blob', sha='old-trip'),
                          dict(path='trip-index.json', type='blob', sha='old-index')])
        replies = [dict(object=dict(sha='parent')), dict(tree=dict(sha='base-tree')),
                   tree, dict(sha='new-tree'), dict(sha='new-commit'), {}]
        with patch('scripts.publish_trip_index.github', side_effect=replies) as api:
            result = publish_files('/synthetic/gh', files)
        self.assertEqual(result['commit_sha'], 'new-commit')
        edits = api.call_args_list[3].args[3]['tree']
        self.assertEqual({e['path'] for e in edits},
                         {'trip-index.json','chat-data/trips/old/context.json','chat-data/schedule.json',
                          'item-index/by-date/2099-01-01.json','item-index/by-trip/old.json'})
        self.assertTrue(all(e['sha'] is None for e in edits if e['path'].startswith(('chat-data/', 'item-index/'))))
        self.assertEqual(api.call_args_list[-1].args[3], dict(sha='new-commit', force=False))

    def test_cache_and_failure_preserve_mac(self):
        self.settings()
        with patch('scripts.publish_trip_index.publish_files',
                   return_value=dict(status='published', commit_sha='synthetic')) as api:
            self.assertEqual(publish(self.db, self.root)['status'], 'published')
            self.assertEqual(publish(self.db, self.root)['status'], 'unchanged')
            self.cal.add_chat_instruction('new', self.tid, '合成指示')
            self.assertEqual(publish(self.db, self.root)['status'], 'unchanged')
            api.assert_called_once()
        self.cal.apply_trip_request(self.update())
        before = self.cal.get_trip_command_context(self.tid)
        with patch('scripts.publish_trip_index.publish_files', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                publish(self.db, self.root)
        self.assertEqual(self.cal.get_trip_command_context(self.tid), before)

    def test_hook_ignores_ordinary_and_instruction_only_updates(self):
        self.launcher.stop()
        self.settings()
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen') as spawn:
            self.cal.add_chat_instruction('new', self.tid, '指示')
            self.cal.change_schedule('event', 'save', values=dict(title='合成', start_date='2099-01-01'))
            spawn.assert_not_called()
            self.cal.change_travel(dict(title='合成旅行', date_status='undecided', start_date=None, end_date=None))
            spawn.assert_called_once()
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen', side_effect=OSError):
            self.assertEqual(self.cal.apply_trip_request(self.update())['status'], 'committed')
