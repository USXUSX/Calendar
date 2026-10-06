import copy
import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize
from scripts.migrate_travel import migrate
from test_google_calendar import FakeGoogle
ROOT=Path(__file__).resolve().parents[1]

class TravelTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'cal.sqlite3';initialize(self.db)
        self.cal=CalendarDomain(self.db,self.root)
    def create(self,**values):
        return self.cal.change_travel(dict(title='旅行',**values))['receipt']['item']
    def test_independent_travel_receipt_revision_and_connection(self):
        travel=self.create();tid=travel['id']
        self.assertFalse(self.cal.list_trips());self.assertEqual(len(self.cal.list_travel()),1)
        self.assertFalse(self.cal.read_schedule('2027-01-01','2027-12-31')['items'])
        changed=self.cal.change_travel(dict(start_date='2027-05-01',end_date='2027-05-03',date_status='tentative',transport='rail'),tid,travel['revision'])['receipt']['item']
        with self.assertRaises(ConflictError):self.cal.change_travel({'title':'古い'},tid,travel['revision'])
        trip=json.loads((ROOT/'Samples/synthetic-trip.json').read_text());trip['id']=tid
        request=dict(request_id='connect',kind='trip',action='create',trip=trip,coordinate_results={})
        with patch('Sources.calendar_domain.trip_chat.complete',side_effect=lambda candidate,*a,**k:(candidate,dict(filled=0,missing=0,existing=0))):
            saved=self.cal.apply_trip_request(request)
            self.assertEqual(self.cal.apply_trip_request(request)['resolution'],'replayed')
        self.assertEqual(len(self.cal.list_travel()),1);self.assertEqual(len(self.cal.list_trips()),1)
        detail=self.cal.get_trip_detail_view(tid,weather_by_day={})
        self.assertEqual(detail['title'],'旅行');self.assertEqual(detail['date_range'],changed['dateRange'])
        self.assertEqual(self.cal.lookup_chat_request('connect')['receipt'],saved['receipt'])
    def test_common_fields_links_and_related_items(self):
        travel=self.create();tid=travel['id'];url='https://mail.google.com/mail/u/0/#all/abc123'
        event=self.cal.apply_schedule_request(dict(request_id='mail',kind='event',action='save',values=dict(title='予約',start_date='2027-01-01',category='lodging',gmail_url=url,trip_id=tid)))['receipt']['item']
        todo=self.cal.change_schedule('todo','save',values=dict(label='準備',due_date='2027-01-01',category='pet',trip_id=tid))
        self.assertEqual(len(self.cal.get_travel(tid)['items']),2)
        self.cal.apply_schedule_request(dict(request_id='unlink',kind='event',action='save',id=event['id'],expected_revision=self.cal.get_schedule_item('event',event['id'])['revision'],values=dict(trip_id=None)))
        self.assertEqual(len(self.cal.get_travel(tid)['items']),1)
        self.cal.change_schedule('todo','save',todo['id'],{'notes':'保持'})
        self.assertEqual(self.cal.get_todo(todo['id'])['category'],'pet')
        for invalid in [{'category':'unknown'},{'gmail_url':'https://evil.example/'},{'trip_id':'missing'}]:
            with self.assertRaises(ValidationError): self.cal.change_schedule('todo','save',todo['id'],invalid)
    def test_migration_preserves_old_values_and_is_repeatable(self):
        old=self.root/'old.sqlite3'
        with sqlite3.connect(old) as c:c.executescript((ROOT/'Schemas/calendar-v3.sql').read_text())
        from scripts.migrate_schedule import migrate as schedule
        from scripts.migrate_schedule_receipts import migrate as receipts
        from scripts.migrate_recurrence import migrate as recurrence
        schedule(old);receipts(old);recurrence(old)
        cal=CalendarDomain(old,self.root);cal.create_event('old',title='保持',start_date='2027-01-01')
        before=cal.get_event('old');migrate(old,self.root);migrate(old,self.root)
        self.assertEqual(cal.get_event('old'),dict(before,category='general',gmail_url=None,google_calendar_id=None,google_event_id=None))
    def test_verified_google_match_preserves_external_event(self):
        api=FakeGoogle();api.events['mail-existing']={'summary':'外部保持'}
        (self.root/'settings').mkdir();(self.root/'settings/google-token.json').write_text('{"refresh_token":"synthetic"}');(self.root/'settings/google-calendar.json').write_text('{"calendar_id":"synthetic-cal"}')
        with patch('Sources.calendar_domain.google_calendar.GoogleClient',return_value=api),patch('Sources.calendar_domain.google_calendar.today',return_value='2027-01-01'):
            self.cal.change_schedule('event','save',values=dict(title='予約',start_date='2027-01-01',gmail_url='https://mail.google.com/mail/u/0/#all/abc',google_calendar_id='primary',google_event_id='mail-existing'))
            self.assertEqual(api.calls,[]);self.assertEqual(api.events,{'mail-existing':{'summary':'外部保持'}})
