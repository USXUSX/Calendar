import copy
import json
from pathlib import Path
import unittest

from Sources.calendar_domain.trip_detail import build_trip_detail_view


class TripMapTest(unittest.TestCase):
    def setUp(self):
        self.trip = json.loads(Path('Samples/hokkaido-4days-candidate.json').read_text())

    def test_occurrences_candidates_links_and_no_mutation(self):
        item = self.trip['days'][0]['scheduleItems'][0]
        places = self.trip['places'][:2]
        item['placeSelection'].update(selection=[], candidatePlaceIds=[p['id'] for p in places])
        places[0]['location'] = dict(latitude=43.06, longitude=141.35)
        places[0]['officialUrl'] = 'https://example.com/park'
        places[0]['urls'] = ['https://example.com/park', 'https://example.com/info']
        places[1]['location'] = None
        before = copy.deepcopy(self.trip)
        view = build_trip_detail_view(self.trip)
        entry = next(e for e in view['days'][0]['entries'] if e['source_item_id'] == item['id'])
        self.assertEqual([p['role'] for p in entry['map_points']], ['candidate', 'candidate'])
        self.assertTrue(all(not p['overview'] for p in entry['map_points']))
        self.assertIsNone(entry['map_points'][1]['location'])
        self.assertEqual(entry['map_points'][0]['links'], ['https://example.com/park', 'https://example.com/info'])
        self.assertEqual(self.trip, before)
        item['placeSelection']['selection'] = [places[0]['id']]
        selected = next(e for e in build_trip_detail_view(self.trip)['days'][0]['entries'] if e['source_item_id'] == item['id'])
        self.assertEqual(len(selected['map_points']), 1)
        self.assertEqual(selected['map_points'][0]['role'], 'selected')
        self.assertTrue(selected['map_points'][0]['overview'])

    def test_transport_retains_both_endpoints_and_order(self):
        transport = self.trip['transports'][0]
        transport['important'] = True
        entries = build_trip_detail_view(self.trip)['days'][0]['entries']
        entry = next(e for e in entries if e['source_item_id'] == transport['id'])
        self.assertEqual([p['place_id'] for p in entry['map_points']], [transport['fromPlaceId'], transport['toPlaceId']])
        self.assertEqual([p['role'] for p in entry['map_points']], ['departure', 'arrival'])
        self.assertTrue(all(p['overview'] for p in entry['map_points']))
        self.assertEqual([e['order'] for e in entries], sorted(e['order'] for e in entries))
