import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from Sources.calendar_domain import CalendarDomain, ConflictError, ValidationError
from Sources.place_acquisition import Acquisition, FacilityCandidate, WikidataAdapter, FacilityQuery
from Sources.aig_comment_extraction import extract, result
from scripts.init_calendar_db import initialize
from Tests.test_place_acquisition import entity, statement


class CommentTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        self.db = root / 'db'; initialize(self.db)
        self.domain = CalendarDomain(self.db, root / 'data')
        parsed = self.domain.parse_chat_paste('旅行名: 合成\n日付: 2027-06-12\n代表エリア: 東京\n予定: 未定 | 散歩\nカテゴリ: 観光\n場所: サンプル塔\nコメント: 元コメント\n予定: 未定 | 昼食\nカテゴリ: 食事\n場所: 別施設')
        self.tid = self.domain.import_chat_paste('import', parsed, confirmed=True)['trip_id']
        self.trip = self.domain.get_effective_trip(self.tid)
        self.item = self.trip['days'][0]['scheduleItems'][0]
        self.iid = self.item['id']; self.pid = self.item['placeSelection']['selection'][0]
        self.raw = self.domain._trip_path(self.tid).read_bytes()
        self.evidence = dict(text='歴史資料を展示する塔。営業は月曜から金曜。展望台から街並みが見える。',
            source='https://example.org/source', retrieved_at='2026-09-07T00:00:00+00:00',
            license='CC0', attribution='Synthetic source', storage_allowed=True)

    def acquire(self, instruction='概要', evidence=None, status='candidates'):
        owner = self
        class Adapter:
            def search(self, query):
                owner.query = query
                return Acquisition(status, [FacilityCandidate({'name': 'サンプル塔'},
                    {'description': '非保存の本文', 'license': 'CC0'},
                    [copy.deepcopy(owner.evidence if evidence is None else evidence)])])
        return self.domain.get_comment_enrichment(self.tid, self.iid, self.pid, instruction, Adapter())

    def prepare(self, acquired, text='短い補足', ids=None):
        def transport(request):
            self.request = request
            return result('extracted', text, ['e0'] if ids is None else ids)
        return self.domain.prepare_comment_enrichment(self.tid, self.iid, acquired, 0, transport, confirmed=True)

    def append(self, preview):
        return self.domain.append_comment_enrichment('append', self.tid, self.iid, preview, confirmed=True)

    def test_three_instructions_same_flow_preserves_all_other_fields(self):
        for instruction, text in [('概要', '歴史資料を展示する塔。'), ('営業日', '営業は月曜から金曜。'), ('見どころ', '展望台から街並みが見える。')]:
            with self.subTest(instruction=instruction):
                before = self.domain.get_effective_trip(self.tid)
                preview = self.prepare(self.acquire(instruction), text)
                self.assertEqual(self.domain.get_effective_trip(self.tid), before)
                self.assertEqual(set(self.request), {'contract_version', 'instruction', 'evidence'})
                self.assertNotIn('元コメント', json.dumps(self.request, ensure_ascii=False))
                actual = self.append(preview)['trip']
                summary = actual['days'][0]['scheduleItems'][0]['summary']
                self.assertTrue(summary.startswith(before['days'][0]['scheduleItems'][0]['summary'] + '\n\n'))
                self.assertIn(text, summary); self.assertIn(self.evidence['source'], summary)
                self.assertIn(self.evidence['retrieved_at'], summary)
                self.assertNotIn('非保存の本文', summary)
                expected = copy.deepcopy(before); expected['days'][0]['scheduleItems'][0]['summary'] = summary
                self.assertEqual(actual, expected)
                self.assertEqual(self.domain._trip_path(self.tid).read_bytes(), self.raw)
                with self.assertRaises(ConflictError): self.append(preview)

    def test_permissions_and_missing_information_do_not_call_afm_or_write(self):
        for changes in [{'storage_allowed': False}, {'license': 'unknown'}, {'retrieved_at': 'invalid'}, {'source': 'javascript:bad'}]:
            acquired = self.acquire(evidence=dict(self.evidence, **changes))
            self.assertEqual(acquired['candidates'][0]['evidence'], [])
            preview = self.domain.prepare_comment_enrichment(self.tid, self.iid, acquired, 0,
                lambda _: self.fail('must not call'), confirmed=True)
            self.assertEqual(self.append(preview)['status'], 'no_information')
        self.assertEqual(self.domain.get_effective_trip(self.tid), self.trip)
        self.assertEqual(self.acquire(status='unavailable')['status'], 'unavailable')
        self.assertEqual(self.acquire(status='no_candidates')['status'], 'no_information')

    def test_no_information_and_afm_failure_keep_original(self):
        for answer in [result('no_information'), result('failed', code='afm_unavailable')]:
            preview = self.domain.prepare_comment_enrichment(self.tid, self.iid, self.acquire(), 0,
                lambda _: answer, confirmed=True)
            self.append(preview)
        self.assertEqual(self.domain.get_effective_trip(self.tid), self.trip)

    def test_confirmations_and_binding_required(self):
        acquired = self.acquire()
        with self.assertRaises(ValidationError):
            self.domain.prepare_comment_enrichment(self.tid, self.iid, acquired, 0, lambda _: None)
        preview = self.prepare(acquired)
        with self.assertRaises(ValidationError):
            self.domain.append_comment_enrichment('x', self.tid, self.iid, preview)
        wrong = copy.deepcopy(preview); wrong['source_item_id'] = 'other'
        with self.assertRaises(ValidationError): self.append(wrong)
        with self.assertRaises(ValidationError):
            self.domain.get_comment_enrichment(self.tid, self.iid, self.trip['places'][1]['id'], '概要', None)

    def test_manual_comment_edit_during_extraction_is_not_overwritten(self):
        acquired = self.acquire()
        def transport(_):
            self.domain.edit_trip_item('manual', self.tid, 'scheduleItem', self.iid, {'normal_comment': '変更後'})
            return result('extracted', '補足', ['e0'])
        with self.assertRaises(ConflictError):
            self.domain.prepare_comment_enrichment(self.tid, self.iid, acquired, 0, transport, confirmed=True)
        self.assertEqual(self.domain.get_effective_trip(self.tid)['days'][0]['scheduleItems'][0]['summary'], '変更後')

    def test_preview_stale_and_transaction_rollback(self):
        preview = self.prepare(self.acquire())
        original = self.domain._store_trip_fields
        def fail(*args):
            original(*args); raise RuntimeError('write failed')
        with patch.object(self.domain, '_store_trip_fields', side_effect=fail):
            with self.assertRaises(RuntimeError): self.append(preview)
        self.assertEqual(self.domain.get_effective_trip(self.tid), self.trip)
        self.domain.edit_trip_item('manual', self.tid, 'scheduleItem', self.iid, {'title': '変更'})
        with self.assertRaises(ConflictError): self.append(preview)

    def test_working_and_journal_boundary(self):
        self.domain.start_working_trip(self.tid)
        with sqlite3.connect(self.db) as db:
            before = db.execute('SELECT * FROM working_trips').fetchall()
        preview = self.prepare(self.acquire())
        journal = self.domain._journal_path(self.tid)
        journal.parent.mkdir(parents=True, exist_ok=True)
        journal.write_text('{}')
        with self.assertRaises(ConflictError): self.append(preview)
        journal.unlink()
        self.append(preview)
        with sqlite3.connect(self.db) as db:
            self.assertEqual(db.execute('SELECT * FROM working_trips').fetchall(), before)
        self.assertTrue(self.domain.get_working_trip(self.tid)['stale'])

    def test_invalid_afm_outputs_fail_without_persistence(self):
        for text, ids in [('補足', ['foreign']), ('補足', ['e0', 'e0']), ('x' * 301, ['e0']), ('補足', [])]:
            preview = self.prepare(self.acquire(), text, ids)
            self.assertEqual(preview['failure_code'], 'invalid_extraction')
            self.append(preview)
        self.assertEqual(self.domain.get_effective_trip(self.tid), self.trip)


