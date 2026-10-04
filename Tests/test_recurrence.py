import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize
from scripts.migrate_recurrence import migrate

ROOT=Path(__file__).resolve().parents[1]
class RecurrenceTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'cal.sqlite3';initialize(self.db)
        self.cal=CalendarDomain(self.db,self.root);self.serial=0
    def apply(self,request):
        self.serial+=1
        return self.cal.apply_recurrence_request(dict(request_id='r'+str(self.serial),**request))['receipt']
    def create(self,kind='event',**r):
        start=r.get('start','2026-01-01');r.setdefault('start',start);r.setdefault('frequency','daily')
        values=dict(title='synthetic',start_date=start) if kind=='event' else dict(label='synthetic',due_date=start)
        return self.apply(dict(kind=kind,action='save',scope='series',recurrence=r,values=values))
    def read(self,start,end):return self.cal.read_schedule(start,end,True,False)['items']
    def change(self,item,action='save',scope='this',**kwargs):
        return self.apply(dict(kind=item['kind'],action=action,scope=scope,id=item['id'],expected_revision=item['revision'],**kwargs))
    def test_calendar_rules_and_boundaries(self):
        self.create(frequency='month_end',start='2023-02-01',until='2024-03-31')
        self.assertEqual([x['start_date'] for x in self.read('2023-02-01','2023-03-31')],['2023-02-28','2023-03-31'])
        self.assertEqual([x['start_date'] for x in self.read('2024-02-01','2024-04-01')],['2024-02-29','2024-03-31'])
        self.create(frequency='monthly',month_day=31,start='2025-01-01',until='2025-05-31')
        self.assertEqual([x['start_date'] for x in self.read('2025-01-01','2025-06-01')],['2025-01-31','2025-03-31','2025-05-31'])
        yearly=self.create(frequency='yearly',start='2024-11-30',until='2027-12-31')
        self.assertEqual([x['start_date'] for x in self.read('2024-01-01','2027-12-31') if x['series_id']==yearly['series_id']],['2024-11-30','2025-11-30','2026-11-30','2027-11-30'])
        leap=self.create(frequency='yearly',start='2024-02-29',until='2028-03-01')
        self.assertEqual([x['start_date'] for x in self.read('2024-01-01','2028-03-01') if x['series_id']==leap['series_id']],['2024-02-29','2028-02-29'])
        self.create(frequency='weekly',weekdays=[1,3],start='2026-01-06',until='2026-01-14')
        self.assertEqual([x['start_date'] for x in self.read('2026-01-01','2026-01-31')],['2026-01-07','2026-01-12','2026-01-14'])
        self.create(start='2099-01-01')
        self.assertEqual(len(self.read('2099-05-01','2099-05-31')),31)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],0)
    def test_single_move_delete_and_overlapping_reads(self):
        self.create(until='2026-01-05')
        item=self.read('2026-01-02','2026-01-02')[0]
        self.change(item,values={'start_date':'2026-02-02'})
        self.assertFalse(self.read('2026-01-02','2026-01-02'))
        moved=self.read('2026-02-02','2026-02-02')[0];self.assertEqual(moved['id'],item['id'])
        self.change(moved,action='delete')
        self.assertFalse(self.read('2026-02-02','2026-02-02'))
        self.assertFalse(self.read('2026-01-02','2026-01-02'))
        a=self.read('2026-01-01','2026-01-04');b=self.read('2026-01-03','2026-01-05')
        self.assertEqual([x['id'] for x in a if x['start_date']=='2026-01-03'],[x['id'] for x in b if x['start_date']=='2026-01-03'])
    def test_following_preserves_past_and_explicit_exceptions(self):
        self.create(kind='todo',until='2026-01-10')
        self.change(self.read('2026-01-01','2026-01-01')[0],action='complete',values={'completed':True})
        self.change(self.read('2026-01-02','2026-01-02')[0],values={'label':'past exception'})
        self.change(self.read('2026-01-07','2026-01-07')[0],action='delete')
        past=self.read('2026-01-01','2026-01-02')
        self.change(self.read('2026-01-03','2026-01-03')[0],scope='following',values={'label':'new'})
        for a,b in zip(past,self.read('2026-01-01','2026-01-02')):
            self.assertEqual(a|{'revision':None},b|{'revision':None})
        self.assertEqual(self.read('2026-01-03','2026-01-03')[0]['title'],'new')
        self.assertFalse(self.read('2026-01-07','2026-01-07'))
        self.change(self.read('2026-01-05','2026-01-05')[0],scope='following',action='delete')
        self.assertEqual(len(self.read('2026-01-01','2026-02-01')),4)
        self.assertTrue(self.read('2026-01-01','2026-01-01')[0]['completed_at'])
    def test_completion_stale_and_receipts(self):
        self.create(kind='todo',until='2026-01-03')
        items=self.read('2026-01-01','2026-01-03')
        request=dict(request_id='complete',kind='todo',action='complete',scope='this',id=items[0]['id'],expected_revision=items[0]['revision'],values={'completed':True})
        result=self.cal.apply_recurrence_request(request)
        self.assertEqual(self.cal.apply_recurrence_request(request)['receipt'],result['receipt'])
        self.assertEqual(self.cal.lookup_chat_request('complete')['receipt'],result['receipt'])
        with self.assertRaises(ConflictError):self.change(items[1],values={'label':'stale'})
        with self.assertRaises(ConflictError):self.cal.apply_recurrence_request(request|{'values':{'completed':False}})
        self.assertEqual(len(self.cal.read_schedule('2026-01-01','2026-01-03',False,False)['items']),2)
        fresh=self.read('2026-01-01','2026-01-03');self.assertFalse(fresh[1]['completed_at'])
        self.change(fresh[0],action='complete',values={'completed':False})
        self.assertEqual(len(self.cal.read_schedule('2026-01-01','2026-01-03',False,False)['items']),3)
    def test_multiday_and_following_new_rule(self):
        request=dict(kind='event',action='save',scope='series',recurrence=dict(frequency='weekly',weekdays=[1],start='2026-01-05'),values=dict(title='span',start_date='2026-01-05',start_time='20:00',end_date='2026-01-07',end_time='09:00'))
        self.apply(request)
        item=self.read('2026-01-13','2026-01-13')[0]
        self.assertEqual((item['start_date'],item['end_date']),('2026-01-12','2026-01-14'))
        self.change(item,scope='following',recurrence=dict(frequency='weekly',weekdays=[3],start='2026-01-14',until='2026-01-28'),values={})
        self.assertEqual([(x['start_date'],x['end_date']) for x in self.read('2026-01-01','2026-02-01')],[('2026-01-05','2026-01-07'),('2026-01-14','2026-01-16'),('2026-01-21','2026-01-23'),('2026-01-28','2026-01-30')])
    def test_atomic_parallel_and_migration(self):
        request=dict(request_id='parallel',kind='todo',action='save',scope='series',recurrence=dict(frequency='daily',start='2026-01-01'),values=dict(label='synthetic',due_date='2026-01-01'))
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.cal.apply_recurrence_request(request),range(2)))
        self.assertEqual({r['resolution'] for r in results},{'new','replayed'})
        with sqlite3.connect(self.db) as c:
            before=c.execute('SELECT * FROM schedule_series').fetchall()
            c.execute("CREATE TRIGGER reject_receipt BEFORE INSERT ON schedule_receipts BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertRaises(ValidationError):self.create()
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT * FROM schedule_series').fetchall(),before)
        migrate(self.db);migrate(self.db)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT * FROM schedule_series').fetchall(),before)
        with self.assertRaises(sqlite3.Error):migrate(self.root/'missing.sqlite3')
    def test_cli_and_explicit_additive_migration(self):
        single=self.cal.change_schedule('event','save',values={'title':'single synthetic','start_date':'2026-01-01'})
        with sqlite3.connect(self.db) as c:
            before=c.execute('SELECT * FROM events').fetchall()
            c.execute('DROP TABLE schedule_series')
        def cli(*args,payload=None):
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/cal_schedule.py'),'--database',str(self.db),'--local-root',str(self.root),*args],input=json.dumps(payload) if payload is not None else None,text=True,capture_output=True)
            return result.returncode,json.loads(result.stdout)
        self.assertEqual(cli('doctor'),(2,{'status':'rejected','reason':'recurrence_migration_required'}))
        migrate(self.db);migrate(self.db)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT * FROM events').fetchall(),before)
        self.assertEqual(cli('doctor')[1]['status'],'ready')
        request=dict(request_id='cli-series',kind='event',action='save',scope='series',recurrence=dict(frequency='daily',start='2026-01-01',until='2026-01-02'),values=dict(title='rec synthetic',start_date='2026-01-01'))
        code,result=cli('apply',payload=request);self.assertEqual(code,0)
        self.assertEqual(cli('lookup','--request-id','cli-series')[1]['receipt'],result['receipt'])
        self.assertEqual(cli('apply',payload=request)[1]['resolution'],'replayed')
        self.assertEqual(len(cli('series')[1]['series']),1)
        sid=result['receipt']['series_id']
        self.assertEqual(cli('series','--id',sid)[1]['series']['revision'],result['receipt']['revision'])
        occurrence=cli('get','--kind','event','--id','rec:'+sid+':2026-01-01')[1]['item']
        # Frame-facing write has no series scope: only the selected occurrence changes.
        self.cal.change_schedule('event','save',occurrence['id'],{'title':'one'},expected_revision=occurrence['revision'])
        self.assertEqual(self.cal.get_occurrence('rec:'+sid+':2026-01-02')['title'],'rec synthetic')
        self.assertEqual(len(cli('read','--start','2026-01-01','--end','2026-01-02')[1]['items']),3)
    def test_invalid_rules_and_scope_are_atomic(self):
        valid=dict(request_id='invalid',kind='todo',action='save',scope='series',recurrence=dict(frequency='daily',start='2026-01-01'),values=dict(label='synthetic',due_date='2026-01-01'))
        for bad_rule in [dict(frequency='weekly',start='2026-01-01',weekdays=[1,1]),dict(frequency='monthly',start='2026-01-01',month_day=32),dict(frequency='daily',start='2026-01-01',until='2025-01-01')]:
            with self.assertRaises(ValidationError):self.cal.apply_recurrence_request(valid|{'recurrence':bad_rule})
        with self.assertRaises(ValidationError):self.cal.apply_recurrence_request(valid|{'values':[]})
        self.assertEqual(self.cal.lookup_chat_request('invalid')['status'],'not_found')
        self.create(kind='todo',until='2026-01-02')
        item=self.read('2026-01-01','2026-01-01')[0]
        with self.assertRaises(ValidationError):self.change(item,scope='following',action='complete',values={'completed':True})
        with self.assertRaises(ValidationError):self.change(item,recurrence={'frequency':'daily','start':'2026-01-01'},values={})
        self.assertEqual(self.cal.get_occurrence(item['id'])['revision'],item['revision'])
