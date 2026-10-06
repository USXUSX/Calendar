"""Finite-window recurrence with stable occurrence IDs and explicit exceptions."""
from .google_calendar import after_save
import calendar
import copy
import json
from datetime import date, timedelta, datetime, timezone
from uuid import uuid4
from .errors import ValidationError, ConflictError, NotFoundError
from .schedule import day
from .schedule_chat import request_id, encoded


def rule(value):
    if not isinstance(value,dict) or set(value)-{'frequency','start','until','weekdays','month_day'}:
        raise ValidationError('invalid_recurrence_rule')
    result=copy.deepcopy(value);frequency=result.get('frequency');day(result.get('start'))
    if frequency not in ('daily','weekly','monthly','month_end','yearly'):
        raise ValidationError('invalid_recurrence_frequency')
    if result.get('until') is not None:
        day(result['until'])
        if result['until']<result['start']:raise ValidationError('invalid_recurrence_end')
    if frequency=='weekly':
        days=result.get('weekdays')
        if not isinstance(days,list) or not days or any(type(x)!=int or x<0 or x>6 for x in days) or len(set(days))!=len(days):
            raise ValidationError('invalid_weekdays')
        result['weekdays']=sorted(days)
    elif 'weekdays' in result:raise ValidationError('unexpected_weekdays')
    if frequency=='monthly':
        if type(result.get('month_day'))!=int or not 1<=result['month_day']<=31:raise ValidationError('invalid_month_day')
    elif 'month_day' in result:raise ValidationError('unexpected_month_day')
    return result


def matches(segment, anchor):
    r=segment['rule'];d=date.fromisoformat(anchor)
    if anchor<max(segment['from'],r['start']) or anchor>min(segment.get('until') or '9999-12-31',r.get('until') or '9999-12-31'):return False
    return r['frequency']=='daily' or (r['frequency']=='weekly' and (d.weekday()+1)%7 in r['weekdays']) or (r['frequency']=='monthly' and d.day==r['month_day']) or (r['frequency']=='month_end' and d.day==calendar.monthrange(d.year,d.month)[1]) or (r['frequency']=='yearly' and (d.month,d.day)==(date.fromisoformat(r['start']).month,date.fromisoformat(r['start']).day))


def occurrence_id(series_id, anchor):return 'rec:'+series_id+':'+anchor


def split_id(identity):
    if not isinstance(identity,str):raise ValidationError('invalid_occurrence_id')
    parts=identity.split(':')
    if len(parts)!=3 or parts[0]!='rec':raise ValidationError('invalid_occurrence_id')
    day(parts[2]);return parts[1],parts[2]


def revision(row):return 'series:'+row['id']+':'+str(row['revision'])


def template(segment, anchor, kind):
    values=copy.deepcopy(segment['values']);field='start_date' if kind=='event' else 'due_date'
    if kind=='event' and values.get('end_date'):
        offset=(date.fromisoformat(values['end_date'])-date.fromisoformat(values[field])).days
        try:values['end_date']=(date.fromisoformat(anchor)+timedelta(days=offset)).isoformat()
        except OverflowError:raise ValidationError('recurrence_date_overflow') from None
    values[field]=anchor
    return values


