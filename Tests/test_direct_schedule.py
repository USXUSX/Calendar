import copy
import json
import tempfile
import unittest
from pathlib import Path
from Sources.calendar_domain import CalendarDomain, ValidationError
from Sources.place_acquisition import Acquisition, FacilityCandidate
from scripts.init_calendar_db import initialize

class DirectScheduleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); initialize(self.root/'db')
        self.domain = CalendarDomain(self.root/'db',self.root/'data',chat_root=self.root/'chat')
        self.trip = json.loads(Path('Samples/hokkaido-4days-candidate.json').read_text())
        self.tid = self.trip['id']; self.did = self.trip['days'][0]['id']
        self.domain.import_trip_json(self.trip,confirmed=True)
    def change(self, action, **values):
        return self.domain.change_trip_schedule(action,self.tid,action,dict(day_id=self.did,**values))
    def test_add_edit_reorder_delete_and_chat_adopt(self):
        value = self.change('add',title='追加予定',category='sightseeing',start=None,end=None,place_name='合成場所')
        item = value['trip']['days'][0]['scheduleItems'][-1]
        self.domain.edit_trip_item('edit',self.tid,'scheduleItem',item['id'],{'title':'編集後'})
        ids = [e['source_item_id'] for e in value['view']['days'][0]['entries']][::-1]
        self.change('reorder',item_ids=ids)
        self.assertEqual([e['source_item_id'] for e in self.domain.get_trip_detail_view(self.tid)['days'][0]['entries']],ids)
        self.change('delete',source_item_id=item['id'])
        self.assertNotIn(item['id'], [i['id'] for i in self.domain.get_effective_trip(self.tid)['days'][0]['scheduleItems']])
        context = self.domain.get_chat_context(self.tid)
        candidate = dict(trip_id=self.tid,base_revision=context['effective_revision'],handled_instruction_ids=[],trip=context['trip'])
        candidate['trip']['title']='Chat反映'
        path = self.root/'chat'/self.tid/'candidate.json';path.write_text(json.dumps(candidate))
        self.domain.adopt_chat_candidate(self.tid,candidate,confirmed=True)
        self.assertEqual(self.domain.get_effective_trip(self.tid)['title'],'Chat反映')
    def test_paste_candidate_enrichment_does_not_select(self):
        value = self.change('add',text='予定: 未定 | 候補予定\nカテゴリ: 観光\n候補: 候補公園A\n候補: 候補公園B')
        item = value['trip']['days'][0]['scheduleItems'][-1]
        pid = item['placeSelection']['candidatePlaceIds'][0]
        class Adapter:
            def search(self, query):
                return Acquisition('candidates',[FacilityCandidate(dict(name=query.name,address='合成住所',urls=['https://example.com'],location=dict(latitude=35.,longitude=139.)),{})])
        before = copy.deepcopy(value['trip'])
        result = self.domain.get_place_enrichment(self.tid,{'place_id':pid},Adapter())
        self.domain.adopt_place_enrichment('enrich',self.tid,pid,result,0,confirmed=True)
        after = self.domain.get_effective_trip(self.tid)
        self.assertEqual(after['days'], before['days'])
        self.assertEqual(after['days'][0]['scheduleItems'][-1]['placeSelection']['selection'],[])
        self.domain.edit_trip_item('choose',self.tid,'scheduleItem',item['id'],{'selection':[pid]})
        self.assertEqual(self.domain.get_effective_trip(self.tid)['days'][0]['scheduleItems'][-1]['placeSelection']['selection'],[pid])
    def test_base_transport_delete_and_candidate_after_chat_adoption(self):
        transport = self.trip['transports'][0]
        self.domain.change_trip_schedule('remove-transport',self.tid,'delete',
            dict(day_id=transport['dayId'],source_item_id=transport['id']))
        current=self.domain.get_effective_trip(self.tid)
        self.assertNotIn(transport['id'],[t['id'] for t in current['transports']])
        self.assertTrue(all(transport['id'] not in d['transportIds'] for d in current['days']))
        ctx=self.domain.get_chat_context(self.tid)
        candidate=dict(trip_id=self.tid,base_revision=ctx['effective_revision'],handled_instruction_ids=[],trip=ctx['trip'])
        place=copy.deepcopy(candidate['trip']['places'][0]);place.update(id='chat-candidate-place',address=None,location=None,urls=[])
        candidate['trip']['places'].append(place)
        item=candidate['trip']['days'][0]['scheduleItems'][0]
        item['placeSelection']['candidatePlaceIds'].append(place['id'])
        path=self.root/'chat'/self.tid/'candidate.json';path.write_text(json.dumps(candidate))
        self.domain.adopt_chat_candidate(self.tid,candidate,confirmed=True)
        class Adapter:
            def search(self,query): return Acquisition('candidates',[FacilityCandidate(dict(name=query.name,address='Chat候補の補完住所'),{})])
        result=self.domain.get_place_enrichment(self.tid,{'place_id':place['id']},Adapter())
        self.domain.adopt_place_enrichment('after-chat',self.tid,place['id'],result,0,confirmed=True)
        after=self.domain.get_effective_trip(self.tid)
        self.assertEqual(after['days'],candidate['trip']['days'])
        self.assertEqual(next(p for p in after['places'] if p['id']==place['id'])['address'],'Chat候補の補完住所')

    def test_bad_paste_and_invalid_selection_do_not_write(self):
        before=self.domain.get_effective_trip(self.tid)
        with self.assertRaises(ValidationError): self.change('add',text='解釈できない行')
        item=before['days'][0]['scheduleItems'][0]
        with self.assertRaises(ValidationError): self.domain.edit_trip_item('bad',self.tid,'scheduleItem',item['id'],{'selection':['missing']})
        self.assertEqual(before,self.domain.get_effective_trip(self.tid))

if __name__ == '__main__': unittest.main()
