import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime
from Sources.calendar_domain import CalendarDomain
from Sources.calendar_domain.google_calendar import GoogleError, event_body
from scripts.init_calendar_db import initialize
from scripts.migrate_google_calendar import migrate


class FakeGoogle:
    config={'calendar_id':'synthetic-cal'}
    def __init__(self):self.events={};self.fail=False;self.lose=False;self.calls=[]
    def request(self,method,path,body=None):
        self.calls.append((method,path));identity=path.rsplit('/',1)[1]
        if self.fail:raise GoogleError('communication_failed')
        if method=='GET':
            if identity not in self.events:raise GoogleError('http_404')
            return copy.deepcopy(self.events[identity])
        if method=='POST':
            identity=body['id']
            if identity in self.events:raise GoogleError('http_409')
            self.events[identity]=copy.deepcopy(body)
            if self.lose:self.lose=False;raise GoogleError('communication_failed')
        elif method=='PUT':self.events[identity]=copy.deepcopy(body)
        elif method=='DELETE':del self.events[identity]
        return copy.deepcopy(body or {})


class GoogleTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'cal.sqlite3';initialize(self.db)
        self.cal=CalendarDomain(self.db,self.root);self.api=FakeGoogle();self.serial=0
        (self.root/'settings').mkdir();(self.root/'settings/google-token.json').write_text('{}');(self.root/'settings/google-calendar.json').write_text('{}')
        self.addCleanup(patch.stopall)
        patch('Sources.calendar_domain.google_calendar.today',return_value='2026-10-05').start()
        patch('Sources.calendar_domain.google_calendar.GoogleClient',return_value=self.api).start()
    def create(self,**values):return self.cal.change_schedule('event','save',values=dict(title='synthetic',start_date='2026-10-05',**values))
    def series(self,kind='event',**rule):
        self.serial+=1;rule.setdefault('start','2026-10-05');rule.setdefault('frequency','daily')
        values=dict(title='rec',start_date=rule['start']) if kind=='event' else dict(label='rec',due_date=rule['start'])
        return self.cal.apply_recurrence_request(dict(request_id='s'+str(self.serial),kind=kind,action='save',scope='series',recurrence=rule,values=values))['receipt']
    def change(self,item,**request):
        self.serial+=1
        return self.cal.apply_recurrence_request(dict(request_id='c'+str(self.serial),kind=item['kind'],id=item['id'],expected_revision=item['revision'],scope='this',action='save',**request))
    def test_save_failure_retry_response_loss_and_delete(self):
        self.api.fail=True;saved=self.create();self.assertEqual(saved['google']['status'],'unreflected')
        self.assertEqual(self.cal.get_event(saved['id'])['title'],'synthetic')
        self.api.fail=False;self.api.lose=True
        self.assertEqual(self.cal.sync_google()['status'],'unreflected');self.assertEqual(len(self.api.events),1)
        self.assertEqual(self.cal.sync_google()['status'],'synced');self.assertEqual(len(self.api.events),1)
        identity=next(iter(self.api.events));self.cal.change_schedule('event','save',saved['id'],{'title':'changed'})
        self.assertEqual(self.api.events[identity]['summary'],'changed')
        self.api.fail=True;self.cal.change_schedule('event','delete',saved['id'],{})
        self.assertEqual(self.cal.google_status()['pending'],1)
        self.api.fail=False;self.assertEqual(self.cal.sync_google()['status'],'synced');self.assertFalse(self.api.events)
        self.assertEqual(self.cal.sync_google()['status'],'synced')
    def test_scope_ownership_and_past_updates(self):
        self.cal.change_schedule('event','save',values=dict(title='past',start_date='2026-10-04'))
        self.assertFalse(self.api.events)
        saved=self.create();identity=next(iter(self.api.events))
        self.api.events['unrelated']={'summary':'synthetic'}
        with patch('Sources.calendar_domain.google_calendar.today',return_value='2026-11-01'):
            self.cal.change_schedule('event','save',saved['id'],{'title':'past changed'})
        self.assertEqual(self.api.events[identity]['summary'],'past changed')
        self.api.events[identity]['extendedProperties']={}
        result=self.cal.sync_google(reconcile=True);self.assertEqual(result['status'],'unreflected')
        self.assertEqual(result['reason'],'ownership_conflict');self.assertIn('unrelated',self.api.events)
    def test_tasks_marker_and_completion(self):
        item=self.cal.change_schedule('todo','save',values=dict(label='task',due_date='2026-10-05',due_time='12:00'))
        body=next(iter(self.api.events.values()));self.assertIn('終了不明',body['description'])
        a=datetime.fromisoformat(body['start']['dateTime']);b=datetime.fromisoformat(body['end']['dateTime']);self.assertEqual((b-a).seconds,60)
        self.cal.change_schedule('todo','complete',item['id'],dict(completed=True));self.assertTrue(next(iter(self.api.events.values()))['summary'].startswith('✓ '))
        self.cal.change_schedule('todo','complete',item['id'],dict(completed=False));self.assertFalse(next(iter(self.api.events.values()))['summary'].startswith('✓'))
    def test_recurring_rules_exceptions_following(self):
        for r in [dict(frequency='monthly',month_day=31),dict(frequency='month_end'),dict(frequency='yearly',start='2024-02-29'),dict(frequency='weekly',weekdays=[0,3])]:self.series(**r)
        lines=[b['recurrence'][0] for b in self.api.events.values()]
        self.assertTrue(any('BYMONTHDAY=-1' in s for s in lines));self.assertTrue(any('BYMONTH=2;BYMONTHDAY=29' in s for s in lines));self.assertTrue(any('BYDAY=SU,WE' in s for s in lines))
        receipt=self.series(kind='todo',until='2026-10-10');sid=receipt['series_id']
        item=next(i for i in self.cal.read_schedule('2026-10-06','2026-10-06',True,False)['items'] if i.get('series_id')==sid)
        self.change(item,values=dict(due_date='2026-10-07'))
        self.assertTrue(any('EXDATE;VALUE=DATE:20261006' in b.get('recurrence',[]) for b in self.api.events.values()))
        item=self.cal.get_occurrence(item['id']);self.serial+=1
        self.cal.apply_recurrence_request(dict(request_id='d'+str(self.serial),kind='todo',action='complete',scope='this',id=item['id'],expected_revision=item['revision'],values={'completed':True}))
        self.assertTrue(any(b['summary']=='✓ rec' for b in self.api.events.values()))
        item=self.cal.get_occurrence('rec:'+sid+':2026-10-08');self.serial+=1
        self.cal.apply_recurrence_request(dict(request_id='f'+str(self.serial),kind='todo',action='delete',scope='following',id=item['id'],expected_revision=item['revision'],values={}))
        self.assertTrue(any('UNTIL=20261007' in b.get('recurrence',[''])[0] for b in self.api.events.values()))
    def test_unauthenticated_save_and_receipt(self):
        (self.root/'settings/google-token.json').unlink()
        with patch('Sources.calendar_domain.google_calendar.GoogleClient',side_effect=GoogleError('authentication_required')):
            result=self.cal.apply_schedule_request(dict(request_id='receipt',kind='event',action='save',values=dict(title='saved',start_date='2026-10-05')))
        self.assertEqual(result['status'],'committed');self.assertEqual(result['google']['status'],'unreflected');self.assertNotIn('google',result['receipt'])
        self.assertEqual(self.cal.lookup_schedule_request('receipt')['receipt'],result['receipt'])
    def test_google_http_runs_after_cal_commit(self):
        original=self.api.request
        def request(method,path,body=None):
            with sqlite3.connect(self.db,timeout=0) as c:
                c.execute('BEGIN IMMEDIATE')
                if method=='POST':self.assertEqual(c.execute('SELECT count(*) FROM events').fetchone()[0],1)
            return original(method,path,body)
        self.api.request=request
        self.assertEqual(self.create()['google']['status'],'synced')
    def test_trip_changes_delete_and_following_save(self):
        trip=dict(trip_id='synthetic-trip',title='trip',dateRange={'start':'2026-10-04','end':'2026-10-06'})
        with patch.object(self.cal,'list_trips',return_value=[trip]):
            self.cal.sync_google();identity=next(iter(self.api.events))
            trip['dateRange']['end']='2026-10-08';self.cal.sync_google()
            self.assertEqual(self.api.events[identity]['end'],{'date':'2026-10-09'})
        with patch.object(self.cal,'list_trips',return_value=[]):self.cal.sync_google()
        self.assertFalse(self.api.events)
        receipt=self.series();item=self.cal.get_occurrence('rec:'+receipt['series_id']+':2026-10-08')
        self.cal.apply_recurrence_request(dict(request_id='following-save',kind='event',action='save',scope='following',id=item['id'],expected_revision=item['revision'],values={'title':'changed'},recurrence={'frequency':'weekly','start':'2026-10-08','weekdays':[4]}))
        self.assertEqual(len(self.api.events),2)
        self.assertTrue(any('UNTIL=20261007' in b['recurrence'][0] for b in self.api.events.values()))
        self.assertTrue(any('BYDAY=TH' in b['recurrence'][0] and b['summary']=='changed' for b in self.api.events.values()))

    def test_migration_preserves_existing_rows(self):
        saved=self.create()
        with sqlite3.connect(self.db) as c:
            before=c.execute('SELECT * FROM events').fetchall();c.execute('DROP TABLE google_events');c.execute('DROP TABLE google_calendar_meta')
        migrate(self.db);migrate(self.db)
        with sqlite3.connect(self.db) as c:self.assertEqual(before,c.execute('SELECT * FROM events').fetchall())
    def test_trip_period_payload(self):
        body=event_body(dict(title='trip',start_date='2026-10-04',end_date='2026-10-06',trip_id='synthetic-trip'),'trip:synthetic-trip')
        self.assertEqual(body['end'],{'date':'2026-10-07'});self.assertTrue(body['source']['url'].endswith('/synthetic-trip'))


if __name__=='__main__':unittest.main()
