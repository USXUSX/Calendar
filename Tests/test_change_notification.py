import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from Sources.calendar_domain import CalendarDomain
from scripts.init_calendar_db import initialize

class ChangeNotificationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.db=self.root/'cal.sqlite3';initialize(self.db)
        self.cal=CalendarDomain(self.db,self.root);self.cal.sync_google=lambda:dict(status='unreflected')
        (self.root/'settings').mkdir()
        self.counter=self.root/'notices'
        script=self.root/'notify.py';script.write_text('from pathlib import Path\nimport json,sys\np=Path(sys.argv[1])\np.write_text(p.read_text()+"x" if p.exists() else "x")\nprint(json.dumps({"accepted":True}))\n')
        self.config=self.root/'settings/change-notifier.json'
        self.config.write_text(json.dumps(dict(database=str(self.db),command=[sys.executable,str(script),str(self.counter)])))

    def test_commit_rollback_replay_and_delivery_failure(self):
        request=dict(request_id='create',kind='event',action='save',values=dict(title='合成',start_date='2099-01-01'))
        first=self.cal.apply_schedule_request(request)
        self.assertEqual(self.counter.read_text(),'x')
        self.cal.apply_schedule_request(request);self.assertEqual(self.counter.read_text(),'x')
        with self.assertRaises(Exception):
            self.cal.apply_schedule_request(dict(request,request_id='bad',values={}))
        self.assertEqual(self.counter.read_text(),'x')
        self.config.write_text(json.dumps(dict(database=str(self.db),command=['/does/not/exist'])))
        saved=self.cal.change_schedule('event','save',values=dict(title='保存は成功',start_date='2099-01-02'))
        self.assertEqual(saved['status'],'committed')
        state=json.loads((self.root/'settings/change-notification-state.json').read_text());self.assertTrue(state['committed']);self.assertEqual(state['status'],'failed')
        self.assertEqual(self.cal.lookup_schedule_request('create')['receipt'],first['receipt'])

    def test_common_commit_covers_crud_travel_and_other_tables_do_not_notify(self):
        self.cal.create_event('old',title='旧CRUD',start_date='2099-01-01')
        self.cal.update_event('old',title='更新');self.cal.delete_event('old')
        with self.cal._command() as c:c.execute('UPDATE trips SET version=version+1')
        self.assertEqual(self.counter.read_text(),'xxx')
        self.cal.change_travel(dict(title='合成旅行',date_status='confirmed',start_date='2099-01-01',end_date='2099-01-03'))
        self.assertEqual(self.counter.read_text(),'xxxx')
        before=self.counter.read_text()
        with self.cal._command() as c:c.execute('CREATE TABLE IF NOT EXISTS google_test (x TEXT)');c.execute("INSERT INTO google_test VALUES ('state')")
        self.assertEqual(self.counter.read_text(),before)
        self.cal.apply_recurrence_request(dict(request_id='series',kind='event',action='save',scope='series',recurrence=dict(frequency='daily',start='2099-01-01'),values=dict(title='定期',start_date='2099-01-01')))
        self.assertEqual(self.counter.read_text(),before+'x')
        self.cal.create_todo('legacy-todo',label='旧Todo',due_date='2099-01-02')
        self.assertEqual(self.counter.read_text(),before+'xx')
