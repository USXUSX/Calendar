"""CAL-owned hundred-castle master and one visit record per castle."""
import hashlib
import json
from datetime import date, datetime, timezone
from uuid import uuid4
from .errors import ConflictError, NotFoundError, ValidationError
from .schedule_chat import encoded, request_id


def extend_castles(c):
    c.execute('CREATE TABLE IF NOT EXISTS castles (id INTEGER PRIMARY KEY, master_json TEXT NOT NULL, record_json TEXT NOT NULL, version INTEGER NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS castle_receipts (request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, receipt_json TEXT NOT NULL)')


def validate_record(record):
    if set(record) != {'visited', 'visit_date', 'comment'} or type(record['visited']) is not bool:
        raise ValidationError('invalid_castle_record')
    value = record['visit_date']
    if value is not None:
        try:
            if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
                raise ValueError
        except (TypeError, ValueError):
            raise ValidationError('invalid_visit_date') from None
        if not record['visited']:
            raise ValidationError('unvisited_date_must_be_null')
    if not isinstance(record['comment'], str):
        raise ValidationError('invalid_comment')


def item(row):
    return dict(id=row['id'], **json.loads(row['master_json']), **json.loads(row['record_json']),
                revision=f"castle:{row['id']}:{row['version']}")


def castle_id(value):
    if type(value) is not int or not 1 <= value <= 100:
        raise ValidationError('invalid_castle_id')
    return value


class CastlesMixin:
    def list_castles(self):
        with self._read() as c:
            return [item(r) for r in c.execute('SELECT * FROM castles ORDER BY id')]

    def get_castle(self, identity):
        castle_id(identity)
        with self._read() as c:
            row = c.execute('SELECT * FROM castles WHERE id=?', (identity,)).fetchone()
            if row is None:
                raise NotFoundError('castle_not_found')
            return item(row)

    def lookup_castle_request(self, identity):
        request_id(identity)
        with self._read() as c:
            row = c.execute('SELECT receipt_json FROM castle_receipts WHERE request_id=?', (identity,)).fetchone()
        return dict(status='committed', resolution='lookup', receipt=json.loads(row[0])) if row else dict(status='not_found', request_id=identity)

    def apply_castle_request(self, request):
        if not isinstance(request, dict) or set(request) != {'request_id', 'id', 'expected_revision', 'values'}:
            raise ValidationError('invalid_castle_request')
        identity = request_id(request['request_id'])
        target = castle_id(request['id'])
        values = request['values']
        if not isinstance(values, dict) or not values or set(values) - {'visited', 'visit_date', 'comment'}:
            raise ValidationError('invalid_castle_values')
        if not isinstance(request['expected_revision'], str) or not request['expected_revision']:
            raise ValidationError('expected_revision_required')
        try:
            digest = hashlib.sha256(encoded(request).encode()).hexdigest()
        except (ValueError, TypeError):
            raise ValidationError('invalid_castle_request') from None
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            prior = c.execute('SELECT * FROM castle_receipts WHERE request_id=?', (identity,)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    raise ConflictError('request_id_payload_conflict')
                return dict(status='committed', resolution='replayed', receipt=json.loads(prior['receipt_json']))
            row = c.execute('SELECT * FROM castles WHERE id=?', (target,)).fetchone()
            if row is None:
                raise NotFoundError('castle_not_found')
            old = item(row)
            if old['revision'] != request['expected_revision']:
                raise ConflictError('revision_conflict')
            record = {**json.loads(row['record_json']), **values}
            validate_record(record)
            c.execute('UPDATE castles SET record_json=?, version=version+1 WHERE id=?', (encoded(record), target))
            saved = item(c.execute('SELECT * FROM castles WHERE id=?', (target,)).fetchone())
            receipt = dict(status='committed', request_id=identity, receipt_id=str(uuid4()), entity_id=target,
                           committed_at=datetime.now(timezone.utc).isoformat(), previous_revision=old['revision'],
                           revision=saved['revision'], item=saved)
            c.execute('INSERT INTO castle_receipts VALUES (?,?,?)', (identity, digest, encoded(receipt)))
        return dict(status='committed', resolution='new', receipt=receipt)
