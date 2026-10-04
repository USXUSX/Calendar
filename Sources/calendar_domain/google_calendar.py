"""CAL-owned one-way projection. Google failures never roll back a CAL save."""
import fcntl
import functools
import hashlib
import json
import os
import sqlite3
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from uuid import uuid4
from urllib.request import Request, urlopen
from urllib.parse import quote, urlencode
from urllib.error import HTTPError

ZONE = ZoneInfo('Asia/Tokyo')
SCOPE = 'https://www.googleapis.com/auth/calendar.app.created'


def today():
    return datetime.now(ZONE).date().isoformat()


def extend_google(c):
    c.execute('CREATE TABLE IF NOT EXISTS google_events (cal_key TEXT PRIMARY KEY, event_id TEXT NOT NULL, lower_date TEXT NOT NULL, applied_hash TEXT, error TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS google_calendar_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')


def private_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + '.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(value, f)
    os.replace(temporary, path)


class GoogleError(Exception):
    """Safe reason only: never expose provider bodies, URLs or tokens."""


class GoogleClient:
    def __init__(self, root):
        self.root = root
        try:
            self.config = json.loads((root/'settings/google-calendar.json').read_text())
            self.token = json.loads((root/'settings/google-token.json').read_text())
        except (OSError, ValueError):
            raise GoogleError('authentication_required') from None
        self.access = None

    def request(self, method, path, body=None):
        if self.access is None:
            try:
                credentials = json.loads((self.root/'settings/google-client.json').read_text())['installed']
                raw = urlencode(dict(client_id=credentials['client_id'], client_secret=credentials.get('client_secret',''),
                                     refresh_token=self.token['refresh_token'], grant_type='refresh_token')).encode()
                with urlopen(Request('https://oauth2.googleapis.com/token', data=raw), timeout=15) as r:
                    self.access = json.load(r)['access_token']
            except Exception:
                raise GoogleError('authentication_required') from None
        req = Request('https://www.googleapis.com/calendar/v3/'+path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={'Authorization':'Bearer '+self.access,'Content-Type':'application/json'}, method=method)
        try:
            with urlopen(req, timeout=15) as r:
                return json.loads(r.read() or b'{}')
        except HTTPError as e:
            raise GoogleError('http_'+str(e.code)) from None
        except (OSError, ValueError):
            raise GoogleError('communication_failed') from None


def event_body(item, key):
    begin = item['start_date']; finish = item.get('end_date') or begin
    notes = item.get('notes') or ''
    body = dict(summary=('✓ ' if item.get('completed_at') else '')+item['title'],
                description=notes, extendedProperties={'private':{'calOwner':'cal-v1','calKey':hashlib.sha256(key.encode()).hexdigest()}},
                reminders={'useDefault':False}, visibility='private')
    if item.get('trip_id'):
        link = 'https://frame.usxtools.com/calendar/trips/'+quote(item['trip_id'], safe='')
        body['description'] = (notes+'\n'+link).strip()
        body['source'] = dict(title='CAL 旅程',url=link)
    if item.get('start_time'):
        zone_name = item.get('time_zone') or 'Asia/Tokyo'
        zone = ZoneInfo(zone_name)
        start = datetime.fromisoformat(begin+'T'+item['start_time']).replace(tzinfo=zone)
        if item.get('end_time'):
            end = datetime.fromisoformat(finish+'T'+item['end_time']).replace(tzinfo=zone)
        else:
            end = start + timedelta(minutes=1)
            body['description'] = (body['description']+'\n終了不明（1分の開始マーカー）').strip()
        # Google requires a positive duration even for an explicitly zero length CAL marker.
        if end == start:
            end = start + timedelta(minutes=1)
            body['description'] = (body['description']+'\n開始マーカー（CALの開始・終了は同時刻）').strip()
        body.update(start=dict(dateTime=start.isoformat(),timeZone=zone_name),end=dict(dateTime=end.isoformat(),timeZone=zone_name))
    else:
        body.update(start={'date':begin},end={'date':(date.fromisoformat(finish)+timedelta(days=1)).isoformat()})
    return body


