import base64
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import test_trip_chat as fixture
from scripts.publish_trip_index import build_index, publish
from Sources.calendar_domain.trip_index import queue_publication


class TripIndexTest(unittest.TestCase):
    def setUp(self):
        fixture.TripChatTest.setUp(self)
        worker = patch('Sources.calendar_domain.trip_index.subprocess.Popen')
        worker.start()
        self.addCleanup(worker.stop)

    attempts = fixture.TripChatTest.attempts
    create = fixture.TripChatTest.create
    update = fixture.TripChatTest.update
    def settings(self):
        folder = self.root / 'settings'
        folder.mkdir(exist_ok=True)
        (folder / 'trip-index-publisher.json').write_text(json.dumps(
            dict(database=str(self.db), gh='/synthetic/gh')))
        return folder

    def test_allowlist_and_changes(self):
        self.cal.apply_trip_request(self.create())
        before = build_index(self.cal)
        self.assertEqual(set(before), {'schema', 'travels'})
        item = before['travels'][0]
        self.assertEqual(set(item), {'id', 'title', 'dateRange', 'has_itinerary'})
        self.assertEqual(item['id'], self.tid)
        self.assertTrue(item['has_itinerary'])
        # Explicitly exclude pending instruction bodies and private Trip data.
        self.cal.add_chat_instruction('pending', self.tid, 'DO NOT PUBLISH')
        self.assertEqual(build_index(self.cal), before)
        self.cal.apply_trip_request(self.update())
        self.assertEqual(build_index(self.cal)['travels'][0]['title'], '合成変更')
        travel = self.cal.change_travel(dict(title='合成未定旅行', date_status='undecided',
                                             start_date=None, end_date=None))['receipt']['item']
        entry = next(t for t in build_index(self.cal)['travels'] if t['id'] == travel['id'])
        self.assertEqual(entry['dateRange'], dict(start=None, end=None))
        self.assertFalse(entry['has_itinerary'])
        self.cal.change_travel(dict(title='合成日程変更', date_status='confirmed',
                                    start_date='2099-03-01', end_date='2099-03-02'),
                               item_id=travel['id'], expected_revision=travel['revision'])
        entry = next(t for t in build_index(self.cal)['travels'] if t['id'] == travel['id'])
        self.assertEqual(entry['dateRange']['start'], '2099-03-01')

    def test_publication_cache_and_remote_no_change(self):
        self.cal.apply_trip_request(self.create())
        folder = self.settings()
        replies = [None, dict(content=dict(sha='new'))]
        with patch('scripts.publish_trip_index.github', side_effect=replies) as api:
            self.assertEqual(publish(self.db, self.root)['status'], 'published')
            body = api.call_args_list[1].args[3]
            self.assertEqual(json.loads(base64.b64decode(body['content'])), build_index(self.cal))
            self.assertEqual(body['branch'], 'chat-index')
            self.assertEqual(publish(self.db, self.root)['status'], 'unchanged')
            self.assertEqual(api.call_count, 2)
        (folder / 'trip-index-publication-state.json').unlink()
        remote = dict(sha='same', content=base64.b64encode(
            json.dumps(build_index(self.cal)).encode()).decode())
        with patch('scripts.publish_trip_index.github', return_value=remote) as api:
            self.assertEqual(publish(self.db, self.root)['status'], 'unchanged')
            api.assert_called_once()
        # A travel rename must replace the exact prior GitHub blob.
        self.cal.apply_trip_request(self.update())
        with patch('scripts.publish_trip_index.github', side_effect=[remote, {}]) as api:
            self.assertEqual(publish(self.db, self.root)['status'], 'published')
            self.assertEqual(api.call_args_list[1].args[3]['sha'], 'same')

    def test_failed_publication_does_not_change_cal(self):
        self.cal.apply_trip_request(self.create())
        self.settings()
        before = self.cal.get_trip_command_context(self.tid)
        with patch('scripts.publish_trip_index.github', side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):
                publish(self.db, self.root)
        self.assertEqual(self.cal.get_trip_command_context(self.tid), before)
        state = json.loads((self.root/'settings/trip-index-publication-state.json').read_text())
        self.assertEqual(state['status'], 'failed')

    def test_commit_queue_opt_in_and_failure(self):
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen') as spawn:
            self.cal.apply_trip_request(self.create())
            spawn.assert_not_called()
            self.settings()
            # Frame and Chat writers share this transaction hook.
            self.cal.change_travel(dict(title='新規合成旅行', date_status='undecided',
                                        start_date=None, end_date=None))
            self.assertGreater(spawn.call_count, 0)
            self.assertTrue(spawn.call_args.kwargs['start_new_session'])
            self.assertEqual(spawn.call_args.args[0][0], sys.executable)
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen', side_effect=OSError):
            result = self.cal.apply_trip_request(self.update())
        self.assertEqual(result['status'], 'committed')
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen') as spawn:
            queue_publication(self.root/'other.sqlite3', self.root)
            spawn.assert_not_called()
