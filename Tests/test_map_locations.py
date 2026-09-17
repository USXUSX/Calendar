import copy
import json
from unittest import TestCase
from Tests import test_direct_schedule
from Sources.calendar_domain import ConflictError, ValidationError
from Sources.calendar_domain.map_locations import prepare, complete


class MapLocationsTest(TestCase):
    setUp = test_direct_schedule.DirectScheduleTests.setUp

    def test_only_map_targets_dedup_query_priority_and_failure(self):
        trip = copy.deepcopy(self.trip)
        _, initial = prepare(trip)
        for p in trip['places']: p['location'] = None
        p = next(p for p in trip['places'] if p['id'] == initial[0]['place_id'])
        p['address'] = '合成住所'
        _, plan = prepare(trip)
        point = next(x for x in plan if x['place_id'] == p['id'])
        self.assertEqual(point['query'], p['name']+' 合成住所')
        self.assertEqual(len({x['place_id'] for x in plan}), len(plan))
        self.assertLess(len(plan),len(trip['places']))  # home/access-side places excluded
        result, counts = complete(trip,{p['id']:{'latitude':43,'longitude':141}, 'not-a-target': {'latitude':0,'longitude':0}})
        self.assertEqual(counts,dict(filled=1,missing=len(plan)-1,existing=0))
        bad, bad_counts=complete(trip,{p['id']:{'latitude':999,'longitude':141}})
        self.assertEqual(bad_counts['filled'],0)
        imported=self.domain.import_trip_json(dict(result,id='new-import'),confirmed=True)
        self.assertEqual(imported['status'],'adopted')

    def test_saved_location_wins_and_manual_save_survives_chat(self):
        point=self.domain.prepare_import_locations(self.trip)[0]
        pid=point['place_id']; old=point['location']
        moved={'latitude':43.25,'longitude':141.25}
        self.domain.save_map_location('move',self.tid,pid,moved,old)
        with self.assertRaises(ConflictError):
            self.domain.save_map_location('stale',self.tid,pid,moved,old)
        context=self.domain.get_chat_context(self.tid)
        candidate=copy.deepcopy(context['trip'])
        next(p for p in candidate['places'] if p['id']==pid)['location']={'latitude':1,'longitude':2}
        envelope=dict(trip_id=self.tid,base_revision=context['effective_revision'],handled_instruction_ids=[],trip=candidate)
        self.domain._chat_path(self.tid,'candidate.json').write_text(json.dumps(envelope))
        self.domain.adopt_chat_candidate(self.tid,envelope,confirmed=True,coordinate_results={pid:{'latitude':3,'longitude':4}})
        self.assertEqual(next(p for p in self.domain.get_effective_trip(self.tid)['places'] if p['id']==pid)['location'],moved)
        self.assertEqual(self.domain.get_map_location(self.tid,pid)['location'],moved)
        with self.assertRaises(ValidationError):
            self.domain.save_map_location('invalid',self.tid,pid,{'latitude':True,'longitude':0},moved)

    def test_existing_or_new_schedule_needs_no_search(self):
        pid=self.trip['places'][0]['id']
        for command,values in [('existing',{'place_id':pid}),('new',{'place_name':'新規未登録'})]:
            result=self.domain.change_trip_schedule(command,self.tid,'add',dict(day_id=self.did,title='予定',category='food',start=None,end=None,**values))
            item=result['trip']['days'][0]['scheduleItems'][-1]
            place=next(p for p in result['trip']['places'] if p['id']==item['placeSelection']['selection'][0])
            if command=='existing': self.assertEqual(place['location'],self.trip['places'][0]['location'])
            else: self.assertIsNone(place['location'])

    def test_same_name_address_searched_once_and_coordinates_preserved(self):
        trip=copy.deepcopy(self.trip)
        _, plan=prepare(trip)
        target=next(p for p in trip['places'] if p['id']==plan[0]['place_id'])
        target.update(location=None,address='同一住所')
        duplicate=dict(copy.deepcopy(target),id='duplicate')
        trip['places'].append(duplicate)
        _, plan=prepare(trip)
        point=next(p for p in plan if target['id'] in p['place_ids'])
        self.assertIn('duplicate',point['place_ids'])
        result,counts=complete(trip,{point['place_id']:{'latitude':43,'longitude':141}})
        self.assertEqual([p['location'] for p in result['places'] if p['id'] in point['place_ids']],[{'latitude':43,'longitude':141}]*2)
