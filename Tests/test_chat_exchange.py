import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize

ROOT = Path(__file__).resolve().parents[1]

class ChatExchangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'calendar.sqlite3'
        initialize(self.db)
        self.domain = CalendarDomain(self.db, self.root / 'data')
        self.trip = json.loads((ROOT / 'Samples/hokkaido-4days-candidate.json').read_text())
        self.id = self.trip['id']
        self.domain.import_trip_json(self.trip, confirmed=True)
        self.directory = self.root / 'data/chat' / self.id
        self.file = self.directory / 'candidate.json'

    def context(self):
        return json.loads((self.directory / 'context.json').read_text())

    def candidate(self):
        context = self.context()
        value = dict(trip_id=self.id, base_revision=context['effective_revision'],
                     handled_instruction_ids=[i['id'] for i in context['instructions']], trip=context['trip'])
        value['trip']['title'] = 'Chatで変更した旅程'
        self.file.write_text(json.dumps(value))
        return value

    def test_roundtrip_edit_instruction_hold_adopt(self):
        day = self.trip['days'][0]
        self.domain.edit_trip_day('edit', self.id, day['id'], {'route_summary': '札幌をゆっくり'})
        self.assertEqual(self.context()['trip']['days'][0]['routeSummary'], '札幌をゆっくり')
        self.domain.add_chat_instruction('chat-1', self.id, '午後はゆっくり')
        self.assertEqual(self.context()['instructions'][0]['id'], 'chat-1')
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM generation_requests').fetchone()[0], 0)
        value = self.candidate()
        value['trip']['days'][0]['routeSummary'] = 'Chatで調整した代表エリア'
        self.file.write_text(json.dumps(value))
        before = self.domain._trip_path(self.id).read_bytes()
        review = self.domain.review_chat_candidate(self.id)
        self.assertTrue(review['ready'])
        self.assertTrue(any('代表エリア' in c['field'] for c in review['changes']))
        self.assertEqual(self.domain._trip_path(self.id).read_bytes(), before)
        self.assertTrue(self.file.exists())  # Holding is read-only.
        with self.assertRaises(ValidationError):
            self.domain.adopt_chat_candidate(self.id, value)
        result = self.domain.adopt_chat_candidate(self.id, review['candidate'], confirmed=True)
        self.assertEqual(result['version'], 2)
        self.assertEqual(self.domain.get_effective_trip(self.id), value['trip'])
        self.assertEqual(self.context()['instructions'], [])
        self.assertEqual(self.domain.list_active_direct_overrides(self.id), [])
        self.assertFalse(self.file.exists())
        self.assertEqual(sorted(p.name for p in self.directory.iterdir()), ['context.json'])

    def test_stale_invalid_and_changed_snapshot_leave_formal_state(self):
        value = self.candidate()
        self.domain.edit_trip_day('edit', self.id, self.trip['days'][0]['id'], {'route_summary': '別の編集'})
        before = self.domain._trip_path(self.id).read_bytes()
        self.assertEqual(self.domain.review_chat_candidate(self.id)['status'], 'stale')
        with self.assertRaises(ConflictError):
            self.domain.adopt_chat_candidate(self.id, value, confirmed=True)
        value = self.candidate()
        for change in ('schema', 'semantic', 'instruction', 'id', 'json'):
            bad = copy.deepcopy(value)
            if change == 'schema': del bad['trip']['title']
            if change == 'semantic': bad['trip']['days'][0]['scheduleItems'][0]['dayId'] = 'missing'
            if change == 'instruction': bad['handled_instruction_ids'] = ['missing']
            if change == 'id': bad['trip']['id'] = 'different'
            self.file.write_text('{' if change == 'json' else json.dumps(bad))
            self.assertEqual(self.domain.review_chat_candidate(self.id)['status'], 'invalid')
            with self.assertRaises(ConflictError):
                self.domain.adopt_chat_candidate(self.id, bad, confirmed=True)
        self.file.write_text(json.dumps(value))
        snapshot = self.domain.review_chat_candidate(self.id)['candidate']
        value['trip']['title'] = '確認後に更新'
        self.file.write_text(json.dumps(value))
        with self.assertRaises(ConflictError):
            self.domain.adopt_chat_candidate(self.id, snapshot, confirmed=True)
        self.assertEqual(self.domain._trip_path(self.id).read_bytes(), before)
        self.assertEqual(self.context()['effective_revision']['trip_version'], 1)

    def test_new_instruction_remains_pending(self):
        value = self.candidate()
        self.domain.add_chat_instruction('late', self.id, '次の変更')
        self.domain.adopt_chat_candidate(self.id, value, confirmed=True)
        self.assertEqual([i['id'] for i in self.context()['instructions']], ['late'])

    def test_recover_interrupted_atomic_adoption(self):
        self.domain.add_chat_instruction('chat-1', self.id, '変更')
        value = self.candidate()
        with patch.object(self.domain, '_after_candidate_replace', side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):
                self.domain.adopt_chat_candidate(self.id, value, confirmed=True)
        result = self.domain.recover_trip_adoption(self.id)
        self.assertEqual(result['status'], 'adopted')
        self.assertFalse(self.file.exists())
        self.assertEqual(self.context()['instructions'], [])
        self.assertEqual(self.domain.get_effective_trip(self.id), value['trip'])

    def test_todo_reference_and_symlink(self):
        item = self.trip['days'][0]['scheduleItems'][0]['id']
        self.domain.create_todo('todo', label='prepare', trip_id=self.id, trip_item_id=item)
        value = self.candidate()
        value['trip']['days'][0]['scheduleItems'].pop(0)
        self.file.write_text(json.dumps(value))
        self.assertFalse(self.domain.review_chat_candidate(self.id)['ready'])
        self.file.unlink()
        self.file.symlink_to(ROOT / 'Samples/hokkaido-4days-candidate.json')
        with self.assertRaises(ValidationError):
            self.domain.review_chat_candidate(self.id)

if __name__ == '__main__':
    unittest.main()
