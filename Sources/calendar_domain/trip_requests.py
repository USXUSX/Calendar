"""Versioned direct Trip commands, using the existing overrides and receipts."""
from datetime import datetime, timezone
import json
from uuid import uuid4
from .errors import ConflictError, ValidationError
from .google_calendar import after_save
from .schedule_chat import encoded, request_id


class TripRequestMixin:
    def get_trip_edit_view(self, trip_id):
        """The view and revision describe the same SQLite snapshot."""
        self.get_trip_command_context(trip_id)
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            if self._journal_path(trip_id).exists():
                raise ConflictError('pending Trip adoption; lookup and retry')
            self._trip_write_state.connection = c
            try:
                context = self._trip_command_context(c, trip_id)
                view = self.load_trip_detail_view(trip_id)
                return dict(view, revision=context['revision'])
            finally:
                self._trip_write_state.connection = None

    @after_save
    def apply_trip_operation(self, request):
        allowed = {'request_id', 'trip_id', 'operation', 'expected_revision', 'values'}
        if not isinstance(request, dict) or set(request) != allowed:
            raise ValidationError('invalid_trip_operation')
        identity = request_id(request['request_id'])
        tid, operation, values = request['trip_id'], request['operation'], request['values']
        self._trip_path(tid)
        if operation not in {'item', 'day', 'add', 'delete', 'reorder', 'location', 'instruction'}:
            raise ValidationError('invalid_trip_operation')
        if not isinstance(values, dict) or not isinstance(request['expected_revision'], dict):
            raise ValidationError('values_and_expected_revision_required')
        try:
            digest = self._digest(encoded(request).encode())
        except (TypeError, ValueError):
            raise ValidationError('invalid_trip_values') from None
        found = self.lookup_chat_request(identity)
        if found['status'] == 'committed':
            with self._read() as c:
                prior = c.execute('SELECT payload_hash FROM schedule_receipts WHERE request_id=?', (identity,)).fetchone()
            if prior['payload_hash'] != digest:
                raise ConflictError('request_id_payload_conflict')
            return dict(found, resolution='replayed')
        self.recover_trip_adoption(tid)
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            self._recover_request_journal(c, identity)
            prior = c.execute('SELECT * FROM schedule_receipts WHERE request_id=?', (identity,)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    raise ConflictError('request_id_payload_conflict')
                return dict(status='committed', resolution='replayed', receipt=json.loads(prior['receipt_json']))
            if self._journal_path(tid).exists():
                raise ConflictError('pending Trip adoption; lookup and retry')
            self._trip_write_state.connection = c
            try:
                before = self._trip_command_context(c, tid)['revision']
                if request['expected_revision'] != before:
                    raise ConflictError('revision_conflict')
                try:
                    if operation == 'item':
                        self.edit_trip_item(identity, tid, values['source_type'], values['source_item_id'], values['changes'])
                    elif operation == 'day':
                        self.edit_trip_day(identity, tid, values['day_id'], values['changes'])
                    elif operation in {'add', 'delete', 'reorder'}:
                        self.change_trip_schedule(identity, tid, operation, values)
                    elif operation == 'location':
                        self.save_map_location(identity, tid, values['place_id'], values['location'], values['expected_location'],
                                               values.get('googlePlaceId'), values.get('expected_name'))
                    else:
                        self.add_chat_instruction(identity, tid, values['instruction'])
                except (KeyError, TypeError):
                    raise ValidationError('invalid_trip_values') from None
                context = self._trip_command_context(c, tid)
                receipt = dict(request_id=identity, receipt_id=str(uuid4()), status='committed', kind='trip_operation',
                               action=operation, entity_id=tid, previous_revision=before, revision=context['revision'],
                               values=values, committed_at=datetime.now(timezone.utc).isoformat())
                if operation == 'instruction' or (operation == 'item' and 'ai_instruction' in values.get('changes', {})):
                    receipt['instructions_state'] = 'pending' if context['instructions'] else 'none'
                c.execute('INSERT INTO schedule_receipts VALUES (?,?,?)', (identity, digest, encoded(receipt)))
            finally:
                self._trip_write_state.connection = None
        return dict(status='committed', resolution='new', receipt=receipt)
