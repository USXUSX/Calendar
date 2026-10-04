"""Request/receipt boundary for the existing RDC transport; CAL remains authoritative."""
from .google_calendar import after_save
import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from .errors import ConflictError, NotFoundError, ValidationError
from .schedule import schedule_revision


def request_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,127}', value):
        raise ValidationError('invalid_request_id')
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def table(kind):
    if kind not in ('event', 'todo'):
        raise ValidationError('invalid_kind')
    return 'events' if kind == 'event' else 'todos'


class ScheduleChatMixin:
    def get_schedule_item(self, kind, item_id):
        if isinstance(item_id,str) and item_id.startswith("rec:"):
            item=self.get_occurrence(item_id)
            if item["kind"]!=kind:raise ValidationError("kind_mismatch")
            return dict(kind=kind,item=item,revision=item["revision"])
        name = table(kind)
        with self._read() as c:
            row = c.execute(f'SELECT * FROM {name} WHERE id=?', (item_id,)).fetchone()
            if row is None:
                raise NotFoundError('item_not_found')
            return dict(kind=kind, item=dict(row), revision=schedule_revision(row))

    def lookup_schedule_request(self, identity):
        request_id(identity)
        with self._read() as c:
            prior = c.execute('SELECT receipt_json FROM schedule_receipts WHERE request_id=?', (identity,)).fetchone()
        if prior is None:
            return dict(status='not_found', request_id=identity)
        return dict(status='committed', resolution='lookup', receipt=json.loads(prior[0]))

    @after_save
    def apply_schedule_request(self, request):
        if not isinstance(request, dict) or set(request) - {'request_id', 'kind', 'action', 'id', 'expected_revision', 'values'}:
            raise ValidationError('invalid_request')
        identity = request_id(request.get('request_id'))
        kind, action = request.get('kind'), request.get('action')
        name = table(kind)
        if action not in ('save', 'delete', 'complete'):
            raise ValidationError('invalid_action')
        item_id, expected = request.get('id'), request.get('expected_revision')
        if item_id is not None and (not isinstance(item_id, str) or not item_id):
            raise ValidationError('invalid_item_id')
        if item_id is None and (action != 'save' or expected is not None):
            raise ValidationError('invalid_create')
        if item_id is not None and (not isinstance(expected, str) or not expected):
            raise ValidationError('expected_revision_required')
        values = request.get('values', {})
        if not isinstance(values, dict) or (action == 'delete' and values):
            raise ValidationError('invalid_values')
        payload = dict(kind=kind, action=action, id=item_id, expected_revision=expected, values=values)
        try:
            digest = hashlib.sha256(encoded(payload).encode('utf-8')).hexdigest()
        except (TypeError, ValueError):
            raise ValidationError('invalid_values') from None
        # The same lock covers receipt lookup, revision comparison, mutation and receipt.
        # Reuse the CAL schedule implementation, never a second independent write path.
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            self._recover_request_journal(c, identity)
            prior = c.execute('SELECT payload_hash,receipt_json FROM schedule_receipts WHERE request_id=?', (identity,)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    raise ConflictError('request_id_payload_conflict')
                return dict(status='committed', resolution='replayed', receipt=json.loads(prior['receipt_json']))
            old = None
            if item_id is not None:
                row = c.execute(f'SELECT * FROM {name} WHERE id=?', (item_id,)).fetchone()
                if row is None:
                    raise NotFoundError('item_not_found')
                old = dict(row)
                if schedule_revision(old) != expected:
                    raise ConflictError('revision_conflict')
            item = self._change_schedule(c, kind, action, item_id, values)
            receipt = dict(request_id=identity, receipt_id=str(uuid4()), status='committed',
                           kind=kind, action=action, entity_id=item['id'],
                           committed_at=datetime.now(timezone.utc).isoformat(),
                           previous_revision=expected, revision=None if action=='delete' else schedule_revision(item),
                           deleted=action=='delete', item=old if action=='delete' else item)
            c.execute('INSERT INTO schedule_receipts VALUES (?,?,?)', (identity, digest, encoded(receipt)))
        # _command has committed before a successful response becomes observable.
        return dict(status='committed', resolution='new', receipt=receipt)
