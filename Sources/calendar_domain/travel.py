"""Independent travel management in the existing CAL registry and receipt transaction."""
import calendar
import copy
import json
import re
from datetime import date, datetime, timezone
from uuid import uuid4
from .errors import ValidationError, ConflictError, NotFoundError
from .google_calendar import after_save

CATEGORIES = ('general','air','rail','ship','car','lodging','food','reservation','medical','finance','anniversary','pet','travel','other')
TRANSPORTS = ('air','rail','ship','car','other')


def validate_common(c, values):
    if values.get('category', 'general') not in CATEGORIES:
        raise ValidationError('invalid_category')
    url = values.get('gmail_url')
    if url is not None and (not isinstance(url,str) or not re.fullmatch(r'https://mail\.google\.com/mail/u/(?:\d+|[^/?#]+)/(?:#(?:all|inbox)/[A-Za-z0-9_-]+|\?[^#\s]*#(?:all|inbox)/[A-Za-z0-9_-]+)',url)):
        raise ValidationError('invalid_gmail_reference')
    refs=[values.get(k) for k in ('google_calendar_id','google_event_id')]
    if any(refs) and (not all(isinstance(v,str) and v.strip() for v in refs) or not url):
        raise ValidationError('verified_google_reference_requires_gmail')
    tid = values.get('trip_id')
    if tid is not None and (not isinstance(tid,str) or c.execute('SELECT 1 FROM trips WHERE id=?',(tid,)).fetchone() is None):
        raise ValidationError('travel_not_found')


