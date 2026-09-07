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
        self.domain = CalendarDomain(self.db, self.root / 'data')
        self.handoff = self.root / 'handoff'
        self.handoff.mkdir()
        self.candidate = json.loads((ROOT / 'Samples/hokkaido-4days-candidate.json').read_text())
        self.file = self.handoff / (self.candidate['id'] + '.json')
        self.file.write_text(json.dumps(self.candidate))

    def test_handoff_snapshot_adoption_and_duplicate(self):
        self.assertEqual(self.domain.list_trip_json_candidates(candidate_root=self.handoff)['files'], [self.file.name])
        review = self.domain.read_trip_json_candidate(self.file.name, candidate_root=self.handoff)
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

    def test_invalid_json_schema_semantic_and_path(self):
        for value in ['{', 'null', '{}']:
            self.file.write_text(value)
            try:
                result = self.domain.read_trip_json_candidate(self.file.name, candidate_root=self.handoff)
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
            self.domain.read_trip_json_candidate(self.file.name, candidate_root=self.handoff)
        self.assertFalse(self.domain.trip_root.exists())

    def test_unregistered_file_and_database_failure(self):
        path = self.domain._trip_path(self.candidate['id'])
        path.parent.mkdir(parents=True)
        path.write_text('existing')
        with self.assertRaises(ConflictError):
            self.domain.import_trip_json(self.candidate, confirmed=True)
        self.assertEqual(path.read_text(), 'existing')
        path.unlink()
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TRIGGER fail_import BEFORE INSERT ON trips BEGIN SELECT RAISE(ABORT, 'test'); END")
        with self.assertRaises(Exception):
            self.domain.import_trip_json(self.candidate, confirmed=True)
        self.assertEqual(list(path.parent.iterdir()), [])
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM trips').fetchone()[0], 0)

if __name__ == '__main__':
    unittest.main()
