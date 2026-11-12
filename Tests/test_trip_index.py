import copy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_trip_chat as fixture
from scripts.publish_trip_index import build_files, publish_files, publish, canonical, blob_sha
from Sources.calendar_domain.trip_index import queue_publication


class ChatCopyTest(unittest.TestCase):
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

    def cli(self, action, request):
        p = subprocess.run(
            [sys.executable, '-B', 'scripts/cal_schedule.py', '--database', str(self.db),
             '--local-root', str(self.root), action],
            input=canonical(request), capture_output=True, text=True, cwd=fixture.ROOT)
        return p.returncode, json.loads(p.stdout)

    def item_request(self, files, identity='copy-save'):
        index = files['trip-index.json']['travels'][0]
        overview = files[index['items_path']]
        target = next(i for i in overview['items'] if i['source_item_id'] == 'stay-1')
        return dict(request_id=identity, trip_id=self.tid, operation='item',
                    expected_revision=overview['revision'],
                    values=dict(source_type=target['source_type'], source_item_id=target['source_item_id'],
                                changes=dict(title='合成の名称変更')))

    def test_copy_consistency_and_instructions(self):
        before = self.cal.get_trip_command_context(self.tid)
        files = build_files(self.cal)
        index = files['trip-index.json']
        trip = index['travels'][0]
        self.assertEqual(index['schema'], 'cal-chat-copy-v2')
        self.assertEqual(files[trip['context_path']], dict(status='ok', **before))
        self.assertEqual(files[trip['items_path']]['revision'], before['revision'])
        self.assertEqual(self.cal.get_trip_command_context(self.tid), before)
        self.cal.add_chat_instruction('pending', self.tid, '合成未処理指示')
        changed = build_files(self.cal)
        self.assertNotEqual(changed[trip['items_path']]['revision'], before['revision'])
        self.assertEqual(changed[trip['items_path']]['instructions'][0]['instruction'], '合成未処理指示')
        self.assertFalse(any('settings' in p or p.endswith('.sqlite3') for p in files))

    def test_schedule_and_travel_without_itinerary(self):
        event = self.cal.change_schedule('event', 'save', values=dict(title='合成予定', start_date='2099-03-01'))
        todo = self.cal.change_schedule('todo', 'save', values=dict(label='合成Todo', due_date='2099-03-02'))
        travel = self.cal.change_travel(dict(title='合成未定旅行', date_status='undecided',
                                             start_date=None, end_date=None))['receipt']['item']
        self.cal.apply_recurrence_request(dict(
            request_id='recurring', kind='event', action='save', scope='series',
            recurrence=dict(frequency='daily', start='2099-01-01'),
            values=dict(title='合成定期', start_date='2099-01-01')))
        files = build_files(self.cal)
        schedule = files[files['trip-index.json']['schedule_path']]
        self.assertEqual(len(schedule['items']), 2)
        for value in schedule['items']:
            self.assertEqual(value, self.cal.get_schedule_item(value['kind'], value['item']['id']))
        self.assertEqual(len(schedule['series']), 1)
        self.assertEqual(schedule['series'][0], self.cal.get_series(schedule['series'][0]['series_id']))
        entry = next(t for t in files['trip-index.json']['travels'] if t['id'] == travel['id'])
        self.assertFalse(entry['has_itinerary'])
        self.assertNotIn('context_path', entry)
        self.assertEqual(files[entry['travel_path']]['travel']['revision'], travel['revision'])

    def test_one_save_from_serialized_copy_and_replay(self):
        files = json.loads(canonical(build_files(self.cal)))
        request = self.item_request(files)
        before = self.cal.get_trip_command_context(self.tid)
        code, saved = self.cli('trip-operation', request)
        self.assertEqual(code, 0)
        self.assertEqual(saved['status'], 'committed')
        after = self.cal.get_trip_command_context(self.tid)
        expected = copy.deepcopy(before['trip'])
        next(i for d in expected['days'] for i in d['scheduleItems'] if i['id']=='stay-1')['action']='合成の名称変更'
        self.assertEqual(after['trip'], expected)
        code, replay = self.cli('trip-operation', request)
        self.assertEqual(code, 0)
        self.assertEqual(replay['resolution'], 'replayed')
        self.assertEqual(replay['receipt'], saved['receipt'])

    def test_stale_copy_returns_latest_item_and_never_writes(self):
        request = self.item_request(build_files(self.cal))
        self.cal.set_direct_override('browser-edit', self.tid, 'stay-1', '/action', '先行した画面変更')
        self.cal.add_chat_instruction('instruction', self.tid, '新しい指示')
        before = self.cal.get_trip_command_context(self.tid)
        code, result = self.cli('trip-operation', request)
        self.assertEqual(code, 3)
        self.assertEqual(result['reason'], 'revision_conflict')
        self.assertEqual(result['current']['context_scope'], 'item')
        self.assertEqual(result['current']['item']['action'], '先行した画面変更')
        self.assertEqual(result['current']['revision'], before['revision'])
        self.assertEqual(result['current']['instructions'], before['instructions'])
        self.assertEqual(self.cal.get_trip_command_context(self.tid), before)
        self.assertEqual(self.cal.lookup_chat_request(request['request_id'])['status'], 'not_found')
        request.update(request_id='reconsidered', expected_revision=result['current']['revision'])
        self.assertEqual(self.cli('trip-operation', request)[0], 0)

    def test_ordinary_stale_copy_returns_context(self):
        saved = self.cal.change_schedule('event', 'save', values=dict(title='合成予定', start_date='2099-03-01'))
        files = build_files(self.cal)
        context = files[files['trip-index.json']['schedule_path']]['items'][0]
        request = dict(request_id='event-copy', kind='event', action='save', id=context['item']['id'],
                       expected_revision=context['revision'], values=dict(start_time='10:00'))
        self.cal.change_schedule('event', 'save', item_id=context['item']['id'],
                                 expected_revision=context['revision'], values=dict(title='画面で変更'))
        code, result = self.cli('apply', request)
        self.assertEqual(code, 3)
        self.assertEqual(result['current']['item']['title'], '画面で変更')
        request.update(request_id='event-reconsidered', expected_revision=result['current']['revision'])
        code, result = self.cli('apply', request)
        self.assertEqual(code, 0)
        self.assertEqual(result['receipt']['item']['title'], '画面で変更')
        self.assertEqual(result['receipt']['item']['start_time'], '10:00')

    def test_atomic_git_update_and_removal(self):
        files = {'trip-index.json': '{}\n', 'chat-data/new.json': '{"value":1}\n'}
        tree = dict(tree=[dict(path='AGENTS.md', type='blob', sha='source'),
                          dict(path='chat-data/old.json', type='blob', sha='old'),
                          dict(path='trip-index.json', type='blob', sha=blob_sha('{}\n'))])
        replies = [dict(object=dict(sha='parent')), dict(tree=dict(sha='base-tree')),
                   tree, dict(sha='new-tree'), dict(sha='new-commit'), {}]
        with patch('scripts.publish_trip_index.github', side_effect=replies) as api:
            result = publish_files('/synthetic/gh', files)
        self.assertEqual(result['commit_sha'], 'new-commit')
        edits = api.call_args_list[3].args[3]['tree']
        self.assertEqual({e['path'] for e in edits}, {'chat-data/old.json', 'chat-data/new.json'})
        self.assertIsNone(next(e for e in edits if e['path'].endswith('old.json'))['sha'])
        self.assertEqual(api.call_args_list[4].args[3]['parents'], ['parent'])
        self.assertEqual(api.call_args_list[5].args[3], dict(sha='new-commit', force=False))

    def test_publication_cache_and_failure_keeps_mac(self):
        self.settings()
        with patch('scripts.publish_trip_index.publish_files',
                   return_value=dict(status='published', commit_sha='synthetic')) as api:
            self.assertEqual(publish(self.db, self.root)['status'], 'published')
            self.assertEqual(publish(self.db, self.root)['status'], 'unchanged')
            api.assert_called_once()
        self.cal.add_chat_instruction('new', self.tid, '合成変更')
        before = self.cal.get_trip_command_context(self.tid)
        with patch('scripts.publish_trip_index.publish_files', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                publish(self.db, self.root)
        self.assertEqual(self.cal.get_trip_command_context(self.tid), before)

    def test_commit_queue_covers_instructions_and_schedule(self):
        self.launcher.stop()
        self.settings()
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen') as spawn:
            self.cal.add_chat_instruction('new', self.tid, '指示')
            self.assertGreater(spawn.call_count, 0)
            spawn.reset_mock()
            self.cal.change_schedule('event', 'save', values=dict(title='合成', start_date='2099-01-01'))
            spawn.assert_called_once()
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen', side_effect=OSError):
            self.assertEqual(self.cal.apply_trip_request(self.update())['status'], 'committed')
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen') as spawn:
            queue_publication(self.root/'other.sqlite3', self.root)
            spawn.assert_not_called()

    def test_recurrence_stale_copy_returns_latest_occurrence(self):
        created = self.cal.apply_recurrence_request(dict(
            request_id='series-create', kind='event', action='save', scope='series',
            recurrence=dict(frequency='daily', start='2099-01-01'),
            values=dict(title='合成定期', start_date='2099-01-01')))
        files = build_files(self.cal)
        series = files[files['trip-index.json']['schedule_path']]['series'][0]
        identity = 'rec:' + series['series_id'] + ':2099-01-02'
        self.cal.apply_recurrence_request(dict(
            request_id='rec-browser', kind='event', action='save', scope='this',
            id=identity, expected_revision=series['revision'], values=dict(title='先行変更')))
        request = dict(request_id='rec-stale', kind='event', action='save', scope='this',
                       id=identity, expected_revision=series['revision'], values=dict(start_time='10:00'))
        code, result = self.cli('apply', request)
        self.assertEqual(code, 3)
        self.assertEqual(result['current']['item']['title'], '先行変更')
        request.update(request_id='rec-reconsidered', expected_revision=result['current']['revision'])
        self.assertEqual(self.cli('apply', request)[0], 0)

    def test_travel_stale_copy_returns_latest_basic(self):
        travel = self.cal.change_travel(dict(title='合成旅行', date_status='undecided',
                                             start_date=None, end_date=None))['receipt']['item']
        files = build_files(self.cal)
        index = next(t for t in files['trip-index.json']['travels'] if t['id']==travel['id'])
        basic = files[index['travel_path']]['travel']
        self.cal.change_travel(dict(title='先行変更'), item_id=basic['id'], expected_revision=basic['revision'])
        request = dict(request_id='travel-stale', kind='travel', action='save', id=basic['id'],
                       expected_revision=basic['revision'], values=dict(title='依頼した変更'))
        code, result = self.cli('apply', request)
        self.assertEqual(code, 3)
        self.assertEqual(result['current']['title'], '先行変更')
        request.update(request_id='travel-reconsidered', expected_revision=result['current']['revision'])
        self.assertEqual(self.cli('apply', request)[0], 0)
