import copy
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize
ROOT=Path(__file__).resolve().parents[1]

class TripChatTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'db.sqlite3';initialize(self.db)
        self.cal=CalendarDomain(self.db,self.root,chat_root=self.root/'chat')
        self.trip=json.loads((ROOT/'Samples/hokkaido-4days-candidate.json').read_text())
        self.tid=self.trip['id']
    def attempts(self,trip,existing_trip_id=None):
        plan=self.cal.prepare_import_locations(trip,existing_trip_id=existing_trip_id)
        return {p['place_id']:None for p in plan if p['location'] is None and not p.get('skip_search')}
    def create(self,identity='create'):
        trip=copy.deepcopy(self.trip)
        return dict(request_id=identity,kind='trip',action='create',trip=trip,coordinate_results=self.attempts(trip))
    def update(self,identity='update'):
        context=self.cal.get_trip_command_context(self.tid)
        trip=context['trip'];trip['title']='合成変更'
        return dict(request_id=identity,kind='trip',action='save',trip=trip,expected_revision=context['revision'],
                    handled_instruction_ids=[i['id'] for i in context['instructions']],coordinate_results=self.attempts(trip,self.tid))
    def test_lifecycle_preservation_conflicts_and_instructions(self):
        receipt=self.cal.apply_trip_request(self.create())['receipt']
        self.assertEqual(receipt['trip'],self.trip)
        self.assertFalse((self.root/'chat').exists())
        self.cal.add_chat_instruction('instruction',self.tid,'合成指示')
        request=self.update()
        self.cal.add_chat_instruction('new',self.tid,'後続指示')
        with self.assertRaisesRegex(ConflictError,'revision_conflict'):self.cal.apply_trip_request(request)
        request=self.update();result=self.cal.apply_trip_request(request)
        expected=copy.deepcopy(self.trip);expected['title']='合成変更'
        self.assertEqual(result['receipt']['trip'],expected)
        self.assertEqual(self.cal.get_trip_command_context(self.tid)['instructions'],[])
        self.assertEqual(self.cal.lookup_chat_request('update')['receipt'],result['receipt'])
        self.assertEqual(self.cal.apply_trip_request(request)['resolution'],'replayed')
        with self.assertRaisesRegex(ConflictError,'payload_conflict'):
            self.cal.apply_trip_request(request|{'trip':self.trip})
        with self.assertRaises(ConflictError):self.cal.apply_trip_request(self.create('another'))
    def test_parallel_replay(self):
        request=self.create()
        def apply(_):return CalendarDomain(self.db,self.root).apply_trip_request(request)
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(apply,range(2)))
        self.assertEqual({r['resolution'] for r in results},{'new','replayed'})
        self.assertEqual(results[0]['receipt'],results[1]['receipt'])
    def test_crashes_create_and_update(self):
        for action in ('create','save'):
            if action=='save':self.cal.apply_trip_request(self.create('initial'))
            for when in ('before','after','response'):
                request=self.create(action+when) if action=='create' else self.update(action+when)
                if action=='create':request['trip']['id']=self.tid+'-'+when
                script='''import json,os,sys
from Sources.calendar_domain import CalendarDomain
cal=CalendarDomain(sys.argv[1],sys.argv[2])
when=sys.argv[3]
if when=='before':
 original=cal._write_journal
 def stop(*args):
  original(*args);os._exit(81)
 cal._write_journal=stop
if when=='after':cal._after_candidate_replace=lambda:os._exit(82)
cal.apply_trip_request(json.loads(sys.argv[4]))
os._exit(83)
'''
                p=subprocess.run([sys.executable,'-B','-c',script,str(self.db),str(self.root),when,json.dumps(request)],cwd=ROOT,capture_output=True)
                self.assertEqual(p.returncode,{'before':81,'after':82,'response':83}[when],p.stderr)
                self.assertEqual(p.stdout,b'')
                lookup=self.cal.lookup_chat_request(request['request_id'])
                self.assertEqual(lookup['status'],'not_found' if when=='before' else 'committed')
                result=self.cal.apply_trip_request(request)
                self.assertEqual(result['resolution'],'new' if when=='before' else 'replayed')
                self.assertEqual(self.cal.get_trip_command_context(request['trip']['id'])['revision'],result['receipt']['revision'])
    def test_override_absorption_and_no_auto_candidate(self):
        self.cal.apply_trip_request(self.create())
        self.cal.set_direct_override('override',self.tid,self.tid,'/title','画面の変更')
        context=self.cal.get_trip_command_context(self.tid)
        self.assertEqual(context['trip']['title'],'画面の変更')
        request=self.update();request['trip']['summary']='Chat変更'
        self.cal.apply_trip_request(request)
        self.assertEqual(self.cal.get_effective_trip(self.tid),request['trip'])
        directory=self.root/'chat'/self.tid;directory.mkdir(parents=True)
        candidate=directory/'candidate.json';candidate.write_text('{"retained":true}')
        self.cal.load_trip_detail_view(self.tid)
        self.assertEqual(candidate.read_text(),'{"retained":true}')
        self.assertFalse((directory/'context.json').exists())

    def test_location_search_attempts_are_required(self):
        request=self.create('missing-attempts')
        request['coordinate_results']={}
        with self.assertRaisesRegex(ValidationError,'coordinate_results_incomplete'):
            self.cal.apply_trip_request(request)
        request=self.create('explicit-missing')
        result=self.cal.apply_trip_request(request)['receipt']
        self.assertGreater(result['coordinates']['missing'],0)

    def test_locations_and_file_only_target_protection(self):
        request=self.create()
        point=next(p for p in request['trip']['places'] if p['location'] is not None)
        pid=point['id'];point['location']=None
        plan=self.cal.prepare_import_locations(request['trip'])
        self.assertTrue(any(p['place_id']==pid for p in plan))
        request['coordinate_results']=self.attempts(request['trip'])
        request['coordinate_results'][pid]=dict(location=dict(latitude=43.0,longitude=141.0),googlePlaceId='synthetic-id')
        result=self.cal.apply_trip_request(request)['receipt']
        self.assertGreater(result['coordinates']['filled'],0)
        update=self.update()
        next(p for p in update['trip']['places'] if p['id']==pid)['location']=dict(latitude=1,longitude=2)
        saved=self.cal.apply_trip_request(update)['receipt']['trip']
        self.assertEqual(next(p for p in saved['places'] if p['id']==pid)['location'],dict(latitude=43.0,longitude=141.0))
        orphan=self.create('orphan');orphan['trip']['id']='orphan'
        path=self.cal._trip_path('orphan');path.write_text('keep this file')
        with self.assertRaises(ConflictError):self.cal.apply_trip_request(orphan)
        self.assertEqual(path.read_text(),'keep this file')

    def test_receipt_insert_failure_recovers_without_false_success(self):
        with sqlite3.connect(self.db) as c:
            c.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON schedule_receipts BEGIN SELECT RAISE(ABORT,'test'); END")
        from Sources.calendar_domain import ValidationError
        with self.assertRaises(ValidationError):self.cal.apply_trip_request(self.create())
        self.assertTrue(self.cal._journal_path(self.tid).exists())
        with sqlite3.connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM trips').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT count(*) FROM schedule_receipts').fetchone()[0],0)
            c.execute('DROP TRIGGER reject_receipt')
        result=self.cal.lookup_chat_request('create')
        self.assertEqual(result['status'],'committed')
        self.assertEqual(self.cal.get_trip_command_context(self.tid)['trip'],result['receipt']['trip'])

    def test_pending_trip_id_cannot_be_reused_by_schedule(self):
        from unittest.mock import patch
        with patch.object(self.cal,'_after_candidate_replace',side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):self.cal.apply_trip_request(self.create())
        with self.assertRaisesRegex(ConflictError,'payload_conflict'):
            self.cal.apply_schedule_request(dict(request_id='create',kind='event',action='save',values=dict(title='synthetic',start_date='2099-01-01')))
        self.assertEqual(self.cal.lookup_chat_request('create')['receipt']['kind'],'trip')
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],0)
