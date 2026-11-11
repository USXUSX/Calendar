"""Synthetic CLI contracts and diagnostic isolation; no live connections."""
import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from Sources.calendar_domain import CalendarDomain
from Sources.calendar_domain.timing import Timing
from scripts import cal_schedule
from scripts.init_calendar_db import initialize
from scripts.trip_location_resolver import resolve_location_plan

ROOT = Path(__file__).resolve().parents[1]


class ChatTimingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db = self.root/'db.sqlite3'
        initialize(self.db)
        self.cal = CalendarDomain(self.db, self.root, chat_root=self.root/'chat-unused')
        self.trip = json.loads((ROOT/'Samples/hokkaido-4days-candidate.json').read_text())
        self.trip['title'] = 'PRIVATE TITLE'
        self.block = patch('socket.socket.connect', side_effect=AssertionError('live network forbidden'))
        self.block.start()
        self.addCleanup(self.block.stop)

    def request(self):
        plan = self.cal.prepare_import_locations(self.trip)
        return dict(request_id='PRIVATE-REQUEST', kind='trip', action='create', trip=copy.deepcopy(self.trip),
                    coordinate_results={p['place_id']: None for p in plan if p['location'] is None and not p.get('skip_search')})

    def cli(self, action, value=None, timing=True, extra=()):
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ['--database', str(self.db), '--local-root', str(self.root)]
        if timing:
            args += ['--timing']
        with patch('sys.stdin', io.StringIO(json.dumps(value))), patch('sys.stdout', stdout), patch('sys.stderr', stderr):
            code = cal_schedule.main(args+list(extra)+action)
        lines = stdout.getvalue().splitlines()
        self.assertEqual(len(lines), 1)
        diagnostics = stderr.getvalue()
        record = json.loads(diagnostics) if diagnostics else None
        if record:
            self.assertEqual(record['exit_code'], code)
            for private in ('PRIVATE TITLE', 'PRIVATE-REQUEST', '北海道', 'coordinate_results', 'committed_at', 'receipt_id', 'credential'):
                self.assertNotIn(private, diagnostics)
            self.assertGreaterEqual(record['total_ms'], 0)
            self.assertTrue(all(s['ms'] >= 0 for s in record['spans']))
        return code, json.loads(lines[0]), record

    def test_off_create_save_replay_lookup_contracts(self):
        request = self.request()
        code, created, off = self.cli(['apply'], request, timing=False)
        self.assertEqual(code, 0)
        self.assertIsNone(off)
        code, replay, timing = self.cli(['apply'], request)
        self.assertEqual(created['receipt'], replay['receipt'])
        self.assertEqual(timing['resolution'], 'replayed')
        self.assertNotIn('formal_json_journal', [s['stage'] for s in timing['spans']])
        self.assertIn('post_commit_google_status', [s['stage'] for s in timing['spans']])
        _, lookup, lookup_timing = self.cli(['lookup', '--request-id', request['request_id']])
        self.assertEqual(created['receipt'], lookup['receipt'])
        self.assertNotEqual(timing['diagnostic_id'], lookup_timing['diagnostic_id'])
        _, context, get_timing = self.cli(['trip-get', '--id', self.trip['id']])
        self.assertTrue({'trip_recovery', 'trip_read', 'trip_effective'} <= {s['stage'] for s in get_timing['spans']})
        update = dict(request, request_id='save', action='save', expected_revision=context['revision'])
        update['trip']['title'] = 'PRIVATE TITLE changed'
        code, saved, record = self.cli(['apply'], update)
        self.assertEqual(code, 0)
        self.assertEqual(record['resolution'], 'new')
        self.assertEqual(record['counts']['places'], len(self.trip['places']))
        stages = {s['stage'] for s in record['spans']}
        self.assertTrue({'lock_wait', 'revision_check', 'trip_validation', 'formal_json_journal',
                         'db_commit', 'receipt_finalize', 'post_commit_notification',
                         'post_commit_google_sync', 'response_prepare'} <= stages)
        self.assertEqual(saved['receipt'], self.cli(['apply'], update, timing=False)[1]['receipt'])
        with sqlite3.connect(self.db) as c:
            stored = c.execute('SELECT payload_hash, receipt_json FROM schedule_receipts WHERE request_id=?', ('save',)).fetchone()
        from Sources.calendar_domain.schedule_chat import encoded
        self.assertEqual(stored[0], self.cal._digest(encoded(update).encode()))
        self.assertEqual(json.loads(stored[1]), saved['receipt'])
        self.assertNotIn('diagnostic_id', stored[1])

    def test_rejection_and_unknown_recovery(self):
        request = self.request()
        self.cli(['apply'], request)
        _, context, _ = self.cli(['trip-get', '--id', self.trip['id']])
        bad = dict(request, request_id='invalid', action='save', expected_revision=context['revision'])
        bad['trip']['dateRange'] = None
        code, result, record = self.cli(['apply'], bad)
        self.assertEqual((code, result['status'], record['failure_class']), (2, 'rejected', 'validation'))
        self.assertTrue(any(s['stage'] == 'trip_validation' and s['status'] == 'error' for s in record['spans']))
        stale = dict(self.request(), request_id='stale', action='save', expected_revision={})
        code, _, record = self.cli(['apply'], stale)
        self.assertEqual((code, record['failure_class']), (3, 'conflict'))
        update = dict(self.request(), request_id='unknown', action='save', expected_revision=context['revision'])
        with patch.object(CalendarDomain, '_after_candidate_replace', side_effect=OSError('PRIVATE TITLE')):
            code, result, record = self.cli(['apply'], update)
        self.assertEqual((code, result['status']), (5, 'unknown'))
        self.assertTrue(any(s['stage'] == 'formal_json_journal' and s['status'] == 'error' for s in record['spans']))
        self.assertEqual(self.cli(['lookup', '--request-id', 'unknown'])[1]['status'], 'committed')
        self.assertEqual(self.cli(['apply'], update)[1]['resolution'], 'replayed')
        code, _, record = self.cli(['lookup', '--request-id', 'absent'])
        self.assertEqual((code, record['status']), (4, 'not_found'))

    def test_mocked_resolve_intervals_and_failure(self):
        now = [0]
        def opener(url, **kwargs):
            now[0] += 7_000_000
            value = {'key': 'credential'} if isinstance(url, str) else {'places': []}
            return io.BytesIO(json.dumps(value).encode())
        record = Timing('trip-resolve')
        plan = [dict(place_id=str(i), location=None, query='PRIVATE TITLE') for i in range(2)]
        with record.activate(), patch('Sources.calendar_domain.timing.time.monotonic_ns', side_effect=lambda: now[0]):
            result = resolve_location_plan(plan, opener=opener)
        spans = record.record['spans']
        self.assertEqual([s['ms'] for s in spans if s['stage'] == 'map_connection'], [7])
        # Duplicate queries still use the existing one-search cache.
        self.assertEqual([s['ms'] for s in spans if s['stage'] == 'places_search'], [7])
        self.assertEqual(result['coordinates']['attempted'], 2)
        self.assertNotIn('PRIVATE TITLE', json.dumps(record.record))
        with patch('scripts.cal_schedule.resolve_location_plan', side_effect=ValueError('map_connection_unavailable')):
            code, _, record = self.cli(['trip-resolve'], {'trip': self.trip})
        self.assertEqual(code, 2)
        self.assertIn('location_plan', [s['stage'] for s in record['spans']])

    def test_diagnostic_sinks_and_clock_cannot_change_save(self):
        group = '00000000-0000-0000-0000-000000000279'
        target = self.root/'timing.jsonl'
        code, _, record = self.cli(['apply'], self.request(), extra=['--timing-file', str(target), '--timing-group', group])
        self.assertEqual(code, 0)
        self.assertEqual(record, json.loads(target.read_text()))
        self.assertEqual(record['group_id'], group)
        # Missing parent is an output failure, never a failed save.
        code, replay, _ = self.cli(['apply'], self.request(), extra=['--timing-file', str(self.root/'missing'/'timing.jsonl')])
        self.assertEqual((code, replay['resolution']), (0, 'replayed'))
        with patch('Sources.calendar_domain.timing.time.monotonic_ns', side_effect=RuntimeError('clock failed')):
            stdout, stderr = io.StringIO(), io.StringIO()
            with patch('sys.stdout', stdout), patch('sys.stderr', stderr):
                code = cal_schedule.main(['--database', str(self.db), '--local-root', str(self.root), '--timing', 'doctor'])
            self.assertEqual(code, 0)
            self.assertIsNone(json.loads(stderr.getvalue())['total_ms'])
        with patch('sys.stdin', io.StringIO('{')), patch('sys.stdout', io.StringIO()), patch('sys.stderr', io.StringIO()) as error:
            code = cal_schedule.main(['--database', str(self.db), '--local-root', str(self.root), '--timing', 'apply'])
            self.assertEqual(code, 2)
            self.assertTrue(any(s['stage'] == 'input' and s['status'] == 'error' for s in json.loads(error.getvalue())['spans']))
        blocked = ROOT/'timing-must-not-be-created.jsonl'
        code, _, _ = self.cli(['apply'], self.request(), extra=['--timing-file', str(blocked)])
        self.assertEqual(code, 0)
        self.assertFalse(blocked.exists())
        class Broken:
            def write(self, value):
                raise OSError('sink failed')
        Timing('doctor').emit(Broken())

    def test_post_commit_mock_waits_and_lock_wait(self):
        import threading
        import time
        request = self.request()
        # Hold an actual synthetic SQLite write lock, then release it in another thread.
        ready = threading.Event()
        def lock():
            with sqlite3.connect(self.db) as c:
                c.execute('BEGIN IMMEDIATE')
                ready.set()
                time.sleep(0.06)
        thread = threading.Thread(target=lock)
        thread.start(); ready.wait()
        def notify(*args):
            time.sleep(0.01)
        def sync(*args):
            time.sleep(0.02)
            return dict(status='unreflected')
        with patch('Sources.calendar_domain.change_notification.notify_committed', side_effect=notify), patch.object(CalendarDomain, 'sync_google', sync):
            code, _, record = self.cli(['apply'], request)
        thread.join()
        self.assertEqual(code, 0)
        stages = record['spans']
        self.assertGreater(sum(s['ms'] for s in stages if s['stage'] == 'lock_wait'), 10)
        self.assertGreater(sum(s['ms'] for s in stages if s['stage'] == 'post_commit_notification'), 8)
        self.assertGreater(sum(s['ms'] for s in stages if s['stage'] == 'post_commit_google_sync'), 18)


if __name__ == '__main__':
    unittest.main()
