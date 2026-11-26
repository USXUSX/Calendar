"""CAL-owned one-way projection. Google failures never roll back a CAL save."""
from .timing import span
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
    columns = {row[1] for row in c.execute('PRAGMA table_info(google_events)')}
    for column in ('calendar_id', 'moving_to'):
        if column not in columns:
            c.execute(f'ALTER TABLE google_events ADD COLUMN {column} TEXT')
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


# Google Calendar event palette: Tangerine, Grape, Banana.
EVENT_COLOR_IDS = {'event': '6', 'trip': '3', 'todo': '5'}
CALENDAR_KEYS = {'event': 'calendar_id', 'trip': 'trip_calendar_id', 'todo': 'todo_calendar_id'}


def calendar_routes(config):
    main = config.get('calendar_id')
    trip = config.get('trip_calendar_id')
    todo = config.get('todo_calendar_id')
    if not main or main == 'primary':
        raise GoogleError('calendar_required')
    if not trip and not todo:
        return dict.fromkeys(CALENDAR_KEYS, main)
    if not trip or not todo or 'primary' in (trip, todo) or len({main, trip, todo}) != 3:
        raise GoogleError('calendar_routes_invalid')
    return dict(event=main, trip=trip, todo=todo)


def event_base(calendar_id):
    return 'calendars/' + quote(calendar_id, safe='') + '/events'


def owned_event(client, path, key):
    try:
        event = client.request('GET', path)
    except GoogleError as exc:
        if str(exc) not in ('http_404', 'http_410'):
            raise
        return None
    if event and event.get('status') != 'cancelled':
        owner = event.get('extendedProperties', {}).get('private', {})
        if owner.get('calOwner') != 'cal-v1' or owner.get('calKey') != hashlib.sha256(key.encode()).hexdigest():
            raise GoogleError('ownership_conflict')
    return event


