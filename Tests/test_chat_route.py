import json
from pathlib import Path
import tempfile
import unittest
from scripts.measure_chat_route import prepare, step, CASES


class ChatRouteTest(unittest.TestCase):
    def test_isolated_routes_and_diagnostic_contents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)/'fixture'
            prepare(root)
            for case in CASES:
                records = [step(root, case, action) for action in
                           ('acquire', 'draft', 'resolve', 'apply', 'lookup', 'reread', 'replay', 'stale')]
                self.assertEqual(records[2]['coordinates']['attempted'], 0)
                self.assertEqual(records[3]['cal']['resolution'], 'new')
                self.assertEqual(records[6]['cal']['resolution'], 'replayed')
                self.assertEqual(records[7]['cal']['exit_code'], 3)
                self.assertTrue(all(r['end_ns'] >= r['start_ns'] for r in records))
            text = (root/'route.jsonl').read_text()
            for key in ('Synthetic route title change', 'coordinate_results', 'receipt_id', 'effective_hash', 'request_id', '札幌'):
                self.assertNotIn(key, text)
            for record in map(json.loads, text.splitlines()):
                if 'cal' in record:
                    self.assertEqual(record['group'], record['cal']['group_id'])
            with self.assertRaises(FileExistsError):
                prepare(root)


if __name__ == '__main__':
    unittest.main()
