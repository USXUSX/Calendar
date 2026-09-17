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

    def test_return_day_five_stops_grouping_and_access_exclusion(self):
        # Synthetic return day: hotel -> market -> lunch -> station -> airport.
        trip = self.trip
        day = trip['days'][-1]
        prototype = copy.deepcopy(trip['days'][0]['scheduleItems'][0])
        transport = copy.deepcopy(trip['transports'][0])
        place = copy.deepcopy(trip['places'][0])
        ids = ['hotel', 'market', 'lunch-a', 'lunch-b', 'station', 'airport', 'home-airport', 'home']
        trip['places'] = [dict(copy.deepcopy(place),id=pid,name=pid,address='',location=dict(latitude=43,longitude=141)) for pid in ids]
        def item(pid, order, candidates=None, **extra):
            value = dict(copy.deepcopy(prototype),id='visit-'+pid,dayId=day['id'],order=order,**extra)
            value['placeSelection'].update(selection=[] if candidates else [pid],candidatePlaceIds=candidates or [pid])
            return value
        day['scheduleItems'] = [item('hotel',0),item('market',2,['lunch-a'],mapPlaceId='market'),item('lunch',5,['lunch-a','lunch-b']),item('home',9),item('home-airport',8,mapPlaceId=None)]
        def move(identity,order,start,end,mode='car'):
            return dict(copy.deepcopy(transport),id=identity,dayId=day['id'],order=order,fromPlaceId=start,toPlaceId=end,mode=mode)
        trip['transports'] = [move('to-market',1,'hotel','market'),move('to-station',3,'market','station'),move('to-airport',6,'station','airport','train'),move('return-flight',7,'airport','home-airport','flight')]
        for d in trip['days'][:-1]:
            d['scheduleItems']=[]; d['transportIds']=[]
        day['transportIds']=[t['id'] for t in trip['transports']]
        before=copy.deepcopy(trip)
        stops=build_trip_detail_view(trip)['days'][-1]['map_stops']
        self.assertEqual([s['name'] for s in stops],['hotel','market',prototype['action']+'（候補）','station','airport'])
        self.assertEqual(len(stops[2]['points']),2)
        self.assertEqual(len(stops[1]['references']),3)
        self.assertEqual([r['entry_key'] for r in stops[-1]['references']],['transport:to-airport','transport:return-flight'])
        self.assertEqual(trip,before)
        # Car-only return keeps the home endpoint; explicit null still hides visits.
        trip['transports'][-1]['mode']='car'
        stops=build_trip_detail_view(trip)['days'][-1]['map_stops']
        self.assertIn('home', [s['name'] for s in stops])
        self.assertIn('home-airport', [s['name'] for s in stops])

    def test_display_target_retains_candidate_names_and_own_positions(self):
        trip = self.trip
        item = trip['days'][0]['scheduleItems'][0]
        target, first, second = trip['places'][:3]
        item['mapPlaceId'] = target['id']
        item['placeSelection'].update(selection=[], candidatePlaceIds=[first['id'],second['id']])
        target['location'] = dict(latitude=43,longitude=141)
        first['location'] = None
        second['location'] = dict(latitude=44,longitude=142)
        before = copy.deepcopy(trip)
        stop = next(s for s in build_trip_detail_view(trip)['days'][0]['map_stops'] if s['stop_id']=='place:'+target['id'])
        self.assertTrue(stop['candidate'])
        self.assertEqual([p['name'] for p in stop['points']], [first['name'],second['name']])
        self.assertEqual(stop['points'][0]['location'],target['location'])
        self.assertEqual(stop['points'][1]['location'],second['location'])
        self.assertEqual(trip,before)
        item['placeSelection']['selection']=[second['id']]
        stop = next(s for s in build_trip_detail_view(trip)['days'][0]['map_stops'] if s['stop_id']=='place:'+target['id'])
        self.assertFalse(stop['candidate'])
        self.assertEqual([p['place_id'] for p in stop['points']], [second['id']])

    def test_outbound_access_and_unlocated_explicit_target(self):
        trip=self.trip
        first=trip['transports'][0]
        first['mode']='flight'
        day=trip['days'][0]
        item=day['scheduleItems'][0]
        item['order']=-1
        item['mapPlaceId']=first['fromPlaceId']
        stops=build_trip_detail_view(trip)['days'][0]['map_stops']
        self.assertNotIn(first['fromPlaceId'],[p['place_id'] for s in stops for p in s['points']])
        item['order']=2
        item['mapPlaceId']=first['toPlaceId']
        place=next(p for p in trip['places'] if p['id']==first['toPlaceId'])
        place['location']=None
        stops=build_trip_detail_view(trip)['days'][0]['map_stops']
        stop=next(s for s in stops if s['stop_id']=='place:'+place['id'])
        self.assertIsNone(stop['points'][0]['location'])
        self.assertTrue(any(r['entry_key']=='scheduleItem:'+item['id'] for r in stop['references']))
