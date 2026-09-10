import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize

ROOT = Path(__file__).resolve().parents[1]

class TripJsonImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'calendar.sqlite3'
        initialize(self.db)
        self.domain = CalendarDomain(self.db, self.root / 'data', chat_root=self.root / "chat")
        self.handoff = self.root / 'handoff'
        self.handoff.mkdir()
        self.candidate = json.loads((ROOT / 'Samples/hokkaido-4days-candidate.json').read_text())
        self.filename = self.candidate['id'] + "/candidate.json"
        self.file = self.handoff / self.filename
        self.file.parent.mkdir()
        self.file.write_text(json.dumps(self.candidate))

    def test_handoff_snapshot_adoption_and_duplicate(self):
        self.assertEqual(self.domain.list_trip_json_candidates(candidate_root=self.handoff)['files'], [self.filename])
        review = self.domain.read_trip_json_candidate(self.filename, candidate_root=self.handoff)
        self.assertTrue(review['ready'])
        self.assertEqual(len(review['view']['days']), 4)
        self.assertFalse(self.domain.trip_root.exists())
        self.file.write_text('{}')
        with self.assertRaises(ValidationError):
            self.domain.import_trip_json(review['candidate'])
        result = self.domain.import_trip_json(review['candidate'], confirmed=True)
        self.assertEqual(result['visibility'], 'owner')
        saved = self.domain._trip_path(result['trip_id'])
        self.assertEqual(json.loads(saved.read_text()), self.candidate)
        before = saved.read_bytes()
        changed = copy.deepcopy(self.candidate)
        changed['title'] = 'must not overwrite'
        with self.assertRaises(ConflictError):
            self.domain.import_trip_json(changed, confirmed=True)
        self.assertEqual(saved.read_bytes(), before)

    def test_representative_generation_import_adopt_and_edit(self):
        candidate = json.loads((ROOT / 'Samples/hokkaido-import-review.json').read_text())
        filename = candidate['id'] + '/candidate.json'
        (self.handoff / candidate['id']).mkdir()
        (self.handoff / filename).write_text(json.dumps(candidate))
        review = self.domain.read_trip_json_candidate(filename, candidate_root=self.handoff)
        self.assertTrue(review['ready'], review['errors'])
        self.domain.import_trip_json(review['candidate'], confirmed=True)
        trip_id = candidate['id']
        self.assertEqual(self.domain.get_effective_trip(trip_id), candidate)
        entries = {e['source_item_id']: e for d in review['view']['days'] for e in d['entries']}
        self.assertIn(candidate['bookings'][0]['notes'], entries['stay-1']['important_comments'])
        self.assertEqual(entries['departure']['booking_status'], 'pending')
        self.assertTrue(entries['arrival']['important'])
        self.assertFalse(entries['walk-museum']['important'])
        self.assertEqual(entries['visit-museum']['time']['durationMinutes'], 90)
        self.assertEqual(entries['city-choice']['title'], '札幌で名所を楽しむ')
        self.domain.edit_trip_item('adopt-clock', trip_id, 'scheduleItem', 'city-choice',
                                   {'adopt_place_id': 'clock'})
        effective = self.domain.get_effective_trip(trip_id)
        item = next(i for i in effective['days'][2]['scheduleItems'] if i['id'] == 'city-choice')
        self.assertEqual(item['placeSelection']['selection'], ['clock'])
        self.assertEqual(item['action'], '札幌市時計台で名所を楽しむ')
        self.assertEqual(item['status'], 'tentative')
        self.domain.edit_trip_item('edit-clock', trip_id, 'scheduleItem', 'city-choice',
                                   {'title': '札幌市時計台で展示を見る', 'normal_comment': 'ゆっくり見学',
                                    'start': '10:15', 'end': '11:15', 'time_mode': 'fixed'})
        effective = self.domain.get_effective_trip(trip_id)
        item = next(i for i in effective['days'][2]['scheduleItems'] if i['id'] == 'city-choice')
        self.assertEqual(item['action'], '札幌市時計台で展示を見る')
        self.assertEqual(item['time']['start'], '10:15')
        self.assertEqual(item['summary'], 'ゆっくり見学')
        self.assertEqual(effective['bookings'], candidate['bookings'])
        self.assertEqual(effective['transports'], candidate['transports'])
        self.assertEqual(json.loads(self.domain._trip_path(trip_id).read_text()), candidate)

    def test_invalid_json_schema_semantic_and_path(self):
        for value in ['{', 'null', '{}']:
            self.file.write_text(value)
            try:
                result = self.domain.read_trip_json_candidate(self.filename, candidate_root=self.handoff)
                self.assertFalse(result['ready'])
            except ValidationError:
                pass
        bad = copy.deepcopy(self.candidate)
        bad['days'][0]['scheduleItems'][0]['dayId'] = 'missing'
        self.assertFalse(self.domain.review_trip_json(bad)['ready'])
        with self.assertRaises(ValidationError):
            self.domain.import_trip_json(bad, confirmed=True)
        with self.assertRaises(ValidationError):
            self.domain.read_trip_json_candidate('../outside.json', candidate_root=self.handoff)
        self.file.unlink()
        self.file.symlink_to(ROOT / 'Samples/hokkaido-4days-candidate.json')
        self.assertEqual(self.domain.list_trip_json_candidates(candidate_root=self.handoff)['files'], [])
        with self.assertRaises(ValidationError):
            self.domain.read_trip_json_candidate(self.filename, candidate_root=self.handoff)
        self.assertFalse(self.domain.trip_root.exists())

    def test_shared_root_and_handoff_contract(self):
        default = CalendarDomain(self.db, self.root / 'unused')
        self.assertEqual(default._candidate_root(), Path('/Users/us/Tools/GoogleDrive/Calendar_Chat'))
        domain = CalendarDomain(self.db, self.domain.trip_root, chat_root=self.handoff)
        (self.file.parent / 'context.json').write_text('{}')
        (self.handoff / 'old.json').write_text('{}')
        self.assertEqual(domain.list_trip_json_candidates()['files'], [self.filename])
        self.assertTrue(domain.read_trip_json_candidate(self.filename)['ready'])
        wrong = self.handoff / 'wrong' / 'candidate.json'
        wrong.parent.mkdir()
        wrong.write_text(json.dumps(self.candidate))
        self.assertFalse(domain.read_trip_json_candidate('wrong/candidate.json')['ready'])
        envelope = {'trip_id': self.candidate['id'], 'base_revision': {},
                    'handled_instruction_ids': [], 'trip': self.candidate}
        self.file.write_text(json.dumps(envelope))
        self.assertFalse(domain.read_trip_json_candidate(self.filename)['ready'])
        self.assertEqual(json.loads(self.file.read_text()), envelope)
        self.assertFalse(self.domain.trip_root.exists())

    def test_nested_path_and_directory_symlink_rejected(self):
        for filename in ['../candidate.json', '/tmp/candidate.json',
                         'a/../candidate.json', 'a/b/candidate.json',
                         self.candidate['id'] + '/context.json', 'old.json']:
            with self.subTest(filename=filename), self.assertRaises(ValidationError):
                self.domain.read_trip_json_candidate(filename, candidate_root=self.handoff)
        linked = self.handoff / 'linked'
        linked.symlink_to(self.file.parent, target_is_directory=True)
        self.assertEqual(self.domain.list_trip_json_candidates(candidate_root=self.handoff)['files'],
                         [self.filename])
        with self.assertRaises(ValidationError):
            self.domain.read_trip_json_candidate('linked/candidate.json', candidate_root=self.handoff)

    def test_unregistered_orphan_file_is_replaced(self):
        path = self.domain._trip_path(self.candidate['id'])
        path.parent.mkdir(parents=True)
        path.write_text('obsolete orphan')
        review = self.domain.review_trip_json(self.candidate)
        self.assertTrue(review['ready'])
        result = self.domain.import_trip_json(review['candidate'], confirmed=True)
        self.assertEqual(result['status'], 'adopted')
        self.assertEqual(json.loads(path.read_text()), self.candidate)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM trips WHERE id = ?', (self.candidate['id'],)).fetchone()[0], 1)
        changed = copy.deepcopy(self.candidate)
        changed['title'] = 'must not overwrite registered trip'
        with self.assertRaises(ConflictError):
            self.domain.import_trip_json(changed, confirmed=True)
        self.assertEqual(json.loads(path.read_text()), self.candidate)

    def test_database_failure_removes_new_file(self):
        candidate = copy.deepcopy(self.candidate)
        candidate['id'] = candidate['id'] + '-db-failure'
        path = self.domain._trip_path(candidate['id'])
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER fail_import BEFORE INSERT ON trips BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(Exception):
            self.domain.import_trip_json(candidate, confirmed=True)
        self.assertFalse(path.exists())
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0], 0)

if __name__ == '__main__':
    unittest.main()