class TravelMixin:
    def _travel_row(self, c, tid):
        return c.execute('SELECT * FROM travel_basics WHERE trip_id=?',(tid,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='travel_basics'").fetchone() else None

    def has_itinerary(self, tid):
        with self._read() as c:
            row = self._travel_row(c,tid)
        return row is None or bool(row['has_itinerary'])

    def _travel_basic(self, c, tid):
        from .schedule import schedule_revision
        registry = c.execute('SELECT * FROM trips WHERE id=?',(tid,)).fetchone()
        if registry is None: raise NotFoundError('travel_not_found')
        row = self._travel_row(c,tid)
        if row:
            data = json.loads(row['data_json']); has = bool(row['has_itinerary'])
        else:
            trip = self.get_effective_trip(tid)
            data = dict(title=trip['title'],start_date=trip['dateRange']['start'],end_date=trip['dateRange']['end'],date_status='confirmed',transport='other')
            has = True
        return dict(data,trip_id=tid,id=tid,dateRange=dict(start=data['start_date'],end=data['end_date']),has_itinerary=has,itinerary_id=tid if has else None,
                    revision=schedule_revision(dict(registry)|dict(basics=data,has_itinerary=has)))

    def list_travel(self):
        with self._read() as c:
            items=[self._travel_basic(c,row[0]) for row in c.execute('SELECT id FROM trips ORDER BY id')]
        return sorted(items,key=lambda t:(t['start_date'] or '9999-12-31',t['id']))

    def get_travel(self, tid, start=None, end=None):
        from .schedule import day
        if start is None and end is None:
            current=date.today(); start=current.replace(day=1).isoformat()
            end=current.replace(day=calendar.monthrange(current.year,current.month)[1]).isoformat()
        day(start); day(end)
        if end < start or (date.fromisoformat(end)-date.fromisoformat(start)).days > 365:
            raise ValidationError("invalid_related_window")
        with self._read() as c:
            result=self._travel_basic(c,tid)
            items=[]
            from .schedule import schedule_revision
            for kind, table in [('event','events'),('todo','todos')]:
                for row in c.execute(f'SELECT * FROM {table} WHERE trip_id=?',(tid,)):
                    item=dict(row,kind=kind,revision=schedule_revision(row))
                    if kind=='todo': item.update(title=row['label'],start_date=row['due_date'],start_time=row['due_time'])
                    items.append(item)
            series=[]
            for raw in c.execute('SELECT * FROM schedule_series'):
                data=json.loads(raw['data_json'])
                if any(s['values'].get('trip_id')==tid for s in data['segments']) or any(e.get('values',{}).get('trip_id')==tid for e in data['exceptions'].values()):
                    series.append(self.get_series(raw['id']))
            items.extend(i for i in self._read_recurrence(c,start,end,True) if i.get('trip_id')==tid)
        result['related_series']=series
        result['recurrence_window']=dict(start=start,end=end)
        result['items']=sorted(items,key=lambda i:(i.get('start_date') or '',i.get('start_time') or '',i['id']))
        return result

    def _travel_overlay(self, trip):
        with self._read() as c: row=self._travel_row(c,trip['id'])
        if row:
            data=json.loads(row['data_json'])
            trip['title']=data['title']
            # Itinerary day dates remain structural; managed period is applied to the view.
        return trip

    @after_save
    def change_travel(self, values, item_id=None, expected_revision=None, request_id=None):
        return self.apply_travel_request(dict(request_id=request_id or str(uuid4()),kind='travel',action='save',id=item_id,expected_revision=expected_revision,values=values))

    @after_save
    def apply_travel_request(self, request):
        from .schedule import day
        from .schedule_chat import encoded, request_id
        if not isinstance(request,dict) or set(request)-{'request_id','kind','action','id','expected_revision','values'} or request.get('kind')!='travel' or request.get('action')!='save':
            raise ValidationError('invalid_travel_request')
        identity=request_id(request.get('request_id')); digest=self._digest(encoded(request).encode())
        tid=request.get('id'); values=request.get('values')
        if not isinstance(values,dict) or set(values)-{'title','start_date','end_date','date_status','transport'}: raise ValidationError('invalid_travel_values')
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            prior=c.execute('SELECT * FROM schedule_receipts WHERE request_id=?',(identity,)).fetchone()
            if prior:
                if prior['payload_hash']!=digest: raise ConflictError('request_id_payload_conflict')
                return dict(status='committed',resolution='replayed',receipt=json.loads(prior['receipt_json']))
            old=self._travel_basic(c,tid) if tid else None
            if old and request.get('expected_revision')!=old['revision']: raise ConflictError('revision_conflict')
            data={k:old[k] for k in ('title','start_date','end_date','date_status','transport')} if old else dict(title=None,start_date=None,end_date=None,date_status='undecided',transport='other')
            data.update(values)
            if not isinstance(data['title'],str) or not data['title'].strip(): raise ValidationError('travel_title_required')
            if data['date_status'] not in ('confirmed','tentative','undecided') or data['transport'] not in TRANSPORTS: raise ValidationError('invalid_travel_state')
            if data['date_status']=='undecided':
                if data['start_date'] is not None or data['end_date'] is not None: raise ValidationError('undecided_dates_must_be_null')
            else:
                day(data['start_date']);day(data['end_date'])
                if data['end_date']<data['start_date']: raise ValidationError('invalid_travel_period')
            stamp=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            if not tid:
                tid='travel-'+uuid4().hex
                c.execute("INSERT INTO trips (id,visibility,created_at,updated_at) VALUES (?,'owner',?,?)",(tid,stamp,stamp))
            else: c.execute('UPDATE trips SET updated_at=?,version=version+1 WHERE id=?',(stamp,tid))
            c.execute('INSERT INTO travel_basics VALUES (?,?,?) ON CONFLICT(trip_id) DO UPDATE SET data_json=excluded.data_json',(tid,encoded(data),int(old['has_itinerary']) if old else 0))
            item=self._travel_basic(c,tid)
            receipt=dict(status='committed',request_id=identity,receipt_id=str(uuid4()),kind='travel',action='save',entity_id=tid,item=item,revision=item['revision'],previous_revision=request.get('expected_revision'),committed_at=stamp)
            c.execute('INSERT INTO schedule_receipts VALUES (?,?,?)',(identity,digest,encoded(receipt)))
        return dict(status='committed',resolution='new',receipt=receipt)

    def _check_travel_connection(self, c, candidate):
        row=self._travel_row(c,candidate['id'])
        if row and not row['has_itinerary']: return row
        for other in c.execute('SELECT * FROM travel_basics WHERE trip_id!=?',(candidate['id'],)):
            data=json.loads(other['data_json'])
            if not other['has_itinerary'] and data['title']==candidate['title'] and (data['start_date'] is None or (data['start_date']==candidate['dateRange']['start'] and data['end_date']==candidate['dateRange']['end'])):
                raise ConflictError('existing_travel_use_its_id')
        return None

    def _connect_travel(self,c,candidate):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name='travel_basics'").fetchone(): return
        data=dict(title=candidate['title'],start_date=candidate['dateRange']['start'],end_date=candidate['dateRange']['end'],date_status='confirmed',transport='other')
        c.execute('INSERT INTO travel_basics VALUES (?,?,1) ON CONFLICT(trip_id) DO UPDATE SET has_itinerary=1',(candidate['id'],json.dumps(data,ensure_ascii=False)))

    def _update_travel_fields(self,c,tid,changes):
        row=self._travel_row(c,tid)
        if row and changes:
            data=json.loads(row['data_json']);data.update(changes)
            c.execute('UPDATE travel_basics SET data_json=? WHERE trip_id=?',(json.dumps(data,ensure_ascii=False),tid))
            c.execute('UPDATE trips SET version=version+1 WHERE id=?',(tid,))

    def _apply_travel_changes(self,c,tid,changes):
        row=self._travel_row(c,tid)
        if row and changes:
            data=json.loads(row['data_json']);data.update(changes)
            c.execute('UPDATE travel_basics SET data_json=? WHERE trip_id=?',(json.dumps(data,ensure_ascii=False),tid))
