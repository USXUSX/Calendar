import base64
import io
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from scripts import cal_schedule
from Sources.calendar_domain import CalendarDomain, ConflictError, NotFoundError, ValidationError
from scripts.init_calendar_db import initialize
from scripts.migrate_schedule_receipts import migrate

ROOT = Path(__file__).resolve().parents[1]


class ScheduleChatTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'cal.sqlite3';initialize(self.db)
        self.cal=CalendarDomain(self.db,self.root,chat_root=self.root/'unused-chat')

    def create(self, kind='event', identity='create'):
        values=dict(title='合成予定',start_date='2099-01-02',notes='一行\n二行') if kind=='event' else dict(label='合成タスク',due_date='2099-01-02')
        return dict(request_id=identity,kind=kind,action='save',values=values)

    def test_cli_deferred_saves_under_network_block(self):
        def cli(action, request=None):
            stdout = io.StringIO()
            with patch('sys.stdin', io.StringIO(json.dumps(request))), patch('sys.stdout', stdout):
                code = cal_schedule.main(['--database', str(self.db), '--local-root', str(self.root)]+action)
            return code, json.loads(stdout.getvalue())

        # Both transport and sync entry are guarded: even a swallowed network error
        # must not make a deferred save appear to pass.
        with patch('socket.socket.connect', side_effect=PermissionError('network blocked')) as network, \
             patch.object(CalendarDomain, 'sync_google', side_effect=PermissionError('network blocked')) as sync:
            requests = [self.create(identity='blocked-'+str(i)) for i in range(2)]
            receipts = []
            for request in requests:
                code, saved = cli(['apply', '--defer-google-sync'], request)
                self.assertEqual((code, saved['status'], saved['google']['sync']), (0, 'committed', 'deferred'))
                self.assertEqual(saved['google']['status'], 'unreflected')
                self.assertNotIn('google', saved['receipt'])
                receipts.append(saved['receipt'])
            self.assertEqual(saved['google']['pending'], 2)
            for request, receipt in zip(requests, receipts):
                self.assertEqual(cli(['lookup', '--request-id', request['request_id']])[1]['receipt'], receipt)
                self.assertEqual(cli(['get', '--kind', 'event', '--id', receipt['entity_id']])[1]['item'], receipt['item'])
                replay = cli(['apply', '--defer-google-sync'], request)[1]
                self.assertEqual(replay['resolution'], 'replayed')
                self.assertEqual(replay['receipt'], receipt)
                # Delivery choice is outside the persisted request identity.
                self.assertEqual(cli(['apply'], request)[1]['receipt'], receipt)
                changed = dict(request, values=dict(request['values'], title='合成変更'))
                self.assertEqual(cli(['apply', '--defer-google-sync'], changed)[0], 3)
            self.assertEqual(len(cli(['read', '--start', '2099-01-02', '--end', '2099-01-02'])[1]['items']), 2)
            stale = dict(requests[0], request_id='stale-deferred', id=receipts[0]['entity_id'], expected_revision='sha256:stale')
            self.assertEqual(cli(['apply', '--defer-google-sync'], stale)[0], 3)
            sync.assert_not_called()
            network.assert_not_called()
            # Default saves still attempt automatic sync; retry remains separate.
            code, saved = cli(['apply'], self.create(identity='default-sync'))
            self.assertEqual((code, saved['status']), (0, 'committed'))
            self.assertEqual(sync.call_count, 1)

    def apply_to(self, receipt, identity, action, values):
        return self.cal.apply_schedule_request(dict(request_id=identity,kind=receipt['kind'],action=action,
            id=receipt['entity_id'],expected_revision=receipt['revision'],values=values))['receipt']

    def test_lifecycle_and_period_read_revisions(self):
        for kind in ('event','todo'):
            receipt=self.cal.apply_schedule_request(self.create(kind,kind))['receipt']
            entity=receipt['entity_id']
            self.assertEqual(self.cal.get_schedule_item(kind,entity)['revision'],receipt['revision'])
            items=self.cal.read_schedule('2099-01-01','2099-01-03',include_completed=True,include_trips=False)['items']
            self.assertEqual(next(x for x in items if x['id']==entity)['revision'],receipt['revision'])
            receipt=self.apply_to(receipt,kind+'-edit','save',{'notes':'更新'})
            self.assertEqual(receipt['item']['notes'],'更新')
            if kind=='todo':
                receipt=self.apply_to(receipt,'complete','complete',{'completed':True})
                self.assertTrue(receipt['item']['completed_at'])
                receipt=self.apply_to(receipt,'undo','complete',{'completed':False})
                self.assertIsNone(receipt['item']['completed_at'])
            previous=receipt
            receipt=self.apply_to(receipt,kind+'-delete','delete',{})
            self.assertTrue(receipt['deleted']);self.assertIsNone(receipt['revision'])
            self.assertEqual(self.apply_to(previous,kind+'-delete','delete',{}),receipt)
            with self.assertRaises(NotFoundError):self.cal.get_schedule_item(kind,entity)
            self.assertEqual(self.cal.lookup_schedule_request(kind+'-delete')['receipt'],receipt)
        self.assertFalse((self.root/'unused-chat').exists())

    def test_same_id_replay_conflict_and_concurrent_send(self):
        request=self.create()
        def apply(_):return CalendarDomain(self.db,self.root).apply_schedule_request(request)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(apply,range(2)))
        self.assertEqual({x['resolution'] for x in results},{'new','replayed'})
        self.assertEqual(results[0]['receipt'],results[1]['receipt'])
        with self.assertRaisesRegex(ConflictError,'request_id_payload_conflict'):
            self.cal.apply_schedule_request(request|{'values':request['values']|{'title':'変更'}})
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],1)
            self.assertEqual(c.execute('SELECT count(*) FROM schedule_receipts').fetchone()[0],1)

    def test_stale_after_frame_write_and_invalid_requests_leave_no_receipt(self):
        receipt=self.cal.apply_schedule_request(self.create())['receipt']
        self.cal.change_schedule('event','save',receipt['entity_id'],{'title':'画面から変更'}, expected_revision=receipt['revision'], request_id='screen-edit')
        for action,values in [('save',{'title':'古い入力'}),('delete',{})]:
            with self.assertRaisesRegex(ConflictError,'revision_conflict'):
                self.apply_to(receipt,action,action,values)
            self.assertEqual(self.cal.lookup_schedule_request(action)['status'],'not_found')
        with self.assertRaises(ValidationError):self.cal.apply_schedule_request(self.create(identity='bad')|{'values':{'title':''}})
        self.assertEqual(self.cal.lookup_schedule_request('bad')['status'],'not_found')

    def test_receipt_failure_rolls_back_item(self):
        with sqlite3.connect(self.db) as c:
            c.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON schedule_receipts BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(ValidationError):self.cal.apply_schedule_request(self.create())
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],0)

    def test_crash_before_and_after_commit(self):
        for when,code in [('before',85),('after',86)]:
            request=self.create(identity=when)
            script='''import os,sys,json
from contextlib import contextmanager
from Sources.calendar_domain import CalendarDomain
cal=CalendarDomain(sys.argv[1],sys.argv[2])
if sys.argv[3]=='before':
 original=cal._command
 @contextmanager
 def fail():
  with original() as c:
   yield c
   os._exit(85)
 cal._command=fail
cal.apply_schedule_request(json.loads(sys.argv[4]))
os._exit(86)
'''
            result=subprocess.run([sys.executable,'-B','-c',script,str(self.db),str(self.root),when,json.dumps(request)],cwd=ROOT,capture_output=True)
            self.assertEqual(result.returncode,code);self.assertEqual(result.stdout,b'')
            lookup=self.cal.lookup_schedule_request(when)
            self.assertEqual(lookup['status'],'not_found' if when=='before' else 'committed')
            retry=self.cal.apply_schedule_request(request)
            self.assertEqual(retry['resolution'],'new' if when=='before' else 'replayed')
            if when=='after':self.assertEqual(retry['receipt'],lookup['receipt'])
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],2)

    def test_migration_preserves_existing_rows_and_cli(self):
        receipt=self.cal.apply_schedule_request(self.create())['receipt']
        with sqlite3.connect(self.db) as c:c.execute('DROP TABLE schedule_receipts')
        migrate(self.db);migrate(self.db)
        self.assertEqual(self.cal.get_schedule_item('event',receipt['entity_id'])['item'],receipt['item'])
        with self.assertRaises(sqlite3.OperationalError):migrate(self.root/'missing.sqlite3')
        command=[sys.executable,'-B',str(ROOT/'scripts/cal_schedule.py'),'--database',str(self.db),'--local-root',str(self.root)]
        for args,status in [(['doctor'],'ready'),(['read','--start','2099-01-01','--end','2099-01-03'],'ok'),(['lookup','--request-id','absent'],'not_found')]:
            result=subprocess.run(command+args,capture_output=True,text=True)
            self.assertEqual(json.loads(result.stdout)['status'],status)
        request=base64.b64encode(json.dumps(self.create('todo')).encode()).decode()
        result=subprocess.run(command+['apply','--request-base64',request],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'committed')

    def test_screen_and_chat_share_receipt_conflicts_and_delivery(self):
        from unittest.mock import Mock
        self.cal.sync_google = Mock(return_value=dict(status='unreflected', reason='synthetic'))
        for kind in ('event', 'todo'):
            request = self.create(kind, 'screen-'+kind)
            def screen(req):
                return self.cal.change_schedule(req['kind'], req['action'], req.get('id'),
                    req.get('values', {}), req.get('expected_revision'), req['request_id'])
            created = screen(request)
            self.assertEqual(self.cal.apply_schedule_request(request)['receipt'], created['receipt'])
            self.assertEqual(screen(request)['receipt'], created['receipt'])
            with self.assertRaisesRegex(ConflictError, 'request_id_payload_conflict'):
                screen(dict(request, values=dict(notes='other')))
            edit = dict(request, request_id='edit-'+kind, id=created['id'],
                        expected_revision=created['receipt']['revision'], values=dict(notes='Chat'))
            updated = self.cal.apply_schedule_request(edit)
            with self.assertRaisesRegex(ConflictError, 'revision_conflict'):
                screen(dict(edit, request_id='stale-'+kind, values=dict(notes='Screen')))
            self.assertEqual(screen(edit)['receipt'], updated['receipt'])
            delete = dict(edit, request_id='delete-'+kind, action='delete', values={},
                          expected_revision=updated['receipt']['revision'])
            lost_response = screen(delete)
            self.assertEqual(self.cal.lookup_schedule_request(delete['request_id'])['receipt'], lost_response['receipt'])
            self.assertEqual(screen(delete)['receipt'], lost_response['receipt'])
            # Old receipt remains distinct from current state, including deletion.
            self.assertEqual(screen(request)['receipt'], created['receipt'])
            with self.assertRaises(NotFoundError): self.cal.get_schedule_item(kind, created['id'])
        self.assertEqual(self.cal.sync_google.call_count, 6)
        with self.assertRaises(ValidationError):
            self.cal.change_schedule('event', 'save', values={'title':''}, request_id='invalid-screen')
        self.assertEqual(self.cal.lookup_schedule_request('invalid-screen')['status'], 'not_found')
        self.assertEqual(self.cal.sync_google.call_count, 6)

    def test_screen_requires_revision_for_existing_item(self):
        receipt = self.cal.apply_schedule_request(self.create())['receipt']
        with self.assertRaisesRegex(ValidationError, 'expected_revision_required'):
            self.cal.change_schedule('event', 'save', receipt['entity_id'], {'notes':'unsafe'}, request_id='unsafe')
        self.assertEqual(self.cal.lookup_schedule_request('unsafe')['status'], 'not_found')