class RecurrenceMixin:
    def _series(self,c,identity):
        row=c.execute('SELECT * FROM schedule_series WHERE id=?',(identity,)).fetchone()
        if row is None:raise NotFoundError('series_not_found')
        return dict(row),json.loads(row['data_json'])

    def get_series(self,identity):
        with self._read() as c:
            row,data=self._series(c,identity)
            return dict(series_id=identity,kind=row['kind'],revision=revision(row),**data)

    def _occurrence(self,row,data,anchor,include_deleted=False):
        exception=data['exceptions'].get(anchor)
        segment=next((s for s in data['segments'] if matches(s,anchor)),None)
        if exception is None and segment is None:raise NotFoundError('occurrence_not_found')
        if exception and exception.get('deleted'):
            if include_deleted:return dict(id=occurrence_id(row['id'],anchor),deleted=True)
            raise NotFoundError('occurrence_deleted')
        values=copy.deepcopy(exception['values']) if exception else template(segment,anchor,row['kind'])
        for key in ('trip_id','gmail_url','google_calendar_id','google_event_id'): values.setdefault(key,None)
        values.setdefault('category','general')
        item=dict(values,id=occurrence_id(row['id'],anchor),kind=row['kind'],series_id=row['id'],occurrence_date=anchor,revision=revision(row))
        if row['kind']=='todo':
            item.update(title=values['label'],start_date=values['due_date'],start_time=values.get('due_time'),end_date=None,end_time=None,completed_at=exception.get('completed_at') if exception else None)
        return item

    def get_occurrence(self,identity):
        sid,anchor=split_id(identity)
        with self._read() as c:
            row,data=self._series(c,sid)
            return self._occurrence(row,data,anchor)

    def _read_recurrence(self,c,start,end,include_completed):
        items=[]
        for raw in c.execute('SELECT * FROM schedule_series'):
            row=dict(raw);data=json.loads(row['data_json']);anchors=set(data['exceptions'])
            for segment in data['segments']:
                values=segment['values'];duration=0
                if row['kind']=='event' and values.get('end_date'):
                    duration=(date.fromisoformat(values['end_date'])-date.fromisoformat(values['start_date'])).days
                low=max(date.min.toordinal(),date.fromisoformat(start).toordinal()-duration,date.fromisoformat(segment['from']).toordinal(),date.fromisoformat(segment['rule']['start']).toordinal())
                high=min(date.fromisoformat(end).toordinal(),date.fromisoformat(segment.get('until') or '9999-12-31').toordinal(),date.fromisoformat(segment['rule'].get('until') or '9999-12-31').toordinal())
                for ordinal in range(low,high+1):
                    anchor=date.fromordinal(ordinal).isoformat()
                    if matches(segment,anchor):anchors.add(anchor)
            for anchor in sorted(anchors):
                try:item=self._occurrence(row,data,anchor)
                except NotFoundError:continue
                if item['start_date']<=end and (item.get('end_date') or item['start_date'])>=start and (include_completed or not item.get('completed_at')):items.append(item)
        return items

    def _change_recurrence(self,c,request):
        kind=request['kind'];action=request['action'];scope=request['scope'];identity=request.get('id');values=request.get('values',{})
        if not isinstance(values,dict):raise ValidationError('invalid_values')
        if kind not in ('event','todo') or action not in ('save','delete','complete') or scope not in ('series','this','following'):
            raise ValidationError('invalid_recurrence_operation')
        if scope=='series':
            if identity is not None or action!='save' or request.get('expected_revision') is not None:raise ValidationError('invalid_series_create')
            r=rule(request.get('recurrence'));v=self._validate_schedule_values(c,kind,values)
            field='start_date' if kind=='event' else 'due_date'
            if v[field]!=r['start']:raise ValidationError('template_date_must_equal_rule_start')
            sid=str(uuid4());row=dict(id=sid,kind=kind,revision=1)
            data=dict(segments=[dict(**{'from':r['start']},until=None,rule=r,values=v)],exceptions={})
            c.execute('INSERT INTO schedule_series VALUES (?,?,?,?)',(sid,kind,1,encoded(data)))
            return dict(series_id=sid,scope=scope,kind=kind,revision=revision(row),series=data)
        sid,anchor=split_id(identity);row,data=self._series(c,sid)
        if row['kind']!=kind:raise ValidationError('kind_mismatch')
        if request.get('expected_revision')!=revision(row):raise ConflictError('revision_conflict')
        item=self._occurrence(row,data,anchor)
        field='start_date' if kind=='event' else 'due_date'
        if scope=='this':
            if 'recurrence' in request:raise ValidationError('single_occurrence_has_no_rule')
            existing=data['exceptions'].get(anchor,{})
            current={key:item.get(key) for key in ({'title','start_date','start_time','end_date','end_time','notes','trip_id'} if kind=='event' else {'label','due_date','due_time','notes'})}
            if action=='delete':
                if values:raise ValidationError('delete_has_no_values')
                data['exceptions'][anchor]=dict(deleted=True)
            elif action=='complete':
                if kind!='todo' or set(values)!={'completed'} or type(values['completed'])!=bool:raise ValidationError('invalid_completion')
                data['exceptions'][anchor]=dict(values=current,completed_at=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') if values['completed'] else None)
            else:
                data['exceptions'][anchor]=dict(values=self._validate_schedule_values(c,kind,values,current),completed_at=existing.get('completed_at'))
        else:
            if action=='complete':raise ValidationError('completion_is_per_occurrence')
            segment=next((s for s in data['segments'] if s['from']<=anchor and (s['until'] is None or anchor<=s['until'])),None)
            if segment is None:raise ConflictError('occurrence_has_no_current_series_segment')
            previous=(date.fromisoformat(anchor)-timedelta(days=1)).isoformat() if anchor!='0001-01-01' else None
            keep=[]
            for s in data['segments']:
                if s['from']<anchor:
                    s['until']=min(s.get('until') or '9999-12-31',previous);keep.append(s)
            if action=='save':
                r=rule(request.get('recurrence',dict(segment['rule'],start=anchor)))
                if r['start']<anchor:raise ValidationError('following_rule_starts_before_target')
                current=template(segment,r['start'],kind)
                v=self._validate_schedule_values(c,kind,values,current)
                if v[field]!=r['start']:raise ValidationError('template_date_must_equal_rule_start')
                keep.append(dict(**{'from':anchor},until=None,rule=r,values=v))
            else:
                if values or 'recurrence' in request:raise ValidationError('delete_has_no_values_or_rule')
                data['exceptions']={d:e for d,e in data['exceptions'].items() if d<anchor}
            data['segments']=keep
        row['revision']+=1
        c.execute('UPDATE schedule_series SET revision=?,data_json=? WHERE id=?',(row['revision'],encoded(data),sid))
        result=dict(series_id=sid,occurrence_date=anchor,entity_id=identity,scope=scope,kind=kind,revision=revision(row),deleted=action=='delete')
        if scope=='this' and action!='delete':result['item']=self._occurrence(row,data,anchor)
        if scope=='following':result['series']=data
        return result

    @after_save
    def apply_recurrence_request(self,request):
        allowed={'request_id','kind','action','scope','id','expected_revision','values','recurrence'}
        if not isinstance(request,dict) or set(request)-allowed or not {'kind','action','scope'}<=set(request):raise ValidationError('invalid_recurrence_request')
        identity=request_id(request.get('request_id'));digest=self._digest(encoded(request).encode())
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE');self._recover_request_journal(c,identity)
            prior=c.execute('SELECT * FROM schedule_receipts WHERE request_id=?',(identity,)).fetchone()
            if prior:
                if prior['payload_hash']!=digest:raise ConflictError('request_id_payload_conflict')
                return dict(status='committed',resolution='replayed',receipt=json.loads(prior['receipt_json']))
            result=self._change_recurrence(c,request)
            receipt=dict(result,request_id=identity,receipt_id=str(uuid4()),status='committed',action=request['action'],committed_at=datetime.now(timezone.utc).isoformat())
            receipt.setdefault('entity_id',result['series_id'])
            c.execute('INSERT INTO schedule_receipts VALUES (?,?,?)',(identity,digest,encoded(receipt)))
        return dict(status='committed',resolution='new',receipt=receipt)