class EvidenceTests(unittest.TestCase):
    def test_wikidata_opt_in_description_and_open_days(self):
        calls = []
        facility = entity(); facility['claims']['P3025'] = [statement({'id': 'Q10'})]
        def send(params):
            calls.append(params)
            if params['action'] == 'wbsearchentities': return {'search': [{'id': 'Q1'}]}
            if params['props'] == 'labels': return {'entities': {'Q10': {'id': 'Q10', 'labels': {'ja': {'value': '月曜から金曜'}}}}}
            return {'entities': {'Q1': facility}}
        adapter = WikidataAdapter(transport=send, include_comment_evidence=True)
        candidate = adapter.search(FacilityQuery('塔')).candidates[0]
        self.assertEqual(len(calls), 3)
        self.assertEqual(candidate.comment_evidence[1]['text'], '営業曜日（営業期間内）: 月曜から金曜')
        self.assertEqual(candidate.comment_evidence[0]['license'], 'CC0')
        facility['claims']['P3025'].append(statement({'id': 'Q11'}, qualifiers={'P580': []}))
        candidate = adapter.search(FacilityQuery('塔')).candidates[0]
        self.assertEqual(len(candidate.comment_evidence), 1)  # whole qualified property omitted
        self.assertEqual(WikidataAdapter(transport=send).search(FacilityQuery('塔')).candidates[0].comment_evidence, [])

    def test_client_invalid_requests_and_errors(self):
        never = lambda _: self.fail('must not call')
        self.assertEqual(extract('概要', [], never)['status'], 'no_information')
        self.assertEqual(extract('', [], never)['failure_code'], 'invalid_request')
        def fail(_): raise TimeoutError('private message')
        answer = extract('概要', [{'id': 'e0', 'text': '根拠'}], fail)
        self.assertEqual(answer, result('failed', code='generation_failed'))

if __name__ == '__main__': unittest.main()
