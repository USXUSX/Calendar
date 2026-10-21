"""CAL sightseeing content and visits, with legacy castle records as the visit authority."""
import hashlib
import json
import math
from datetime import date, datetime, timezone
from urllib.parse import urlsplit
from uuid import uuid4
from .castles import item as castle_item, validate_record
from .errors import ConflictError, NotFoundError, ValidationError
from .schedule_chat import encoded, request_id

MASTER = {'name', 'prefecture', 'city', 'longitude', 'latitude'}
CONTENT = MASTER | {'categories', 'aliases', 'related_ids', 'summary', 'description', 'tags', 'sources', 'seasons', 'image', 'updated_at'}
VISIT = {'visited', 'visit_date', 'comment'}


def extend_places(c):
    c.execute('CREATE TABLE IF NOT EXISTS sightseeing_places (id INTEGER PRIMARY KEY, data_json TEXT NOT NULL, record_json TEXT NOT NULL, version INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS place_receipts (request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, receipt_json TEXT NOT NULL)')


def place_id(value):
    if type(value) is not int or value < 1:
        raise ValidationError('invalid_place_id')
    return value


def iso_day(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (ValueError, TypeError):
        raise ValidationError('invalid_source_date') from None


def url(value):
    if not isinstance(value, str) or urlsplit(value).scheme not in ('http', 'https') or not urlsplit(value).netloc:
        raise ValidationError('invalid_source_url')


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError('nonempty_text_required')


def validate_content(data, identity):
    if set(data) != CONTENT:
        raise ValidationError('invalid_place_content')
    for key in ('name', 'prefecture', 'city'):
        text(data[key])
    for key, limit in (('longitude', 180), ('latitude', 90)):
        v = data[key]
        if type(v) not in (int, float) or not math.isfinite(v) or not -limit <= v <= limit:
            raise ValidationError('invalid_coordinates')
    if not isinstance(data['categories'], list) or not data['categories']:
        raise ValidationError('categories_required')
    for category in data['categories']: text(category)
    if ('castle' in data['categories']) != (identity <= 100):
        raise ValidationError('castle_category_reserved_for_existing_100')
    if not isinstance(data['aliases'], list) or not all(isinstance(x, str) and x.strip() for x in data['aliases']):
        raise ValidationError('invalid_aliases')
    if not isinstance(data['related_ids'], list): raise ValidationError('invalid_related_ids')
    for related in data['related_ids']:
        place_id(related)
        if related == identity: raise ValidationError('self_relation')
    for key in ('summary', 'description'):
        if not isinstance(data[key], str): raise ValidationError('invalid_description')
    iso_day(data['updated_at'])
    if not isinstance(data['sources'], list) or not data['sources']: raise ValidationError('sources_required')
    for s in data['sources']:
        text(s['label']); url(s['url']); iso_day(s['checked_at'])
    if not isinstance(data['tags'], list): raise ValidationError('invalid_tags')
    for t in data['tags']:
        text(t['label']); url(t['source_url'])
    if not isinstance(data['seasons'], list): raise ValidationError('invalid_seasons')
    for s in data['seasons']:
        if s['category'] not in data['categories']: raise ValidationError('season_category_missing')
        text(s['typical']); url(s['source_url']); iso_day(s['checked_at'])
        if not isinstance(s['annual'], list): raise ValidationError('invalid_annual')
        for a in s['annual']:
            if type(a['year']) is not int or a['kind'] not in ('actual', 'forecast', 'unannounced', 'unverified'):
                raise ValidationError('invalid_annual_kind')
            text(a['text']); url(a['source_url']); iso_day(a['checked_at'])
    image = data['image']
    if image is not None:
        if type(image['reusable']) is not bool: raise ValidationError('invalid_image_permission')
        for key in ('url', 'source_url', 'license_url'): url(image[key])
        for key in ('credit', 'license', 'conditions', 'captured_at', 'changes'): text(image[key])
        iso_day(image['checked_at'])


def content_defaults(master, identity):
    return dict(**{k: master[k] for k in MASTER}, categories=['castle'] if identity <= 100 else [],
                aliases=[], related_ids=[], summary='', description='', tags=[], sources=[], seasons=[], image=None, updated_at=None)


def read_item(c, identity):
    row = c.execute('SELECT * FROM sightseeing_places WHERE id=?', (identity,)).fetchone()
    castle = c.execute('SELECT * FROM castles WHERE id=?', (identity,)).fetchone() if identity <= 100 else None
    if not row and not castle: raise NotFoundError('place_not_found')
    legacy = castle_item(castle) if castle else None
    content = json.loads(row['data_json']) if row else content_defaults(legacy, identity)
    record = {k: legacy[k] for k in VISIT} if castle else json.loads(row['record_json'])
    version = row['version'] if row else 0
    return dict(id=identity, **content, **record, castle_id=identity if castle else None,
                revision=f"place:{identity}:{version}:{castle['version'] if castle else 0}")


class PlacesMixin:
    def list_places(self):
        with self._read() as c:
            ids = c.execute('SELECT id FROM castles UNION SELECT id FROM sightseeing_places ORDER BY id').fetchall()
            return [read_item(c, r[0]) for r in ids]

    def get_place(self, identity):
        place_id(identity)
        with self._read() as c: return read_item(c, identity)

    def lookup_place_request(self, identity):
        request_id(identity)
        with self._read() as c:
            row = c.execute('SELECT receipt_json FROM place_receipts WHERE request_id=?', (identity,)).fetchone()
        return dict(status='committed', resolution='lookup', receipt=json.loads(row[0])) if row else dict(status='not_found', request_id=identity)

    def apply_place_request(self, request):
        if not isinstance(request, dict) or set(request) != {'request_id', 'id', 'expected_revision', 'values'}:
            raise ValidationError('invalid_place_request')
        rid = request_id(request['request_id']); identity = place_id(request['id']); values = request['values']
        if not isinstance(values, dict) or not values or set(values) - (CONTENT | VISIT):
            raise ValidationError('invalid_place_values')
        if request['expected_revision'] is not None and not isinstance(request['expected_revision'], str):
            raise ValidationError('invalid_expected_revision')
        digest = hashlib.sha256(encoded(request).encode()).hexdigest()
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT * FROM place_receipts WHERE request_id=?', (rid,)).fetchone()
            if prior:
                if prior['payload_hash'] != digest: raise ConflictError('request_id_payload_conflict')
                return dict(status='committed', resolution='replayed', receipt=json.loads(prior['receipt_json']))
            try: old = read_item(c, identity)
            except NotFoundError: old = None
            if (old['revision'] if old else None) != request['expected_revision']:
                raise ConflictError('revision_conflict')
            if not old and identity <= 100: raise ValidationError('castle_master_required')
            if old:
                content = {k: old[k] for k in CONTENT}
                record = {k: old[k] for k in VISIT}
            else:
                if not MASTER <= set(values): raise ValidationError('place_master_required')
                content = content_defaults(values, identity)
                record = dict(visited=False, visit_date=None, comment='')
            content.update({k: v for k, v in values.items() if k in CONTENT})
            record.update({k: v for k, v in values.items() if k in VISIT})
            if identity <= 100 and any(content[k] != old[k] for k in MASTER):
                raise ValidationError('castle_master_read_only')
            # Visit-only edits also work for the 95 castles without an introduction.
            if set(values) & CONTENT or not old:
                try: validate_content(content, identity)
                except (KeyError, TypeError): raise ValidationError('invalid_place_content') from None
            validate_record(record)
            others = [read_item(c, r[0]) for r in c.execute('SELECT id FROM castles UNION SELECT id FROM sightseeing_places') if r[0] != identity]
            own_names = {content['name'], *content['aliases']}
            for other in others:
                if content['prefecture'] == other['prefecture'] and (own_names & {other['name'], *other['aliases']} or (content['longitude'], content['latitude']) == (other['longitude'], other['latitude'])):
                    raise ConflictError('duplicate_place_use_existing_id')
            known = {o['id'] for o in others}
            if set(content['related_ids']) - known: raise ValidationError('related_place_not_found')
            if identity <= 100 and set(values) & VISIT:
                c.execute('UPDATE castles SET record_json=?, version=version+1 WHERE id=?', (encoded(record), identity))
            c.execute('INSERT INTO sightseeing_places VALUES (?,?,?,1) ON CONFLICT(id) DO UPDATE SET data_json=excluded.data_json, record_json=excluded.record_json, version=sightseeing_places.version+1',
                      (identity, encoded(content), encoded(record)))
            saved = read_item(c, identity)
            receipt = dict(status='committed', request_id=rid, receipt_id=str(uuid4()), entity_id=identity,
                           committed_at=datetime.now(timezone.utc).isoformat(), previous_revision=old['revision'] if old else None,
                           revision=saved['revision'], item=saved)
            c.execute('INSERT INTO place_receipts VALUES (?,?,?)', (rid, digest, encoded(receipt)))
        return dict(status='committed', resolution='new', receipt=receipt)