def recurrence_lines(segment, item, exceptions):
    from .recurrence import matches
    rule = segment['rule']; freq = rule['frequency']
    parts = ['FREQ='+{'daily':'DAILY','weekly':'WEEKLY','monthly':'MONTHLY','month_end':'MONTHLY','yearly':'YEARLY'}[freq]]
    if freq=='weekly': parts.append('BYDAY='+','.join(['SU','MO','TU','WE','TH','FR','SA'][d] for d in rule['weekdays']))
    if freq in ('monthly','month_end'): parts.append('BYMONTHDAY='+str(rule['month_day'] if freq=='monthly' else -1))
    if freq=='yearly':
        d=date.fromisoformat(rule['start']);parts.extend(['BYMONTH='+str(d.month),'BYMONTHDAY='+str(d.day)])
    until = min(segment.get('until') or '9999-12-31',rule.get('until') or '9999-12-31')
    if until!='9999-12-31':
        if item.get('start_time'):
            limit=datetime.fromisoformat(until+'T23:59:59').replace(tzinfo=ZONE)
            parts.append('UNTIL='+limit.astimezone(ZoneInfo('UTC')).strftime('%Y%m%dT%H%M%SZ'))
        else: parts.append('UNTIL='+until.replace('-',''))
    lines=['RRULE:'+';'.join(parts)]
    excluded=[d for d in exceptions if d>=item['start_date'] and matches(segment,d)]
    if excluded:
        if item.get('start_time'):
            lines.append('EXDATE;TZID=Asia/Tokyo:'+','.join(d.replace('-','')+'T'+item['start_time'].replace(':','')+'00' for d in sorted(excluded)))
        else: lines.append('EXDATE;VALUE=DATE:'+','.join(d.replace('-','') for d in sorted(excluded)))
    return lines


def after_save(method):
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        state = self._google_save_state
        depth = getattr(state,'depth',0)
        state.depth = depth+1
        try:
            result = method(self,*args,**kwargs)
        finally:
            state.depth = depth
        if depth==0:
            try:google = self.sync_google()
            except Exception:google = dict(status='unreflected',reason='delivery_failed',pending=0)
            if isinstance(result,dict):
                result = dict(result,google=google)
        return result
    return wrapped


