import copy
import json
from unittest import TestCase
from Tests.test_trip_json_import import TripJsonImportTests
from Sources.calendar_domain import ValidationError
from Sources.calendar_domain.map_locations import prepare


class HomeSettingsTest(TestCase):
    setUp = TripJsonImportTests.setUp
    home = dict(address='合成県合成市1-2-3', location=dict(latitude=35, longitude=139), googlePlaceId=None)

    def configure(self, value=None):
        path = self.domain.trip_root / 'settings' / 'home.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.home if value is None else value))
        return path

    def home_candidate(self):
        trip = copy.deepcopy(self.candidate)
        pid = prepare(trip)[1][0]['place_id']
        next(p for p in trip['places'] if p['id'] == pid).update(name='自宅', address=None, location=None, googlePlaceId='wrong')
        return trip, pid

    def test_new_import_uses_fixed_home_without_search(self):
        self.configure()
        trip, pid = self.home_candidate()
        original = copy.deepcopy(trip)
        plan = self.domain.prepare_import_locations(trip)
        self.assertEqual(next(p for p in plan if p['place_id'] == pid)['location'], self.home['location'])
        review = self.domain.review_trip_json(trip)
        self.assertTrue(review['ready'])
        self.domain.import_trip_json(review['candidate'], confirmed=True, coordinate_results={pid:{'latitude':1,'longitude':2}})
        saved = self.domain.get_effective_trip(trip['id'])
        expected = copy.deepcopy(trip)
        next(p for p in expected['places'] if p['id'] == pid).update(self.home)
        self.assertEqual(saved, expected)
        self.assertEqual(trip, original)
        self.assertEqual(json.loads(self.domain._trip_path(trip['id']).read_text()), expected)

    def test_existing_trips_and_context_use_common_home(self):
        trip, pid = self.home_candidate()
        self.domain.import_trip_json(trip, confirmed=True)
        other = dict(copy.deepcopy(trip), id='another-trip')
        self.domain.import_trip_json(other, confirmed=True)
        before = self.domain._trip_path(trip['id']).read_bytes()
        self.domain.save_map_location('old-pin', trip['id'], pid, {'latitude':1,'longitude':2}, None)
        old_revision = self.domain.get_chat_context(trip['id'])['effective_revision']
        path = self.configure()
        for tid in [trip['id'], other['id']]:
            home = next(p for p in self.domain.get_chat_context(tid)['trip']['places'] if p['id'] == pid)
            self.assertEqual({k:home[k] for k in self.home}, self.home)
        self.assertEqual(self.domain._trip_path(trip['id']).read_bytes(), before)
        self.assertNotEqual(old_revision, self.domain.get_chat_context(trip['id'])['effective_revision'])
        updated = dict(self.home, location={'latitude':36,'longitude':140})
        path.write_text(json.dumps(updated))
        self.assertEqual(self.domain.get_map_location(trip['id'], pid)['location'], updated['location'])
        with self.assertRaisesRegex(ValidationError, '共通設定'):
            self.domain.save_map_location('individual-home', trip['id'], pid, {'latitude':2,'longitude':3}, updated['location'])

    def test_chat_cannot_replace_fixed_home(self):
        self.configure()
        trip, pid = self.home_candidate()
        self.domain.import_trip_json(trip, confirmed=True)
        context = self.domain.get_chat_context(trip['id'])
        candidate = copy.deepcopy(context['trip'])
        next(p for p in candidate['places'] if p['id'] == pid).update(address='別住所', location={'latitude':1,'longitude':2}, googlePlaceId='wrong')
        envelope = dict(trip_id=trip['id'], base_revision=context['effective_revision'], handled_instruction_ids=[], trip=candidate)
        self.domain._chat_path(trip['id'], 'candidate.json').write_text(json.dumps(envelope))
        self.domain.adopt_chat_candidate(trip['id'], envelope, confirmed=True)
        self.assertEqual(self.domain.get_effective_trip(trip['id']), context['trip'])

    def test_inputs_and_paste_use_common_home(self):
        self.configure()
        trip, pid = self.home_candidate()
        self.domain.import_trip_json(trip, confirmed=True)
        day = trip['days'][0]['id']
        points = self.domain.prepare_location_inputs(trip['id'], day, [dict(name='自宅')])
        self.assertTrue(points[0]['skip_search'])
        self.assertEqual(points[0]['location'], self.home['location'])
        result = self.domain.change_trip_schedule('home-add', trip['id'], 'add', dict(day_id=day, title='帰宅', category='other', place_name='自宅'))
        for place in result['trip']['places']:
            if place['name'] == '自宅':
                self.assertEqual(place['address'], self.home['address'])
                self.assertEqual(place['location'], self.home['location'])
        plan = self.domain.change_trip_schedule('paste-home', trip['id'], 'prepare', dict(day_id=day, text='予定: 未定 | 昼食\nカテゴリ: 食事\n候補: 自宅'))['location_plan']
        self.assertEqual(next(p for p in plan if p['name'] == '自宅')['location'], self.home['location'])

    def test_missing_and_invalid_settings(self):
        trip, pid = self.home_candidate()
        self.assertEqual(self.domain.review_trip_json(trip)['candidate'], trip)
        path = self.configure(dict(address='合成住所', location={'latitude':999,'longitude':139}))
        with self.assertRaises(ValidationError):
            self.domain.review_trip_json(trip)
        path.write_text('{')
        with self.assertRaises(ValidationError):
            self.domain.review_trip_json(trip)
