import copy
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import sqlite3
import unittest
import test_trip_chat
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError


class TripRequestsTest(unittest.TestCase):
    attempts = test_trip_chat.TripChatTest.attempts
    create = test_trip_chat.TripChatTest.create
    update = test_trip_chat.TripChatTest.update
    # Use fixture helpers without inheriting the Chat test cases.
    def setUp(self):
        test_trip_chat.TripChatTest.setUp(self)
        self.cal.apply_trip_request(self.create())
        self.did = self.trip['days'][0]['id']
        self.item = self.trip['days'][0]['scheduleItems'][0]['id']

    def request(self, identity, operation='item', values=None):
        return dict(request_id=identity, trip_id=self.tid, operation=operation,
                    expected_revision=self.cal.get_trip_command_context(self.tid)['revision'],
                    values=values or dict(source_type='scheduleItem', source_item_id=self.item, changes={'title':'合成編集'}))

    def test_operation_groups_and_replay_after_delete(self):
        original=copy.deepcopy(self.trip)
        item_request=self.request('edit')
        result=self.cal.apply_trip_operation(item_request)
        self.assertEqual(self.cal.lookup_chat_request('edit')['receipt'],result['receipt'])
        self.cal.apply_trip_operation(self.request('day','day',dict(day_id=self.did,changes={'title':'日別変更'})))
        added=self.cal.apply_trip_operation(self.request('add','add',dict(day_id=self.did,title='追加',category='food',start=None,end=None)))
        view=self.cal.get_trip_edit_view(self.tid)
        self.assertEqual(view['revision'],self.cal.get_trip_command_context(self.tid)['revision'])
        ids=[e['source_item_id'] for e in view['days'][0]['entries']]
        self.cal.apply_trip_operation(self.request('reorder','reorder',dict(day_id=self.did,item_ids=ids[::-1])))
        self.cal.apply_trip_operation(self.request('delete','delete',dict(day_id=self.did,source_item_id=self.item)))
        self.assertEqual(self.cal.apply_trip_operation(item_request)['receipt'],result['receipt'])
        with self.assertRaisesRegex(ConflictError,'payload_conflict'):
            self.cal.apply_trip_operation(item_request|{'operation':'day'})
        self.assertEqual(self.cal._load_trip(self.tid), original)
        self.assertEqual(added['receipt']['action'],'add')

    def test_instruction_revision_and_chat_conflicts(self):
        stale=self.request('stale')
        chat=self.update('chat-old')
        result=self.cal.apply_trip_operation(self.request('instruction','instruction',{'instruction':'全体への合成指示'}))
        self.assertEqual(result['receipt']['instructions_state'],'pending')
        self.assertNotEqual(result['receipt']['previous_revision']['instructions_hash'], result['receipt']['revision']['instructions_hash'])
        for request, apply in [(stale,self.cal.apply_trip_operation),(chat,self.cal.apply_trip_request)]:
            with self.assertRaisesRegex(ConflictError,'revision_conflict'):apply(request)
        screen=self.request('screen-old')
        self.cal.apply_trip_request(self.update('chat-new'))
        with self.assertRaisesRegex(ConflictError,'revision_conflict'):self.cal.apply_trip_operation(screen)
        self.cal.apply_trip_operation(self.request('row-instruction',values=dict(source_type='scheduleItem',source_item_id=self.item,changes={'ai_instruction':'行の指示'})))
        self.cal.apply_trip_operation(self.request('row-clear',values=dict(source_type='scheduleItem',source_item_id=self.item,changes={'ai_instruction':''})))

    def test_candidates_map_and_old_point_expectation(self):
        self.cal.apply_trip_operation(self.request('new-candidate',values=dict(source_type='scheduleItem',source_item_id=self.item,changes={'candidate_place':{'name':'合成候補'}})))
        trip=self.cal.get_effective_trip(self.tid)
        item=trip['days'][0]['scheduleItems'][0]
        pid=item['placeSelection']['candidatePlaceIds'][0]
        for n,changes in enumerate([{'candidate_judgments':{pid:'ok'}},{'candidate_comments':{pid:'合成コメント'}},{'map_display_names':{pid:'表示'}},{'adopt_place_id':pid},{'selection':[]}]):
            self.cal.apply_trip_operation(self.request('candidate'+str(n),values=dict(source_type='scheduleItem',source_item_id=self.item,changes=changes)))
        point=self.cal.get_map_location(self.tid,pid)
        values=dict(place_id=pid,location={'latitude':35.0,'longitude':139.0},expected_location=point['location'],expected_name=point['name'])
        self.cal.apply_trip_operation(self.request('map','location',values))
        before=self.cal.get_trip_command_context(self.tid)
        with self.assertRaises(ConflictError):self.cal.apply_trip_operation(self.request('map-old-point','location',values))
        self.assertEqual(self.cal.get_trip_command_context(self.tid),before)
        self.cal.apply_trip_operation(self.request('remove-candidate',values=dict(source_type='scheduleItem',source_item_id=self.item,changes={'remove_candidate_place_id':pid})))

    def test_parallel_response_loss_and_atomic_receipt_failure(self):
        request=self.request('parallel')
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:CalendarDomain(self.db,self.root).apply_trip_operation(request),range(2)))
        self.assertEqual({r['resolution'] for r in results},{'new','replayed'})
        self.assertEqual(results[0]['receipt'],results[1]['receipt'])
        self.assertEqual(self.cal.lookup_chat_request('parallel')['receipt'],results[0]['receipt'])
        before=self.cal.get_trip_command_context(self.tid)
        with self.cal._command() as c:
            c.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON schedule_receipts BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(ValidationError):
            self.cal.apply_trip_operation(self.request('rollback','instruction',{'instruction':'保存されない指示'}))
        self.assertEqual(self.cal.get_trip_command_context(self.tid),before)
        self.assertEqual(self.cal.lookup_chat_request('rollback')['status'],'not_found')
        with self.assertRaises(ValidationError):self.cal.apply_trip_operation(self.request('bad',values=dict(source_type='scheduleItem',source_item_id=self.item,changes={'title':None})))
        self.assertEqual(self.cal.get_trip_command_context(self.tid),before)

    def test_write_does_not_build_view_or_resend_google(self):
        request=self.request('view-independent')
        with patch.object(self.cal,'get_trip_detail_view',side_effect=RuntimeError('view failed')), patch.object(self.cal,'sync_google',return_value={'status':'unreflected'}) as sync:
            result=self.cal.apply_trip_operation(request)
            self.assertEqual(result['status'],'committed')
            self.cal.apply_trip_operation(request)
            self.assertEqual(sync.call_count,1)

