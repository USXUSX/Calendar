import copy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from scripts.init_calendar_db import initialize
from scripts.migrate_castles import migrate as castles_migrate
from scripts.migrate_places import migrate


class PlacesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.db = self.root/'cal.sqlite3'; initialize(self.db)
        rows = [dict(id=i,n=f'合成城{i}',p='合成県',city='合成市',x=130+i/100,y=35,visitDate='2025/1/2' if i<=68 else None) for i in range(1,101)]
        source=self.root/'castles.js'; source.write_text('const castles='+json.dumps(rows));castles_migrate(self.db,source)
        self.cal = CalendarDomain(self.db,self.root)
        self.samples = json.loads(Path('Samples/sightseeing-phase2.json').read_text())

    def apply(self, identity, values, rid='new'):
        old = next((x for x in self.cal.list_places() if x['id']==identity),None)
        req=dict(request_id=rid,id=identity,expected_revision=old['revision'] if old else None,values=values)
        return req,self.cal.apply_place_request(req)

    def test_official_cli_replay_conflict_and_legacy_visits(self):
        before=self.cal.list_castles()
        values=copy.deepcopy(self.samples[5]['values'])
        req,result=self.apply(1001,values)
        self.assertEqual(result['status'],'committed')
        self.assertEqual(self.cal.apply_place_request(req)['receipt'],result['receipt'])
        self.assertEqual(self.cal.lookup_place_request('new')['receipt'],result['receipt'])
        with self.assertRaises(ConflictError):self.cal.apply_place_request(dict(req,values={'summary':'別内容'}))
        with self.assertRaises(ConflictError):self.cal.apply_place_request(dict(req,request_id='stale'))
        duplicate=copy.deepcopy(values)
        with self.assertRaisesRegex(ConflictError,'duplicate'):
            self.apply(1002,duplicate,'duplicate')
        duplicate['name']='別名';duplicate['aliases']=['三春滝桜'];duplicate['longitude']+=.001
        with self.assertRaisesRegex(ConflictError,'duplicate'):
            self.apply(1002,duplicate,'alias-duplicate')
        _,saved=self.apply(1001,dict(visited=True,visit_date='2026-10-21',comment='合成訪問'),'visit')
        self.assertTrue(saved['receipt']['item']['visited'])
        self.assertEqual(self.cal.list_castles(),before)
        castle=self.cal.get_place(4); content=copy.deepcopy(self.samples[0]['values'])
        content.update({k:castle[k] for k in ('name','prefecture','city','longitude','latitude')})
        self.apply(4,content,'castle-content')
        self.assertEqual(self.cal.list_castles(),before)
        common=self.cal.get_place(4)
        self.cal.apply_castle_request(dict(request_id='legacy',id=4,expected_revision=before[3]['revision'],values={'comment':'既存画面'}))
        with self.assertRaises(ConflictError): self.cal.apply_place_request(dict(request_id='stale-common',id=4,expected_revision=common['revision'],values={'comment':'古い値'}))
        self.assertEqual(self.cal.get_place(4)['comment'],'既存画面')
        self.apply(4,{'comment':'共通画面'},'common-visit')
        self.assertEqual(self.cal.get_castle(4)['comment'],'共通画面')
        with self.assertRaises(ValidationError):self.apply(4,{'name':'マスター変更'},'immutable')
        migrate(self.db);self.assertEqual(len(self.cal.list_places()),101)
        command=[sys.executable,'-B','scripts/cal_places.py','--database',str(self.db),'--local-root',str(self.root)]
        current=self.cal.get_place(1001)
        cli=dict(request_id='cli',id=1001,expected_revision=current['revision'],values={'description':'CLIで紹介を更新'})
        p=subprocess.run(command+['apply'],input=json.dumps(cli),capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=subprocess.run(command+['lookup','--request-id','cli'],capture_output=True,text=True)
        self.assertEqual(json.loads(p.stdout)['receipt']['item']['description'],'CLIで紹介を更新')
        p=subprocess.run(command+['apply'],input=json.dumps(dict(cli,request_id='stale-cli')),capture_output=True,text=True)
        self.assertEqual(p.returncode,3)

    def test_seed_contract_and_rejected_content_is_atomic(self):
        before=self.cal.list_castles()
        for r in self.samples:
            values=copy.deepcopy(r['values'])
            if r['id']<=100:
                current=self.cal.get_place(r['id']);values.update({k:current[k] for k in ('name','prefecture','city','longitude','latitude')})
            self.apply(r['id'],values,'seed-'+str(r['id']))
        items=self.cal.list_places();self.assertEqual(len(items),108)
        self.assertEqual([sum(k in x['categories'] for x in items) for k in ['castle','sakura','autumn']],[100,5,5])
        self.assertEqual(self.cal.list_castles(),before)
        self.assertEqual(sum(x['visited'] for x in self.cal.list_castles()),68)
        self.assertEqual([x['id'] for x in items if '弘前公園' in x['aliases']],[4])
        for change in ({'latitude':float('inf')},{'image':{'reusable':True}},{'related_ids':[99999]},{'tags':[{'label':'架空の称号','source_url':'javascript:bad'}]},{'seasons':[{'category':'sakura','typical':'4月','source_url':'https://example.com','checked_at':'invalid','annual':[]}]}):
            with self.assertRaises((ValidationError,ValueError)):
                self.apply(1001,change,'bad')
            self.assertEqual(self.cal.get_place(1001)['summary'],self.samples[5]['values']['summary'])
        self.assertEqual(self.cal.lookup_place_request('bad')['status'],'not_found')
        for r in self.samples:
            for s in r['values']['seasons']:
                self.assertTrue(s['typical']);self.assertTrue(s['source_url'])
                self.assertTrue(all(a['year'] in (2026,2027) for a in s['annual']))
            if r['values']['image']:
                i=r['values']['image'];self.assertTrue(i['credit']);self.assertTrue(i['license_url']);self.assertTrue(i['reusable'])


if __name__=='__main__':unittest.main()
