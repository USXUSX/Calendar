import copy
import json
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_trip_chat as fixture
from scripts.publish_trip_index import build_files, publish_files, publish, canonical


class ItemIndexTest(unittest.TestCase):
    attempts = fixture.TripChatTest.attempts
    create = fixture.TripChatTest.create
    update = fixture.TripChatTest.update

    def setUp(self):
        fixture.TripChatTest.setUp(self)
        self.launcher = patch('Sources.calendar_domain.trip_index.queue_publication')
        self.launcher.start()
        self.addCleanup(self.launcher.stop)
        self.cal.apply_trip_request(self.create())

    def settings(self):
        folder = self.root / 'settings'
        folder.mkdir(exist_ok=True)
        (folder / 'trip-index-publisher.json').write_text(json.dumps(
            dict(database=str(self.db), gh='/synthetic/gh')))
        return folder

    def trip_index(self, files):
        return files['item-index/by-trip/'+self.tid+'.json']

    def replace_trip(self, trip, identity):
        context = self.cal.get_trip_command_context(self.tid)
        return self.cal.apply_trip_request(dict(
            request_id=identity,kind='trip',action='save',trip=trip,expected_revision=context['revision'],
            handled_instruction_ids=[],coordinate_results=self.attempts(trip,self.tid)))

    def test_small_fields_and_date_trip_views_match(self):
        before = self.cal.get_trip_command_context(self.tid)
        files = build_files(self.cal)
        index = files['trip-index.json']
        self.assertEqual(set(index), {'schema','travels'})
        self.assertEqual(index['schema'], 'cal-trip-index-v1')
        self.assertEqual(set(index['travels'][0]), {'id','title','dateRange','has_itinerary'})
        compact = self.trip_index(files)
        self.assertEqual(set(compact), {'schema','trip_id','days'})
        self.assertEqual(compact['schema'], 'cal-item-index-v1')
        for day in compact['days']:
            dated = files['item-index/by-date/'+day['date']+'.json']
            items = next(t['items'] for t in dated['trips'] if t['trip_id']==self.tid)
            self.assertEqual(items,day['items'])
            for item in items:
                self.assertEqual(set(item),{'source_type','source_item_id','start','title'})
        entries = [i for d in compact['days'] for i in d['items']]
        self.assertTrue(any(i['source_type']=='transport' for i in entries))
        self.assertTrue(any(i['start'] is None for i in entries))
        self.assertEqual(self.cal.get_trip_command_context(self.tid),before)
        self.cal.add_chat_instruction('pending',self.tid,'NOT_IN_INDEX')
        self.assertEqual(build_files(self.cal),files)
        trip = self.cal.get_trip_command_context(self.tid)['trip']
        trip['summary']='COMMENT_ONLY'
        self.replace_trip(trip,'comment-only')
        self.assertEqual(build_files(self.cal),files)

    def test_rename_add_move_delete_and_duplicate_names(self):
        before = build_files(self.cal)
        self.cal.set_direct_override('rename',self.tid,'stay-1','/action','INDEX_RENAMED')
        after = build_files(self.cal)
        entry = next(i for d in self.trip_index(after)['days'] for i in d['items'] if i['source_item_id']=='stay-1')
        self.assertEqual(entry['title'],'INDEX_RENAMED')
        self.assertEqual(after['trip-index.json'],before['trip-index.json'])
        trip = self.cal.get_trip_command_context(self.tid)['trip']
        extra = copy.deepcopy(trip['days'][0]['scheduleItems'][0])
        extra.update(id='index-extra',action='DUPLICATE_NAME',
                     order=max(i['order'] for i in trip['days'][0]['scheduleItems'])+1)
        trip['days'][0]['scheduleItems'].append(extra)
        other = copy.deepcopy(extra);other.update(id='index-extra-2',order=extra['order']+1)
        trip['days'][0]['scheduleItems'].append(other)
        self.replace_trip(trip,'add-index-items')
        day_date=trip['days'][0]['date']
        items=build_files(self.cal)['item-index/by-date/'+day_date+'.json']['trips'][0]['items']
        self.assertEqual({i['source_item_id'] for i in items if i['title']=='DUPLICATE_NAME'},
                         {'index-extra','index-extra-2'})
        trip=self.cal.get_trip_command_context(self.tid)['trip']
        moved=next(i for i in trip['days'][0]['scheduleItems'] if i['id']=='index-extra')
        trip['days'][0]['scheduleItems'].remove(moved)
        if 'dayId' in moved:moved['dayId']=trip['days'][1]['id']
        moved['order']=max(i['order'] for i in trip['days'][1]['scheduleItems'])+1
        trip['days'][1]['scheduleItems'].append(moved)
        self.replace_trip(trip,'move-index-item')
        days=self.trip_index(build_files(self.cal))['days']
        self.assertNotIn('index-extra',{i['source_item_id'] for i in days[0]['items']})
        self.assertIn('index-extra',{i['source_item_id'] for i in days[1]['items']})
        trip=self.cal.get_trip_command_context(self.tid)['trip']
        trip['days'][1]['scheduleItems']=[i for i in trip['days'][1]['scheduleItems'] if i['id']!='index-extra']
        self.replace_trip(trip,'delete-index-item')
        self.assertNotIn('index-extra',{i['source_item_id'] for d in self.trip_index(build_files(self.cal))['days'] for i in d['items']})

    def test_unplanned_travel_and_stale_index_latest_mac_read(self):
        travel=self.cal.change_travel(dict(title='合成未定旅行',date_status='undecided',
                                           start_date=None,end_date=None))['receipt']['item']
        files=build_files(self.cal)
        self.assertNotIn('item-index/by-trip/'+travel['id']+'.json',files)
        old=next(i for d in self.trip_index(files)['days'] for i in d['items'] if i['source_item_id']=='stay-1')
        self.cal.set_direct_override('later-name',self.tid,'stay-1','/action','LATEST_ON_MAC')
        p=subprocess.run([sys.executable,'-B','scripts/cal_schedule.py','--database',str(self.db),
                          '--local-root',str(self.root),'trip-get','--id',self.tid,
                          '--item-id',old['source_item_id']],cwd=fixture.ROOT,capture_output=True,text=True,check=True)
        current=json.loads(p.stdout)
        self.assertEqual(current['context_scope'],'item')
        self.assertNotEqual(current['item']['action'],old['title'])
        self.assertEqual(current['item']['action'],'LATEST_ON_MAC')
        self.assertEqual(current['revision'],self.cal.get_trip_command_context(self.tid)['revision'])

    def test_atomic_index_cleanup_preserves_source(self):
        files={'trip-index.json':'{}\n','item-index/by-date/2099-01-01.json':'{}\n'}
        tree=dict(tree=[dict(path='AGENTS.md',type='blob',sha='source'),
                        dict(path='item-index/by-date/old.json',type='blob',sha='old'),
                        dict(path='item-index/by-trip/old.json',type='blob',sha='old-trip'),
                        dict(path='trip-index.json',type='blob',sha='old-index')])
        replies=[dict(object=dict(sha='parent')),dict(tree=dict(sha='base-tree')),
                 tree,dict(sha='new-tree'),dict(sha='new-commit'),{}]
        with patch('scripts.publish_trip_index.github',side_effect=replies) as api:
            result=publish_files('/synthetic/gh',files)
        edits=api.call_args_list[3].args[3]['tree']
        self.assertEqual({e['path'] for e in edits},set(files)|{'item-index/by-date/old.json','item-index/by-trip/old.json'})
        self.assertTrue(all(e['sha'] is None for e in edits if '/old.json' in e['path']))
        self.assertEqual(api.call_args_list[-1].args[3],dict(sha='new-commit',force=False))

    def test_cache_failure_and_existing_hook(self):
        self.settings()
        with patch('scripts.publish_trip_index.publish_files',
                   return_value=dict(status='published',commit_sha='synthetic')) as api:
            self.assertEqual(publish(self.db,self.root)['status'],'published')
            self.assertEqual(publish(self.db,self.root)['status'],'unchanged')
            self.cal.add_chat_instruction('new',self.tid,'指示')
            self.assertEqual(publish(self.db,self.root)['status'],'unchanged')
            api.assert_called_once()
        self.cal.set_direct_override('item-name',self.tid,'stay-1','/action','INDEX_CHANGED')
        before=self.cal.get_trip_command_context(self.tid)
        with patch('scripts.publish_trip_index.publish_files',side_effect=RuntimeError('offline')):
            with self.assertRaises(RuntimeError):publish(self.db,self.root)
        self.assertEqual(self.cal.get_trip_command_context(self.tid),before)
        self.launcher.stop()
        with patch('Sources.calendar_domain.trip_index.subprocess.Popen') as spawn:
            self.cal.add_chat_instruction('ignored',self.tid,'指示のみ')
            self.cal.change_schedule('event','save',values=dict(title='合成',start_date='2099-01-01'))
            spawn.assert_not_called()
            self.cal.set_direct_override('item-name',self.tid,'stay-1','/action','REFRESH')
            spawn.assert_called_once()
