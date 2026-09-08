import copy
import json
import unittest
import test_direct_schedule
from Sources.calendar_domain import ConflictError, ValidationError

class ReviewEditTests(unittest.TestCase):
    setUp = test_direct_schedule.DirectScheduleTests.setUp
    def edit(self, item, changes, kind='scheduleItem'):
        return self.domain.edit_trip_item('review-edit', self.tid, kind, item['id'], changes)

    def test_sheet_roundtrip_and_handled_instruction(self):
        item = self.trip['days'][0]['scheduleItems'][0]
        saved = self.edit(item,dict(title='時計台へ行く', place={'name':'札幌市時計台','urls':['https://example.com/clock'],'location':{'latitude':43.06,'longitude':141.35}},time_mode='range',start='10:01',end=None,duration_minutes=90,ai_instruction='雨の場合の代替候補を探す'))
        entry=next(e for e in saved['view']['days'][0]['entries'] if e['source_item_id']==item['id'])
        self.assertEqual(entry['title'],'時計台へ行く');self.assertEqual(entry['time']['end'],'11:31')
        self.assertEqual(entry['places'][0]['name'],'札幌市時計台')
        self.assertEqual(entry['ai_instruction'],'雨の場合の代替候補を探す')
        ctx=self.domain.get_chat_context(self.tid)
        self.assertEqual(ctx['instructions'][0]['source_item_id'],item['id'])
        candidate=dict(trip_id=self.tid,base_revision=ctx['effective_revision'],handled_instruction_ids=[ctx['instructions'][0]['id']],trip=ctx['trip'])
        (self.root/'chat'/self.tid/'candidate.json').write_text(json.dumps(candidate))
        self.domain.adopt_chat_candidate(self.tid,candidate,confirmed=True)
        self.assertEqual(self.domain.get_chat_context(self.tid)['instructions'],[])
        self.assertTrue(all(not e['ai_instruction'] for d in self.domain.get_trip_detail_view(self.tid)['days'] for e in d['entries']))

    def test_replaced_instruction_rejects_old_candidate_and_keeps_new_pending(self):
        item = self.trip['days'][0]['scheduleItems'][0]
        self.edit(item, {'ai_instruction':'指示A'})
        context = self.domain.get_chat_context(self.tid)
        old_id = context['instructions'][0]['id']
        candidate = dict(trip_id=self.tid, base_revision=context['effective_revision'],
                         handled_instruction_ids=[old_id], trip=context['trip'])
        path = self.root/'chat'/self.tid/'candidate.json'
        path.write_text(json.dumps(candidate))
        self.edit(item, {'ai_instruction':'指示A'})
        self.assertTrue(self.domain.review_chat_candidate(self.tid)['ready'])
        for instruction in ('指示B', '', '指示A'):
            self.edit(item, {'ai_instruction':instruction})
            before = self.domain.get_effective_trip(self.tid)
            formal = (self.root/'data'/'trips'/f'{self.tid}.json').read_bytes()
            current = self.domain.get_chat_context(self.tid)
            self.assertFalse(self.domain.review_chat_candidate(self.tid)['ready'])
            with self.assertRaises(ConflictError):
                self.domain.adopt_chat_candidate(self.tid, candidate, confirmed=True)
            self.assertEqual(self.domain.get_effective_trip(self.tid), before)
            self.assertEqual((self.root/'data'/'trips'/f'{self.tid}.json').read_bytes(), formal)
            self.assertEqual(self.domain.get_chat_context(self.tid)['instructions'], current['instructions'])
            self.assertEqual(json.loads(path.read_text()), candidate)
        new_id = current['instructions'][0]['id']
        self.assertNotEqual(new_id, old_id)
        self.assertEqual(current['instructions'][0]['source_item_id'], item['id'])
        fresh = dict(trip_id=self.tid, base_revision=current['effective_revision'],
                     handled_instruction_ids=[new_id], trip=current['trip'])
        path.write_text(json.dumps(fresh))
        self.domain.adopt_chat_candidate(self.tid, fresh, confirmed=True)
        self.assertEqual(self.domain.get_chat_context(self.tid)['instructions'], [])

    def test_votes_separate_from_confirmation_and_atomic_failure(self):
        item=next(i for d in self.trip['days'] for i in d['scheduleItems'] if len(i['placeSelection']['candidatePlaceIds'])>1)
        pid=item['placeSelection']['candidatePlaceIds'][0]
        self.edit(item,{'candidate_judgments':{pid:'ok'}})
        current=self.domain.get_effective_trip(self.tid)
        selected=next(i for d in current['days'] for i in d['scheduleItems'] if i['id']==item['id'])
        self.assertEqual(selected['placeSelection']['selection'],item['placeSelection']['selection'])
        self.edit(item,{'selection':[pid],'status':'confirmed'})
        before=self.domain.get_effective_trip(self.tid)
        with self.assertRaises(ValidationError):self.edit(item,{'title':'changed','start':'30:00','ai_instruction':'invalid'})
        self.assertEqual(before,self.domain.get_effective_trip(self.tid))
        self.assertFalse(self.domain.get_chat_context(self.tid)['instructions'])

    def test_transport_and_ordered_areas(self):
        item=self.trip['transports'][0]
        result=self.edit(item,dict(from_place={'name':'新千歳空港駅'},to_place={'name':'札幌駅'},transport_mode='shinkansen',service_name='確認用列車',status='tentative',ai_instruction=''),'transport')
        entry=next(e for d in result['view']['days'] for e in d['entries'] if e['source_item_id']==item['id'])
        self.assertEqual(entry['title'],'新千歳空港駅から札幌駅へ移動')
        self.assertEqual(entry['transport_mode'],'shinkansen')
        areas=[{'name':'小樽','location':None},{'name':'札幌','location':{'latitude':43.06,'longitude':141.35}}]
        result=self.domain.edit_trip_day('day',self.tid,self.did,{'areas':areas})
        self.assertEqual(result['view']['days'][0]['route_summary'],'小樽 → 札幌')
        self.assertEqual(self.domain.get_chat_context(self.tid)['trip']['days'][0]['areas'],areas)

if __name__=='__main__':unittest.main()
