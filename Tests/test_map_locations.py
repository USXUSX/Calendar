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

    def test_google_id_import_area_and_existing_coordinate_pair(self):
        trip=copy.deepcopy(self.trip)
        pid=prepare(trip)[1][0]['place_id']
        target=next(p for p in trip['places'] if p['id']==pid)
        target['location']=None
        trip['days'][0]['areas']=[dict(name='新エリア',location=None)]
        key=f'area:{self.did}:0'
        resolved=dict(location={'latitude':43,'longitude':141},googlePlaceId='google-facility')
        filled,counts=complete(trip,{pid:resolved,key:resolved})
        self.assertEqual(next(p for p in filled['places'] if p['id']==pid)['googlePlaceId'],'google-facility')
        self.assertEqual(filled['days'][0]['areas'][0]['googlePlaceId'],'google-facility')
        incoming=copy.deepcopy(filled)
        next(p for p in incoming['places'] if p['id']==pid).update(location=None,googlePlaceId='wrong')
        incoming['days'][0]['areas'][0].update(location=None,googlePlaceId='wrong')
        kept,_=complete(incoming,{},filled)
        self.assertEqual(kept,filled)
        self.domain.import_trip_json(dict(filled,id='google-import'),confirmed=True)
        self.assertEqual(self.domain.get_effective_trip('google-import')['days'][0]['areas'][0]['googlePlaceId'],'google-facility')

    def test_common_inputs_reuse_saved_and_query_priority(self):
        self.domain.edit_trip_day('area',self.tid,self.did,{'areas':[dict(name='旅行エリア',location=None)]})
        saved=self.trip['places'][0]
        plan=self.domain.prepare_location_inputs(self.tid,self.did,[dict(id=saved['id'],name=saved['name'],location={'latitude':0,'longitude':0}),dict(name='新施設',address='住所'),dict(name='新施設'),dict(name='新エリア',area=True)])
        self.assertTrue(plan[0]['skip_search'])
        self.assertEqual(plan[0]['location'],saved['location'])
        self.assertEqual([p['query'] for p in plan[1:]],['新施設 住所','新施設 旅行エリア','新エリア'])

    def test_new_schedule_and_candidate_keep_google_id(self):
        resolved=dict(location={'latitude':43,'longitude':141},googlePlaceId='google-new')
        result=self.domain.change_trip_schedule('new-google',self.tid,'add',dict(day_id=self.did,title='新予定',category='food',place_name='新施設',resolved_place=resolved))
        item=result['trip']['days'][0]['scheduleItems'][-1]
        pid=item['placeSelection']['selection'][0]
        self.assertEqual(next(p for p in result['trip']['places'] if p['id']==pid)['googlePlaceId'],'google-new')
        result=self.domain.edit_trip_item('candidate-google',self.tid,'scheduleItem',item['id'],{'candidate_place':dict(name='別候補',**resolved)})
        trip=self.domain.get_effective_trip(self.tid)
        item=next(i for i in trip['days'][0]['scheduleItems'] if i['id']==item['id'])
        self.assertEqual(item['placeSelection']['selection'],[pid])
        self.assertEqual(len(item['placeSelection']['candidatePlaceIds']),2)
        self.assertEqual(next(p for p in trip['places'] if p['id']==item['placeSelection']['candidatePlaceIds'][-1])['googlePlaceId'],'google-new')

    def test_area_correction_and_following_day_edit_preserve_position(self):
        self.domain.edit_trip_day('area-new',self.tid,self.did,{'areas':[dict(name='エリア',location=None)]})
        key=f'area:{self.did}:0';location={'latitude':43,'longitude':141}
        self.domain.save_map_location('area-pin',self.tid,key,location,None,'google-area')
        self.domain.edit_trip_day('area-again',self.tid,self.did,{'areas':[dict(name='エリア',location=None)]})
        area=self.domain.get_effective_trip(self.tid)['days'][0]['areas'][0]
        self.assertEqual(area,dict(name='エリア',location=location,googlePlaceId='google-area'))
        moved={'latitude':44,'longitude':142}
        self.domain.save_map_location('area-manual',self.tid,key,moved,location)
        area=self.domain.get_effective_trip(self.tid)['days'][0]['areas'][0]
        self.assertEqual(area['location'],moved)
        self.assertIsNone(area['googlePlaceId'])

    def test_pasted_schedule_uses_same_plan_and_google_result(self):
        values=dict(day_id=self.did,text='予定: 未定 | 昼食\nカテゴリ: 食事\n候補: 店A\n候補: 店B')
        plan=self.domain.change_trip_schedule('paste-google',self.tid,'prepare',values)['location_plan']
        self.assertEqual(len(plan),2)
        values['coordinate_results']={p['place_id']:dict(location={'latitude':43,'longitude':141},googlePlaceId='google-paste') for p in plan}
        result=self.domain.change_trip_schedule('paste-google',self.tid,'add',values)
        item=result['trip']['days'][0]['scheduleItems'][-1]
        self.assertEqual(item['placeSelection']['selection'],[])
        for pid in item['placeSelection']['candidatePlaceIds']:
            self.assertEqual(next(p for p in result['trip']['places'] if p['id']==pid)['googlePlaceId'],'google-paste')