class GoogleCalendarMixin:
    def _google_rows(self):
        with self._read() as c:
            exists=c.execute("SELECT 1 FROM sqlite_master WHERE name='google_events'").fetchone()
            return {r['cal_key']:dict(r) for r in c.execute('SELECT * FROM google_events')} if exists else None

    def _google_desired(self, known):
        from .recurrence import matches, template
        current=today();desired={}
        with self._read() as c:
            for raw in c.execute('SELECT * FROM events'):
                item=dict(raw);key='event:'+item['id']
                if item['start_date']>=current or key in known:
                    desired[key]=event_body(item,key)
            for raw in c.execute('SELECT * FROM todos WHERE due_date IS NOT NULL'):
                item=dict(raw);key='todo:'+item['id']
                item.update(title=item['label'],start_date=item['due_date'],start_time=item['due_time'])
                if item['due_date']>=current or key in known: desired[key]=event_body(item,key)
            series=[dict(r) for r in c.execute('SELECT * FROM schedule_series')]
        for t in self.list_trips():
            key='trip:'+t['trip_id']
            if t['dateRange']['end']>=current or key in known:
                item=dict(title=t['title'],start_date=t['dateRange']['start'],end_date=t['dateRange']['end'],trip_id=t['trip_id'])
                desired[key]=event_body(item,key)
        for row in series:
            data=json.loads(row['data_json'])
            for s in data['segments']:
                key='series:'+row['id']+':'+s['from']
                floor=known.get(key,{}).get('lower_date',current)
                first=max(s['from'],s['rule']['start'],floor)
                end=min(s.get('until') or '9999-12-31',s['rule'].get('until') or '9999-12-31')
                # At most one leap-year cycle to find the first valid recurrence, never expand all future rounds.
                ordinal=date.fromisoformat(first).toordinal()
                for n in range(1462):
                    if ordinal+n>date.max.toordinal():break
                    anchor=date.fromordinal(ordinal+n).isoformat()
                    if anchor>end:break
                    if matches(s,anchor):
                        item=template(s,anchor,row['kind'])
                        if row['kind']=='todo':item.update(title=item['label'],start_date=item['due_date'],start_time=item.get('due_time'))
                        body=event_body(item,key);body['recurrence']=recurrence_lines(s,item,data['exceptions']);desired[key]=body
                        break
            for anchor,exception in data['exceptions'].items():
                key='rec:'+row['id']+':'+anchor
                if exception.get('deleted'):continue
                item=self._occurrence(row,data,anchor)
                # A tracked series keeps past exceptions in scope, even if the round is moved backwards.
                tracked=any(k.startswith('series:'+row['id']+':') and anchor>=v['lower_date'] for k,v in known.items())
                if item['start_date']>=current or key in known or tracked:desired[key]=event_body(item,key)
        return desired

    @staticmethod
    def _google_hash(body):
        return hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def google_status(self):
        try:
            rows=self._google_rows()
            if rows is None:return dict(status='unreflected',reason='migration_required',pending=0)
            desired=self._google_desired(rows)
            pending=sum(self._google_hash(desired.get(k))!=rows.get(k,{}).get('applied_hash') or bool(rows.get(k,{}).get('error')) for k in set(desired)|set(rows))
            configured=(self.trip_root/'settings/google-token.json').is_file() and (self.trip_root/'settings/google-calendar.json').is_file()
            return dict(status='unreflected' if pending or not configured else 'synced',pending=pending,
                        reason='authentication_required' if not configured else next((r['error'] for r in rows.values() if r['error']),None))
        except Exception:
            return dict(status='unreflected',reason='state_unavailable',pending=0)

    def sync_google(self, *, client=None, reconcile=False):
        if self._google_rows() is None:return self.google_status()
        # Serialize CLI and Frame deliveries without holding the CAL transaction during HTTP.
        fd=os.open(str(self.db_path)+'.google.lock',os.O_CREAT|os.O_RDWR,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:return dict(self.google_status(),reason='delivery_in_progress')
            rows=self._google_rows();desired=self._google_desired(rows)
            try:client=client or GoogleClient(self.trip_root)
            except GoogleError:return self.google_status()
            calendar_id=client.config.get('calendar_id')
            if not calendar_id or calendar_id=='primary':return dict(self.google_status(),reason='calendar_required')
            with sqlite3.connect(self.db_path) as c:
                pinned=c.execute("SELECT value FROM google_calendar_meta WHERE key='calendar_id'").fetchone()
                if pinned and pinned[0]!=calendar_id:return dict(self.google_status(),reason='calendar_id_conflict')
                c.execute("INSERT OR IGNORE INTO google_calendar_meta VALUES ('calendar_id',?)",(calendar_id,))
            base='calendars/'+quote(calendar_id,safe='')+'/events'
            for key in sorted(set(rows)|set(desired)):
                body=desired.get(key);digest=self._google_hash(body);old=rows.get(key)
                if old and old['applied_hash']==digest and not old.get('error') and not reconcile:continue
                if old is None:
                    old=dict(event_id='cal'+uuid4().hex,lower_date=today(),applied_hash=None)
                    with sqlite3.connect(self.db_path) as c:
                        c.execute('INSERT INTO google_events VALUES (?,?,?,?,NULL)',(key,old['event_id'],old['lower_date'],None))
                event_path=base+'/'+old['event_id']
                try:
                    try:remote=client.request('GET',event_path)
                    except GoogleError as e:
                        if str(e) not in ('http_404','http_410'):raise
                        remote=None
                    if remote and remote.get('status')!='cancelled':
                        owner=remote.get('extendedProperties',{}).get('private',{})
                        expected=hashlib.sha256(key.encode()).hexdigest()
                        if owner.get('calOwner')!='cal-v1' or owner.get('calKey')!=expected:raise GoogleError('ownership_conflict')
                        if body:client.request('PUT',event_path,dict(body,status='confirmed'))
                        else:client.request('DELETE',event_path)
                    elif body:
                        if (remote and remote.get('status')=='cancelled') or old['applied_hash']==self._google_hash(None):
                            old['event_id']='cal'+uuid4().hex
                            with sqlite3.connect(self.db_path) as c:c.execute('UPDATE google_events SET event_id=? WHERE cal_key=?',(old['event_id'],key))
                        try:client.request('POST',base,dict(body,id=old['event_id']))
                        except GoogleError as e:
                            if str(e)!='http_409':raise
                            # Response loss: same persisted ID, checked ownership on the next retry.
                            raise GoogleError('reconciliation_required')
                    with sqlite3.connect(self.db_path) as c:c.execute('UPDATE google_events SET applied_hash=?,error=NULL WHERE cal_key=?',(digest,key))
                except GoogleError as e:
                    with sqlite3.connect(self.db_path) as c:c.execute('UPDATE google_events SET error=? WHERE cal_key=?',(str(e),key))
                    if str(e) in ('authentication_required','http_401','http_403'):break
            return self.google_status()
        except Exception:
            return dict(status='unreflected',reason='delivery_failed',pending=0)
        finally:os.close(fd)
