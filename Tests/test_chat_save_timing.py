from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts.record_chat_timing import LOG_NAME, project, record

ROOT = Path(__file__).resolve().parents[1]


def sample():
    return dict(clock='caller_epoch_ms', started_at_ms=1000, saved_at_ms=12500,
                route='rdc', operation='trip_item', request_id='synthetic-request',
                receipt_id='synthetic-receipt', calls=[
                    dict(phase='git', started_at_ms=1000, received_at_ms=4000),
                    dict(phase='read', started_at_ms=7000, received_at_ms=8000),
                    dict(phase='save', started_at_ms=12000, received_at_ms=12500)])


class ChatSaveTimingTest(unittest.TestCase):
    def test_total_breakdown_and_missing_detail(self):
        value = project(sample())
        self.assertEqual(value['elapsed_ms'], 11500)
        self.assertEqual(value['call_wall_ms'], 4500)
        self.assertEqual(value['unclassified_ms'], 7000)
        self.assertEqual(value['elapsed_ms'], value['call_wall_ms'] + value['unclassified_ms'])
        self.assertEqual([c['duration_ms'] for c in value['calls']], [3000, 1000, 500])
        self.assertEqual(value['saved_at'], '1970-01-01T00:00:12.500000+00:00')
        without = sample()
        del without['calls']
        self.assertEqual(project(without)['unclassified_ms'], 11500)

    def test_invalid_time_provenance_order_and_fields(self):
        invalid = []
        for field, value in [('clock', 'mac_epoch_ms'), ('saved_at_ms', 999),
                             ('saved_at_ms', float('nan')), ('started_at_ms', True),
                             ('title', 'not-a-log-field')]:
            row = sample()
            row[field] = value
            invalid.append(row)
        row = sample()
        row['calls'][1]['started_at_ms'] = 3000
        invalid.append(row)
        row = sample()
        row['calls'][-1]['received_at_ms'] = 13000
        invalid.append(row)
        for row in invalid:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    project(row)

    def test_concurrent_append_keeps_records_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def append(i):
                row = sample()
                row['request_id'] = 'synthetic-' + str(i)
                record(row, root)
            with ThreadPoolExecutor(max_workers=4) as pool:
                list(pool.map(append, range(12)))
            rows = [json.loads(line) for line in (root/'logs'/LOG_NAME).read_text().splitlines()]
            self.assertEqual(len(rows), 12)
            self.assertEqual({r['request_id'] for r in rows}, {'synthetic-'+str(i) for i in range(12)})
            expected = set(project(sample())) | {'recorded_at'}
            self.assertTrue(all(set(row) == expected for row in rows))

    def test_cli_failure_does_not_touch_calendar_or_echo_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            marker = root/'calendar.sqlite3'
            marker.write_bytes(b'unchanged CAL storage')
            (root/'logs').write_text('synthetic blocked directory')
            p = subprocess.run([sys.executable, '-B', 'scripts/record_chat_timing.py',
                                '--local-root', str(root)], cwd=ROOT,
                               input=json.dumps(sample()), text=True, capture_output=True)
            self.assertEqual(p.returncode, 1)
            self.assertEqual(json.loads(p.stdout), dict(status='failed', reason='chat_timing_record_failed'))
            self.assertEqual(marker.read_bytes(), b'unchanged CAL storage')
            self.assertEqual(p.stderr, '')
            row = sample()
            row['title'] = 'must-not-be-printed'
            p = subprocess.run([sys.executable, '-B', 'scripts/record_chat_timing.py',
                                '--local-root', str(root)], cwd=ROOT,
                               input=json.dumps(row), text=True, capture_output=True)
            self.assertEqual(p.returncode, 1)
            self.assertNotIn('must-not-be-printed', p.stdout+p.stderr)
            with self.assertRaises(ValueError):
                record(sample(), ROOT)
