import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize
from scripts.migrate_castles import migrate


class CastlesTest(unittest.TestCase):
    def test_migration_requests_and_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); db = root/'cal.sqlite3'; initialize(db)
            rows = [dict(id=i,n=f'合成城{i}',p='合成県',city='合成市',x=135+i/100,y=35,
                         visitDate='2025/1/2' if i<=68 else None) for i in range(1,101)]
            source = root/'source.js'; source.write_text('const castles='+json.dumps(rows)+'.map(c=>c);')
            with sqlite3.connect(db) as c:
                before = c.execute('SELECT * FROM trips').fetchall()
            self.assertEqual(migrate(db, source), dict(status='migrated',count=100,visited=68))
            cal = CalendarDomain(db, root)
            saved = cal.list_castles()
            self.assertEqual(len(saved), 100)
            self.assertEqual(sum(x['visited'] for x in saved), 68)
            for actual, original in zip(saved, rows):
                self.assertEqual([actual[k] for k in ('id','name','prefecture','city','longitude','latitude')],
                                 [original[k] for k in ('id','n','p','city','x','y')])
                self.assertEqual(actual['visit_date'], '2025-01-02' if original['visitDate'] else None)
            req = dict(request_id='test-1',id=69,expected_revision=cal.get_castle(69)['revision'],
                       values=dict(visited=True,visit_date='2026-10-21',comment='合成コメント'))
            committed = cal.apply_castle_request(req)
            self.assertEqual(committed['status'], 'committed')
            self.assertEqual(cal.apply_castle_request(req)['receipt'], committed['receipt'])
            self.assertEqual(cal.lookup_castle_request('test-1')['receipt'], committed['receipt'])
            with self.assertRaises(ConflictError): cal.apply_castle_request(dict(req,values={'comment':'別内容'}))
            with self.assertRaises(ConflictError): cal.apply_castle_request(dict(req,request_id='stale'))
            for index, values in enumerate([{'comment':'変更'}, {'visit_date':'2026-10-20'}, {'visited':False,'visit_date':None}]):
                request = dict(request_id=f'edit-{index}',id=69,expected_revision=cal.get_castle(69)['revision'],values=values)
                cal.apply_castle_request(request)
            current = cal.get_castle(69)
            self.assertFalse(current['visited']); self.assertIsNone(current['visit_date']); self.assertEqual(current['comment'],'変更')
            for values in ({'visited':1}, {'visit_date':'2026-02-30'}, {'latitude':0}, {'visited':False,'visit_date':'2026-10-21'}):
                with self.assertRaises(ValidationError):
                    cal.apply_castle_request(dict(request_id='bad',id=69,expected_revision=current['revision'],values=values))
            self.assertEqual(migrate(db,source)['status'],'unchanged')
            self.assertEqual(cal.get_castle(69),current)
            source.write_text('const castles='+json.dumps([{**r,'n':'別名'} if r['id']==1 else r for r in rows]))
            with self.assertRaises(ValueError): migrate(db,source)
            with sqlite3.connect(db) as c:
                self.assertEqual(c.execute('SELECT * FROM trips').fetchall(), before)
            command=[sys.executable,'-B','scripts/cal_castles.py','--database',str(db),'--local-root',str(root)]
            cli_req = dict(request_id='cli-test',id=70,expected_revision=cal.get_castle(70)['revision'],values={'comment':'CLI'})
            result=subprocess.run(command+['apply'],input=json.dumps(cli_req),text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            receipt=json.loads(result.stdout)['receipt']
            result=subprocess.run(command+['lookup','--request-id','cli-test'],text=True,capture_output=True)
            self.assertEqual(json.loads(result.stdout)['receipt'],receipt)
            result=subprocess.run(command+['get','--id','70'],text=True,capture_output=True)
            self.assertEqual(json.loads(result.stdout)['item']['comment'],'CLI')
            stale=dict(cli_req,request_id='cli-stale')
            result=subprocess.run(command+['apply'],input=json.dumps(stale),text=True,capture_output=True)
            self.assertEqual(result.returncode,3)


if __name__ == '__main__': unittest.main()
