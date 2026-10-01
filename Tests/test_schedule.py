import json
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from Sources.calendar_domain import CalendarDomain, ValidationError, NotFoundError
from scripts.init_calendar_db import initialize
from scripts.migrate_schedule import migrate

ROOT = Path(__file__).resolve().parents[1]

class ScheduleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.db = self.root/'cal.sqlite3'
        initialize(self.db)
        (self.root/'trips').mkdir()
        shutil.copy(ROOT/'Samples/synthetic-trip.json',self.root/'trips/trip-setouchi-2027.json')
        self.cal = CalendarDomain(self.db,self.root,chat_root=self.root/'chat')
        self.cal.register_trip('trip-setouchi-2027')

    def test_existing_database_additive_migration_is_repeatable(self):
        db = self.root/'old.sqlite3'
        with sqlite3.connect(db) as c:
            c.executescript((ROOT/'Schemas/calendar-v3.sql').read_text())
        old = CalendarDomain(db,self.root,chat_root=self.root/'old-chat')
        old.create_event('existing',title='既存予定',start_date='2027-01-01')
        old.create_todo('existing-todo',label='既存タスク',due_date='2027-01-01')
        before = old.get_event('existing'); before_todo = old.get_todo('existing-todo')
        migrate(db);migrate(db)
        self.assertEqual(old.get_event('existing'),before|{'trip_id':None})
        self.assertEqual(old.get_todo('existing-todo'),before_todo|{'notes':None})
        with self.assertRaises(sqlite3.OperationalError):migrate(self.root/'missing.sqlite3')
        self.assertFalse((self.root/'missing.sqlite3').exists())

    def test_period_and_lifecycle_preserve_trip_and_hide_completed(self):
        trip = self.cal.list_trips()[0]; start=trip['dateRange']['start'];end=trip['dateRange']['end']
        original=(self.root/'trips/trip-setouchi-2027.json').read_bytes()
        event=self.cal.change_schedule('event','save',values=dict(title='予約',start_date=start,end_date=end,trip_id=trip['trip_id'],notes='メモ'))
        todo=self.cal.change_schedule('todo','save',values=dict(label='準備',due_date=start,notes='持参品'))
        read=self.cal.read_schedule(start,end)
        self.assertEqual([x['kind'] for x in read['items']].count('trip'),1)
        self.assertEqual(len(read['items']),3)
        self.assertEqual(next(x for x in read['items'] if x['kind']=='event')['trip_id'],trip['trip_id'])
        self.cal.change_schedule('event','save',event['id'],dict(start_time='09:00',end_time='10:00'))
        self.assertEqual(self.cal.get_event(event['id'])['notes'],'メモ')
        self.cal.change_schedule('todo','complete',todo['id'],{'completed':True})
        self.assertEqual(len(self.cal.read_schedule(start,end)['items']),2)
        self.assertEqual(self.cal.get_todo(todo['id'])['notes'],'持参品')
        self.cal.change_schedule('event','delete',event['id'],{})
        self.cal.change_schedule('todo','delete',todo['id'],{})
        self.assertEqual(len(self.cal.read_schedule(start,end)['items']),1)
        self.assertEqual((self.root/'trips/trip-setouchi-2027.json').read_bytes(),original)
        self.assertFalse((self.root/'chat').exists())

    def test_invalid_partial_edit_does_not_change_current_record(self):
        item=self.cal.change_schedule('event','save',values=dict(title='予定',start_date='2027-01-02',start_time='10:00'))
        same_day=self.cal.change_schedule('event','save',item['id'],{'end_time':'11:00'})
        self.assertEqual(same_day['end_date'],'2027-01-02')
        item=same_day
        for changes in ({'end_date':'2027-01-01'},{'end_time':'09:00'},{'start_time':'25:00'},{'trip_id':'missing'},{'start_date':'2027-02-30'},{'title':''}):
            with self.assertRaises(ValidationError):self.cal.change_schedule('event','save',item['id'],changes)
            self.assertEqual(self.cal.get_event(item['id']),item)
        with self.assertRaises(NotFoundError):self.cal.change_schedule('event','save','missing',{'title':'new'})
        with self.assertRaises(ValidationError):self.cal.change_schedule('todo','save',values={'label':'日付なし'})
        self.assertEqual(len(self.cal.read_schedule('2027-01-01','2027-01-02')['items']),1)
