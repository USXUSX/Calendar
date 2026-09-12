import copy
import json
import unittest
import test_direct_schedule
from Sources.calendar_domain import ConflictError, ValidationError

class ReviewEditTests(unittest.TestCase):
    setUp = test_direct_schedule.DirectScheduleTests.setUp
    def edit(self, item, changes, kind='scheduleItem'):
        return self.domain.edit_trip_item('review-edit', self.tid, kind, item['id'], changes)

    def test_official_links_rating_and_transport_coordinates(self):
        from Sources.calendar_domain import build_trip_detail_view
        trip = copy.deepcopy(self.trip)
        item = trip['days'][0]['scheduleItems'][0]
        place = trip['places'][0]
        place.update(name='すし善', category='restaurant', officialUrl='https://example.com/official',
                     urls=['https://tabelog.com/example'], summary='静かな店',
                     rating={'source':'食べログ', 'value':3.65, 'observedAt':'2026-09-09'})
        item.update(action='すし善で夕食', status='confirmed')
        item['placeSelection'].update(candidatePlaceIds=[place['id']], selection=[place['id']])
        view = build_trip_detail_view(trip)
        entry = next(e for e in view['days'][0]['entries'] if e['source_item_id']==item['id'])
        self.assertEqual(entry['title'], 'すし善で夕食')
        self.assertEqual(entry['places'][0]['url'], place['officialUrl'])
        self.assertEqual(entry['candidates'][0]['tabelog_rating'], 3.65)
        place['category'] = 'hotel'
        candidate = next(e for e in build_trip_detail_view(trip)['days'][0]['entries'] if e['source_item_id']==item['id'])['candidates'][0]
        self.assertIsNone(candidate['tabelog_url'])
        self.assertIsNone(candidate['tabelog_rating'])
        transport = trip['transports'][0]
        endpoint = next(p for p in trip['places'] if p['id']==transport['fromPlaceId'])
        endpoint['location'] = {'latitude':43.06, 'longitude':141.35}
        entry = next(e for d in build_trip_detail_view(trip)['days'] for e in d['entries'] if e['source_item_id']==transport['id'])
        self.assertEqual(entry['places'][0]['location'], endpoint['location'])

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

    def test_full_comment_update_preserves_separate_ai_instruction(self):
        item = self.trip['days'][0]['scheduleItems'][0]
        saved = self.edit(item, {'normal_comment': '本文\n補足全文', 'supporting_details': [], 'ai_instruction': '雨天案を調べる'})
        entry = next(e for e in saved['view']['days'][0]['entries'] if e['source_item_id'] == item['id'])
        self.assertEqual(entry['normal_comment'], '本文\n補足全文')
        self.assertEqual(entry['supporting_details'], [])
        self.assertEqual(entry['ai_instruction'], '雨天案を調べる')

    def test_remove_candidate_only_from_target_and_preserve_other_references(self):
        item = next(i for d in self.trip['days'] for i in d['scheduleItems'] if len(i['placeSelection']['candidatePlaceIds']) > 1)
        pid, second = item['placeSelection']['candidatePlaceIds'][:2]
        other = next(i for d in self.trip['days'] for i in d['scheduleItems'] if i['id'] != item['id'])
        place = next(p for p in self.trip['places'] if p['id'] == pid)
        self.edit(other, {'place': {'id': pid, 'name': place['name']}})
        self.edit(item, {'selection': [pid], 'candidate_judgments': {pid: 'ok', second: 'ng'}})
        before = self.domain.get_effective_trip(self.tid)
        saved = self.edit(item, {'remove_candidate_place_id': pid})['trip']
        expected = copy.deepcopy(before)
        target = next(i for d in expected['days'] for i in d['scheduleItems'] if i['id'] == item['id'])
        target['placeSelection']['candidatePlaceIds'].remove(pid)
        target['placeSelection']['selection'] = []
        del target['candidateJudgments'][pid]
        self.assertEqual(saved, expected)
        for changes in ({'remove_candidate_place_id': pid}, {'remove_candidate_place_id': second, 'title': 'changed'}):
            with self.assertRaises(ValidationError): self.edit(item, changes)
            self.assertEqual(self.domain.get_effective_trip(self.tid), expected)

    def test_remove_last_candidate_and_shrink_bounds_survives_reload(self):
        from Sources.calendar_domain import CalendarDomain
        added = self.domain.change_trip_schedule('bounded', self.tid, 'add',
            dict(day_id=self.did, title='候補のある予定', category='other', place_name='合成場所'))
        item = added['trip']['days'][0]['scheduleItems'][-1]
        pid = item['placeSelection']['candidatePlaceIds'][0]
        before = self.domain.get_effective_trip(self.tid)
        saved = self.edit(item, {'remove_candidate_place_id': pid})['trip']
        target = self.domain._item_matches(saved, item['id'])[0]
        self.assertEqual(target['placeSelection'], dict(candidatePlaceIds=[], selection=[], minSelections=None, maxSelections=None))
        self.assertTrue(target['searchQuery'])
        self.assertEqual(saved['places'], before['places'])
        fresh = CalendarDomain(self.root/'db', self.root/'data', chat_root=self.root/'chat')
        self.assertEqual(fresh.get_effective_trip(self.tid), saved)
        self.assertEqual(next(e for e in fresh.get_trip_detail_view(self.tid)['days'][0]['entries'] if e['source_item_id']==item['id'])['candidates'], [])

    def test_remove_candidate_reduces_only_incompatible_bounds(self):
        from Sources.calendar_domain import CalendarDomain
        trip = copy.deepcopy(self.trip)
        trip['id'] = 'bounded-candidates'
        item = next(i for d in trip['days'] for i in d['scheduleItems'] if len(i['placeSelection']['candidatePlaceIds']) > 1)
        count = len(item['placeSelection']['candidatePlaceIds'])
        item['placeSelection'].update(minSelections=count, maxSelections=count)
        domain = CalendarDomain(self.root/'db', self.root/'data', chat_root=self.root/'chat')
        domain.import_trip_json(trip, confirmed=True)
        saved = domain.edit_trip_item('shrink', trip['id'], 'scheduleItem', item['id'],
            {'remove_candidate_place_id': item['placeSelection']['candidatePlaceIds'][0]})['trip']
        selection = domain._item_matches(saved, item['id'])[0]['placeSelection']
        self.assertEqual(selection['minSelections'], count-1)
        self.assertEqual(selection['maxSelections'], count-1)
        self.assertEqual(domain.get_effective_trip(trip['id']), saved)

    def test_candidate_comment_shared_place_and_atomic_failure(self):
        item = next(i for d in self.trip['days'] for i in d['scheduleItems'] if len(i['placeSelection']['candidatePlaceIds']) > 1)
        pid = item['placeSelection']['candidatePlaceIds'][0]
        place = next(p for p in self.trip['places'] if p['id'] == pid)
        other = next(i for d in self.trip['days'] for i in d['scheduleItems'] if i['id'] != item['id'])
        self.edit(other, {'place': {'id': pid, 'name': place['name']}})
        before = self.domain.get_effective_trip(self.tid)
        saved = self.edit(item, {'candidate_comments': {pid: '短い補足'}})
        expected = copy.deepcopy(before)
        next(p for p in expected['places'] if p['id'] == pid)['summary'] = '短い補足'
        self.assertEqual(saved['trip'], expected)
        refs = [c for d in saved['view']['days'] for e in d['entries'] for c in e['candidates'] if c['place_id']==pid]
        self.assertGreaterEqual(len(refs), 2)
        self.assertTrue(all(c['comment']=='短い補足' for c in refs))
        for changes in ({'candidate_comments': {pid: 1}}, {'candidate_comments': {pid: 'changed', 'missing': 'bad'}},
                        {'candidate_comments': {pid: 'changed'}, 'start': '29:00', 'time_mode': 'fixed'}):
            with self.assertRaises(ValidationError): self.edit(item, changes)
            self.assertEqual(self.domain.get_effective_trip(self.tid), expected)
        cleared = self.edit(item, {'candidate_comments': {pid: ''}})['trip']
        self.assertIsNone(next(p for p in cleared['places'] if p['id']==pid)['summary'])

    def test_candidate_adoption_updates_body_atomically_and_preserves_status_and_likes(self):
        item = next(i for d in self.trip['days'] for i in d['scheduleItems'] if len(i['placeSelection']['candidatePlaceIds']) > 1)
        pid, second = item['placeSelection']['candidatePlaceIds'][:2]
        name = next(p['name'] for p in self.trip['places'] if p['id'] == pid)
        self.edit(item, {'title': '小樽で昼食', 'candidate_judgments': {pid: 'ok'}})
        saved = self.edit(item, {'adopt_place_id': pid})
        selected = next(i for d in saved['trip']['days'] for i in d['scheduleItems'] if i['id'] == item['id'])
        self.assertEqual(selected['action'], name + 'で昼食')
        self.assertEqual(selected['status'], item['status'])
        self.assertEqual(selected['candidateJudgments'], {pid:'ok'})
        self.assertEqual(selected['placeSelection']['selection'], [pid])
        self.assertEqual(selected['placeSelection']['candidatePlaceIds'], item['placeSelection']['candidatePlaceIds'])
        saved = self.edit(item, {'adopt_place_id': second})
        selected = next(i for d in saved['trip']['days'] for i in d['scheduleItems'] if i['id'] == item['id'])
        self.assertEqual(selected['action'], next(p['name'] for p in self.trip['places'] if p['id'] == second) + 'で昼食')
        before = self.domain.get_effective_trip(self.tid)
        for changes in ({'adopt_place_id':'missing'}, {'adopt_place_id':pid, 'status':'confirmed'}):
            with self.assertRaises(ValidationError): self.edit(item, changes)
            self.assertEqual(self.domain.get_effective_trip(self.tid), before)

    def test_inline_clock_pair_and_candidate_preserve_text(self):
        item = self.trip['days'][0]['scheduleItems'][0]
        for show, mode, duration in ((True, 'range', 75), (False, 'fixed', None)):
            saved = self.edit(item, dict(start='09:00', end='10:15', show_duration=show))
            time = saved['trip']['days'][0]['scheduleItems'][0]['time']
            self.assertEqual(time, dict(mode=mode, start='09:00', end='10:15', durationMinutes=duration))
        saved = self.edit(item, dict(start=None, end='10:15', show_duration=True))
        self.assertEqual(saved['trip']['days'][0]['scheduleItems'][0]['time'],
                         dict(mode='undecided', start=None, end=None, durationMinutes=None))
        saved = self.edit(item, dict(start='23:30', end='00:30', show_duration=True))
        self.assertEqual(saved['trip']['days'][0]['scheduleItems'][0]['time']['durationMinutes'], 60)
        before = self.domain.get_effective_trip(self.tid)
        with self.assertRaises(ValidationError):
            self.edit(item, dict(title='invalid', start='29:00', end='10:15', show_duration=True))
        self.assertEqual(self.domain.get_effective_trip(self.tid), before)
        item = next(i for d in self.trip['days'] for i in d['scheduleItems'] if len(i['placeSelection']['candidatePlaceIds']) > 1)
        pid = item['placeSelection']['candidatePlaceIds'][0]
        saved = self.edit(item, {'selection': [pid]})
        selected = next(i for d in saved['trip']['days'] for i in d['scheduleItems'] if i['id'] == item['id'])
        self.assertEqual(selected['action'], item['action'])
        self.assertEqual(selected['status'], item['status'])
        added = self.domain.change_trip_schedule('inline-add', self.tid, 'add',
            dict(day_id=self.did, title='自然文の予定', category='other', start='09:00', end='10:15',
                 show_duration=True, status='confirmed', normal_comment='コメント'))
        new = next(i for i in added['trip']['days'][0]['scheduleItems'] if i['action'] == '自然文の予定')
        self.assertEqual(new['status'], 'confirmed')
        self.assertEqual(new['time']['durationMinutes'], 75)

    def test_transport_and_ordered_areas(self):
        item=self.trip['transports'][0]
        result=self.edit(item,dict(from_place={'name':'新千歳空港駅'},to_place={'name':'札幌駅'},transport_mode='shinkansen',service_name='確認用列車',status='tentative',ai_instruction=''),'transport')
        entry=next(e for d in result['view']['days'] for e in d['entries'] if e['source_item_id']==item['id'])
        self.assertEqual(entry['title'],'新千歳空港駅 → 札幌駅')
        self.assertEqual(entry['transport_mode'],'shinkansen')
        areas=[{'name':'小樽','location':None},{'name':'札幌','location':{'latitude':43.06,'longitude':141.35}}]
        result=self.domain.edit_trip_day('day',self.tid,self.did,{'areas':areas})
        self.assertEqual(result['view']['days'][0]['route_summary'],'小樽 → 札幌')
        self.assertEqual(self.domain.get_chat_context(self.tid)['trip']['days'][0]['areas'],areas)


    def test_transport_importance_category_and_booking_read_model(self):
        from Sources.calendar_domain import build_trip_detail_view
        transport = self.trip['transports'][0]
        before = self.domain.get_effective_trip(self.tid)
        saved = self.edit(transport, {'important': True}, 'transport')
        entry = next(e for d in saved['view']['days'] for e in d['entries'] if e['source_item_id'] == transport['id'])
        self.assertTrue(entry['important'])
        current = saved['trip']
        current['transports'][0].pop('important')
        self.assertEqual(current, before)
        self.assertTrue(self.domain.get_effective_trip(self.tid)['transports'][0]['important'])
        with self.assertRaises(ValidationError):
            self.edit(transport, {'important':'yes'}, 'transport')
        self.edit(transport, {'important':False}, 'transport')
        item = self.trip['days'][0]['scheduleItems'][0]
        self.edit(item, {'category':'other'})
        self.assertEqual(self.domain.get_effective_trip(self.tid)['days'][0]['scheduleItems'][0]['category'], 'other')
        trip = copy.deepcopy(self.trip)
        trip['bookings'] = [dict(id='reservation', status='pending', notes=None)]
        trip['transports'][0]['bookingId'] = 'reservation'
        for status in ('pending','booked','cancelled'):
            trip['bookings'][0]['status'] = status
            entry = next(e for d in build_trip_detail_view(trip)['days'] for e in d['entries'] if e['source_item_id'] == transport['id'])
            self.assertEqual(entry['booking_status'], status)