def event_body(item, key, *, kind='event'):
    begin = item['start_date']; finish = item.get('end_date') or begin
    notes = item.get('notes') or ''
    body = dict(summary=('✓ ' if item.get('completed_at') else '')+item['title'],
                description=notes, extendedProperties={'private':{'calOwner':'cal-v1','calKey':hashlib.sha256(key.encode()).hexdigest()}},
                reminders={'useDefault':False}, visibility='private')
    if item.get('gmail_url'):
        body['description']=(notes+'\n'+item['gmail_url']).strip()
    if item.get('google_event_id') and item.get('google_calendar_id'):
        body['_external_reference']=dict(calendar_id=item['google_calendar_id'],event_id=item['google_event_id'])
    else:
        body['colorId'] = EVENT_COLOR_IDS[kind]
        body['_calendar_kind'] = kind
    if item.get('trip_id'):
        link = 'https://frame.usxtools.com/calendar/travels/'+quote(item['trip_id'], safe='')
        body['description'] = (body['description']+'\n'+link).strip()
        body['source'] = dict(title='CAL 旅行',url=link)
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
        if depth==0 and getattr(self._trip_write_state, 'connection', None) is None:
            try:
                status_only = self._defer_google_sync or (isinstance(result, dict) and result.get('resolution') == 'replayed')
                with span('post_commit_google_status' if status_only else 'post_commit_google_sync'):
                    google = self.google_status() if status_only else self.sync_google()
            except Exception:google = dict(status='unreflected',reason='delivery_failed',pending=0)
            if self._defer_google_sync:
                google = dict(google, sync='deferred')
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
                if item['due_date']>=current or key in known: desired[key]=event_body(item,key,kind='todo')
            series=[dict(r) for r in c.execute('SELECT * FROM schedule_series')]
        for t in self.list_travel():
            key='trip:'+t['trip_id']
            if t['dateRange']['end'] and (t['dateRange']['end']>=current or key in known):
                item=dict(title=t['title'],start_date=t['dateRange']['start'],end_date=t['dateRange']['end'],trip_id=t['trip_id'])
                desired[key]=event_body(item,key,kind='trip')
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
                        body=event_body(item,key,kind=row['kind']);body['recurrence']=recurrence_lines(s,item,data['exceptions']);desired[key]=body
                        break
            for anchor,exception in data['exceptions'].items():
                key='rec:'+row['id']+':'+anchor
                if exception.get('deleted'):continue
                item=self._occurrence(row,data,anchor)
                # A tracked series keeps past exceptions in scope, even if the round is moved backwards.
                tracked=any(k.startswith('series:'+row['id']+':') and anchor>=v['lower_date'] for k,v in known.items())
                if item['start_date']>=current or key in known or tracked:desired[key]=event_body(item,key,kind=row['kind'])
        return desired

    @staticmethod
    def _google_hash(body):
        if body is not None:
            body = {key: value for key, value in body.items() if key != '_calendar_kind'}
        return hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def _google_pending(self, body, row, routes):
        kind = body.get('_calendar_kind') if body else None
        current = row.get('calendar_id') or routes['event']
        return (bool(row.get('moving_to') or row.get('error'))
                or self._google_hash(body) != row.get('applied_hash')
                or bool(kind and current != routes[kind]))

    def google_status(self):
        try:
            rows=self._google_rows()
            if rows is None:return dict(status='unreflected',reason='migration_required',pending=0)
            desired=self._google_desired(rows)
            try:
                token=json.loads((self.trip_root/'settings/google-token.json').read_text())
                config=json.loads((self.trip_root/'settings/google-calendar.json').read_text())
                configured=bool(token.get('refresh_token') and config.get('calendar_id') and config['calendar_id']!='primary')
            except (OSError, ValueError):configured=False
            routes = calendar_routes(config) if configured else dict.fromkeys(CALENDAR_KEYS)
            pending = sum(self._google_pending(desired.get(k), rows.get(k, {}), routes)
                          for k in set(desired) | set(rows))
            return dict(status='unreflected' if pending or not configured else 'synced',pending=pending,
                        reason='authentication_required' if not configured else next((r['error'] for r in rows.values() if r['error']),None))
        except GoogleError as exc:
            return dict(status='unreflected', reason=str(exc), pending=0)
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
            routes = calendar_routes(client.config)
            pinned_routes = {'calendar_id': routes['event']}
            if routes['trip'] != routes['event']:
                pinned_routes.update(trip_calendar_id=routes['trip'], todo_calendar_id=routes['todo'])
            with sqlite3.connect(self.db_path) as c:
                pinned = dict(c.execute('SELECT key, value FROM google_calendar_meta'))
                if any(pinned_routes.get(key) != value for key, value in pinned.items()
                       if key in CALENDAR_KEYS.values()):
                    return dict(self.google_status(), reason='calendar_id_conflict', status='unreflected')
                c.executemany('INSERT OR IGNORE INTO google_calendar_meta VALUES (?,?)', pinned_routes.items())
            for key in sorted(set(rows) | set(desired)):
                body = desired.get(key)
                old = rows.get(key, {})
                if not reconcile and not self._google_pending(body, old, routes):
                    continue
                try:
                    self._sync_google_event(client, key, body, old, routes)
                except GoogleError as exc:
                    with sqlite3.connect(self.db_path) as c:
                        c.execute('UPDATE google_events SET error=? WHERE cal_key=?', (str(exc), key))
                    if str(exc) in ('authentication_required', 'http_401', 'http_403'):
                        break
            return self.google_status()
        except GoogleError as exc:
            return dict(status='unreflected', reason=str(exc), pending=0)
        except Exception:
            return dict(status='unreflected',reason='delivery_failed',pending=0)
        finally:os.close(fd)

    def _sync_google_event(self, client, key, body, old, routes):
        reference = body.get('_external_reference', {}) if body else {}
        kind = body.get('_calendar_kind') if body else None
        current = (old.get('calendar_id') or routes['event']) if old else routes.get(kind, routes['event'])
        target = routes[kind] if kind else (old.get('moving_to') or current)
        identity = old.get('event_id') or ('cal' + uuid4().hex)
        source_path = event_base(current) + '/' + identity
        moving = target != current
        if not old:
            with sqlite3.connect(self.db_path) as c:
                c.execute('INSERT INTO google_events (cal_key,event_id,lower_date,calendar_id) VALUES (?,?,?,?)',
                          (key, identity, today(), current))
        elif moving:
            with sqlite3.connect(self.db_path) as c:
                c.execute('UPDATE google_events SET moving_to=? WHERE cal_key=?', (target, key))

        def projection(calendar_id, path):
            if reference.get('calendar_id') == calendar_id and reference.get('event_id') == identity:
                return None
            return owned_event(client, path, key)

        if not reference or old:
            source = projection(current, source_path)
            source_active = source and source.get('status') != 'cancelled'
            destination_base = event_base(target)
            destination_path = destination_base + '/' + identity
            remote = projection(target, destination_path) if moving else source
            active = remote and remote.get('status') != 'cancelled'
            if kind:
                payload = {field: value for field, value in body.items() if field != '_calendar_kind'}
                if active:
                    client.request('PUT', destination_path, dict(payload, status='confirmed'))
                else:
                    if moving and remote and remote.get('status') == 'cancelled':
                        raise GoogleError('destination_cancelled')
                    if not moving and (remote or old.get('applied_hash') == self._google_hash(None)):
                        identity = 'cal' + uuid4().hex
                        with sqlite3.connect(self.db_path) as c:
                            c.execute('UPDATE google_events SET event_id=? WHERE cal_key=?', (identity, key))
                    try:
                        client.request('POST', destination_base, dict(payload, id=identity))
                    except GoogleError as exc:
                        if str(exc) != 'http_409':
                            raise
                        raise GoogleError('reconciliation_required') from None
            elif active:
                client.request('DELETE', destination_path)
            if moving and source_active:
                client.request('DELETE', source_path)

        with sqlite3.connect(self.db_path) as c:
            c.execute('UPDATE google_events SET calendar_id=?,moving_to=NULL,applied_hash=?,error=NULL WHERE cal_key=?',
                      (target, self._google_hash(body), key))
