"""Travel preparation Todo contracts; no real data."""
from datetime import date
import sqlite3
import unittest
from test_travel import TravelTest
from Sources.calendar_domain import ConflictError, ValidationError
from scripts.migrate_travel_todos import migrate

class TravelTodoTest(unittest.TestCase):
    setUp=TravelTest.setUp
    create=TravelTest.create
    def test_undated_deadline_url_complete_and_receipt(self):
        tid=self.create()['id']
        payload=dict(request_id='prep-create',kind='todo',action='save',values=dict(label='宿を決める',trip_id=tid,notes='条件',related_url='https://example.com/booking'))
        first=self.cal.apply_schedule_request(payload)
        self.assertEqual(self.cal.apply_schedule_request(payload)['resolution'],'replayed')
        item=first['receipt']['item'];identity=item['id']
        self.assertIsNone(item['due_date'])
        self.assertEqual(self.cal.get_travel(tid)['items'][0]['related_url'],'https://example.com/booking')
        self.assertEqual(self.cal.list_travel()[0]['pending_todo_count'],1)
        self.assertEqual(self.cal.read_schedule('2027-01-01','2027-12-31')['items'],[])
        revision=self.cal.get_schedule_item('todo',identity)['revision']
        self.cal.change_schedule('todo','save',identity,dict(due_date='2027-02-01',due_time='10:00'),revision)
        with self.assertRaises(ConflictError):
            self.cal.change_schedule('todo','save',identity,dict(label='古い入力'),revision)
        dated=self.cal.read_schedule('2027-02-01','2027-02-01')['items']
        self.assertEqual([x['id'] for x in dated],[identity])
        self.assertEqual(dated[0]['related_url'],'https://example.com/booking')
        revision=self.cal.get_schedule_item('todo',identity)['revision']
        self.cal.change_schedule('todo','complete',identity,dict(completed=True),revision)
        self.assertEqual(self.cal.list_travel()[0]['pending_todo_count'],0)
        self.assertEqual(len(self.cal.get_travel(tid)['items']),1)
        revision=self.cal.get_schedule_item('todo',identity)['revision']
        self.cal.change_schedule('todo','complete',identity,dict(completed=False),revision)
        self.assertEqual(self.cal.list_travel()[0]['pending_todo_count'],1)
        revision=self.cal.get_schedule_item('todo',identity)['revision']
        self.cal.change_schedule('todo','save',identity,dict(due_date=None,due_time=None),revision)
        self.assertFalse(self.cal.read_schedule('2027-02-01','2027-02-01')['items'])
        self.assertEqual(self.cal.get_schedule_item('todo',identity)['item']['notes'],'条件')
        for url in ['javascript:alert(1)','https://u:p@example.com','https://example.com/ bad']:
            with self.assertRaises(ValidationError):
                self.cal.change_schedule('todo','save',values=dict(label='不正',trip_id=tid,related_url=url))
        with self.assertRaises(ValidationError):
            self.cal.change_schedule('todo','save',values=dict(label='通常タスクは日付必要'))
        with self.assertRaises(ValidationError):
            self.cal.change_schedule('todo','save',values=dict(label='時刻のみ',trip_id=tid,due_time='10:00'))

    def test_additive_migration_and_recurring_count(self):
        tid=self.create()['id']
        with sqlite3.connect(self.db) as c:
            c.execute('ALTER TABLE todos DROP COLUMN related_url')
            before=c.execute('SELECT * FROM todos').fetchall()
        migrate(self.db);migrate(self.db)
        with sqlite3.connect(self.db) as c:self.assertEqual(c.execute('SELECT * FROM todos').fetchall(),before)
        today=date.today().isoformat()
        self.cal.apply_recurrence_request(dict(request_id='prep-series',kind='todo',action='save',scope='series',recurrence=dict(frequency='daily',start=today,until=today),values=dict(label='定期',trip_id=tid,due_date=today,related_url='https://example.com/')))
        recurring=self.cal.get_travel(tid)['items'][0]
        self.assertEqual(self.cal.list_travel()[0]['pending_todo_count'],1)
        self.cal.change_schedule('todo','complete',recurring['id'],dict(completed=True),recurring['revision'])
        self.assertEqual(self.cal.list_travel()[0]['pending_todo_count'],0)
        self.assertEqual(self.cal.get_travel(tid)['items'][0]['related_url'],'https://example.com/')
        latest=self.cal.get_travel(tid)['items'][0]
        with self.assertRaises(ValidationError):
            self.cal.change_schedule('todo','save',latest['id'],dict(due_date=None),latest['revision'])