if __name__=='__main__':unittest.main()

class TripReview138Tests(unittest.TestCase):
    setUp = ReviewEditTests.setUp
    edit = ReviewEditTests.edit
    def test_none_time_and_comment_destinations(self):
        item = self.trip['days'][0]['scheduleItems'][0]
        saved = self.edit(item, {'time_mode':'none', 'start':'09:00', 'show_duration':True})
        entry = next(e for d in saved['view']['days'] for e in d['entries'] if e['source_item_id']==item['id'])
        self.assertEqual(entry['time'], dict(mode='none', start=None,end=None,durationMinutes=None,label=''))
        self.assertEqual(entry['order'], item['order'])
        field = entry['important_comment_fields'][0]
        saved = self.edit(item, {'normal_comment':'通常', 'important_comments':{field['source_id']:'重要'}})
        target = self.domain._item_matches(saved['trip'], field['source_id'])[0]
        self.assertEqual(target['importantComment' if field['source_id']==item['id'] else 'notes'], '重要')
        before = saved['trip']
        with self.assertRaisesRegex(ValidationError, '保存先'):
            self.edit(item, {'title':'失敗', 'important_comments':{'unrelated':'不正'}})
        self.assertEqual(self.domain.get_effective_trip(self.tid), before)
        with self.assertRaisesRegex(ValidationError, r'\.time\.start'):
            self.edit(item, {'start':'29:00', 'time_mode':'fixed'})
        self.assertEqual(self.domain.get_effective_trip(self.tid), before)
        saved = self.edit(item, {'time_mode':'undecided'})
        entry = next(e for d in saved['view']['days'] for e in d['entries'] if e['source_item_id']==item['id'])
        self.assertEqual(entry['time']['label'], '未定')

    def test_booking_notes_and_adopted_metadata(self):
        transport = next(t for t in self.trip['transports'] if t.get('bookingId'))
        saved = self.edit(transport, {'important_comments':{transport['bookingId']:'予約の重要事項'}}, 'transport')
        booking = next(b for b in saved['trip']['bookings'] if b['id']==transport['bookingId'])
        self.assertEqual(booking['notes'], '予約の重要事項')
        item = next(i for d in self.trip['days'] for i in d['scheduleItems'] if len(i['placeSelection']['candidatePlaceIds'])>1)
        pid = item['placeSelection']['candidatePlaceIds'][0]
        saved = self.edit(item, {'adopt_place_id':pid})
        entry = next(e for d in saved['view']['days'] for e in d['entries'] if e['source_item_id']==item['id'])
        candidate = next(p for p in entry['candidates'] if p['place_id']==pid)
        for key in ('tabelog_url','tabelog_rating'):
            self.assertEqual(entry['places'][0][key], candidate[key])
