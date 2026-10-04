"""Shared ordinary schedule commands and period summaries; no external delivery."""
from datetime import date, datetime, timezone
import hashlib
import json
import re
import uuid
from .errors import ValidationError, NotFoundError


def day(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValidationError('日付を確認してください。')
    return value


def clock(value):
    if value is not None and (not isinstance(value, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value)):
        raise ValidationError('時刻を確認してください。')
    return value


def schedule_revision(item):
    """Opaque fingerprint of the authoritative row, including timestamps."""
    raw = json.dumps(dict(item), ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'sha256:' + hashlib.sha256(raw.encode('utf-8')).hexdigest()


class ScheduleMixin:
    def read_schedule(self, start, end, include_completed=False, include_trips=True):
        day(start); day(end)
        if start > end:
            raise ValidationError('期間を確認してください。')
        trips = self.list_trips() if include_trips else []
        items = [dict(id=t['trip_id'], kind='trip', title=t['title'], start_date=t['dateRange']['start'],
                      end_date=t['dateRange']['end'], start_time=None, end_time=None, trip_id=t['trip_id'])
                 for t in trips if t['dateRange']['start'] <= end and t['dateRange']['end'] >= start]
        with self._read() as c:
            for r in c.execute('SELECT * FROM events WHERE start_date<=? AND COALESCE(end_date,start_date)>=?', (end,start)):
                items.append(dict(r) | {'kind':'event', 'revision':schedule_revision(r)})
            for r in c.execute('SELECT * FROM todos WHERE due_date BETWEEN ? AND ? AND (? OR completed_at IS NULL)', (start,end,include_completed)):
                items.append(dict(r) | dict(kind='todo', title=r['label'], start_date=r['due_date'],
                                           end_date=None, start_time=r['due_time'], end_time=None, revision=schedule_revision(r)))
        return dict(items=sorted(items, key=lambda x:(x['start_date'],x.get('start_time') or '',x['kind'],x['id'])),
                    trips=[dict(id=t['trip_id'], title=t['title']) for t in trips])

    def change_schedule(self, kind, action, item_id=None, values=None):
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            return self._change_schedule(c, kind, action, item_id, values)

    def _change_schedule(self, c, kind, action, item_id=None, values=None):
        if kind not in ('event','todo') or action not in ('save','delete','complete'):
            raise ValidationError('予定の操作を確認してください。')
        if not isinstance(values, dict):
            raise ValidationError('入力を確認してください。')
        if action == 'complete' and kind != 'todo':
            raise ValidationError('完了できるのはタスクです。')
        if action != 'save' and not item_id:
            raise ValidationError('対象を選択してください。')
        table = 'events' if kind == 'event' else 'todos'
        allowed = {'title','start_date','start_time','end_date','end_time','notes','trip_id'} if kind == 'event' else {'label','due_date','due_time','notes'}
        if action == 'save' and set(values) - allowed:
            raise ValidationError('未対応の項目があります。')
        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        old = c.execute(f'SELECT * FROM {table} WHERE id=?', (item_id,)).fetchone() if item_id else None
        if item_id and old is None:
            raise NotFoundError('対象が見つかりません。画面を更新してください。')
        if action == 'delete':
            c.execute(f'DELETE FROM {table} WHERE id=?', (item_id,))
            return {'id':item_id, 'deleted':True}
        if action == 'complete':
            if set(values) != {'completed'} or not isinstance(values['completed'],bool):
                raise ValidationError('完了状態を確認してください。')
            c.execute('UPDATE todos SET completed_at=?,updated_at=? WHERE id=?', (timestamp if values['completed'] else None,timestamp,item_id))
        else:
            merged = dict(old) if old else dict.fromkeys(allowed)
            merged.update(values)
            title_field, date_field, time_field = ('title','start_date','start_time') if kind == 'event' else ('label','due_date','due_time')
            if not isinstance(merged[title_field],str) or not merged[title_field].strip():
                raise ValidationError('件名を入力してください。')
            day(merged[date_field]); clock(merged[time_field])
            if merged['notes'] is not None and not isinstance(merged['notes'],str):
                raise ValidationError('メモを確認してください。')
            if kind == 'event':
                finish = day(merged['end_date']) if merged['end_date'] else merged['start_date']
                clock(merged['end_time'])
                if merged['end_time'] and not merged['end_date']:
                    merged['end_date'] = finish
                if finish < merged['start_date'] or (merged['end_time'] and not merged['start_time']) or (finish == merged['start_date'] and merged['end_time'] and merged['end_time'] < merged['start_time']):
                    raise ValidationError('終了は開始以降にしてください。終了時刻には開始時刻が必要です。')
                trip_id = merged['trip_id']
                if trip_id is not None and (not isinstance(trip_id,str) or c.execute('SELECT 1 FROM trips WHERE id=?',(trip_id,)).fetchone() is None):
                    raise ValidationError('関連する旅程を確認してください。')
            fields = sorted(allowed)
            if old:
                c.execute(f'UPDATE {table} SET '+','.join(f'{f}=?' for f in fields)+',updated_at=? WHERE id=?', [merged[f] for f in fields]+[timestamp,item_id])
            else:
                item_id = str(uuid.uuid4())
                fields += ['id','visibility','created_at','updated_at']
                merged.update(id=item_id,visibility='owner',created_at=timestamp,updated_at=timestamp)
                c.execute(f'INSERT INTO {table} ('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',[merged[f] for f in fields])
        result = dict(c.execute(f'SELECT * FROM {table} WHERE id=?',(item_id,)).fetchone())
        return result
