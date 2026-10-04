"""RDC Trip requests using CAL's validation, adoption journal and SQLite receipts."""
from .google_calendar import after_save
import json
import os
from datetime import datetime, timezone
from uuid import uuid4
from .errors import ConflictError, ValidationError
from .schedule_chat import encoded, request_id
from .map_locations import complete


class TripChatMixin:
    def get_trip_command_context(self, trip_id):
        self.recover_trip_adoption(trip_id)
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            journal_path=self._journal_path(trip_id)
            if journal_path.exists():
                journal=json.loads(journal_path.read_text())
                if journal.get('kind') != 'rdc':
                    raise ConflictError('pending legacy adoption')
                self._recover_rdc_trip(c,trip_id,journal)
            return self._trip_command_context(c, trip_id)

    def _trip_command_context(self, c, trip_id):
        trip = self.get_effective_trip(trip_id)
        version = c.execute('SELECT version FROM trips WHERE id=?', (trip_id,)).fetchone()['version']
        instructions = [dict(r) for r in c.execute(
            "SELECT id,instruction FROM ai_instructions WHERE trip_id=? AND state='pending' ORDER BY created_at,id", (trip_id,))]
        revision = dict(trip_version=version, effective_hash=self._digest(self._canonical_json(trip)),
                        instructions_hash=self._digest(self._canonical_json(instructions)))
        for instruction in instructions:
            prefix = f'item:{trip_id}:'
            if instruction['id'].startswith(prefix):
                instruction['source_item_id'] = instruction['id'][len(prefix):].split(':', 1)[0]
        return dict(trip_id=trip_id, trip=trip, instructions=instructions, revision=revision)

    def lookup_chat_request(self, identity):
        request_id(identity)
        # Recover only the requested command, not unrelated legacy candidates.
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            self._recover_request_journal(c, identity)
        return self.lookup_schedule_request(identity)

    def _recover_request_journal(self, c, identity):
        for path in self._adoption_directory().glob('*.json'):
            journal = json.loads(path.read_text())
            if journal.get('kind') == 'rdc' and journal['receipt']['request_id'] == identity:
                self._recover_rdc_trip(c, path.stem, journal)

    @after_save
    def apply_trip_request(self, request):
        allowed = {'request_id','kind','action','trip','expected_revision','handled_instruction_ids','coordinate_results'}
        if not isinstance(request, dict) or set(request)-allowed or request.get('kind') != 'trip':
            raise ValidationError('invalid_trip_request')
        identity = request_id(request.get('request_id'))
        action = request.get('action')
        if action not in ('create','save'):
            raise ValidationError('invalid_trip_action')
        if not isinstance(request.get('trip'),dict) or not isinstance(request.get('coordinate_results'),dict):
            raise ValidationError('trip_and_coordinate_results_required')
        trip_id = request['trip'].get('id')
        path = self._trip_path(trip_id)
        handled = self._instruction_ids(request.get('handled_instruction_ids', []))
        expected = request.get('expected_revision')
        if action == 'create' and (expected is not None or handled):
            raise ValidationError('invalid_create')
        if action == 'save' and not isinstance(expected,dict):
            raise ValidationError('expected_revision_required')
        digest = self._digest(encoded(request).encode())
        self.lookup_chat_request(identity)
        self.recover_trip_adoption(trip_id)
        # Same SQLite lock as Frame writers protects revision, journal and receipt.
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            self._recover_request_journal(c, identity)
            prior = c.execute('SELECT * FROM schedule_receipts WHERE request_id=?',(identity,)).fetchone()
            if prior:
                if prior['payload_hash'] != digest:
                    raise ConflictError('request_id_payload_conflict')
                return dict(status='committed',resolution='replayed',receipt=json.loads(prior['receipt_json']))
            if self._journal_path(trip_id).exists():
                raise ConflictError('pending Trip adoption; lookup and retry')
            existing = None
            if action == 'create':
                if path.exists() or c.execute('SELECT 1 FROM trips WHERE id=?',(trip_id,)).fetchone():
                    raise ConflictError('Trip ID already exists')
                version, old_hash = 0, None
            else:
                context = self._trip_command_context(c, trip_id)
                if expected != context['revision']:
                    raise ConflictError('revision_conflict')
                existing = context['trip']
                version = expected['trip_version']
                old_hash = self._digest(path.read_bytes())
            candidate, _ = self._validated_candidate(trip_id, request['trip'])
            candidate, counts = complete(candidate,request['coordinate_results'],existing)
            candidate, payload = self._validated_candidate(trip_id,candidate)
            timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
            if action == 'create':
                c.execute("INSERT INTO trips (id,visibility,created_at,updated_at) VALUES (?,'owner',?,?)",(trip_id,timestamp,timestamp))
            else:
                c.execute('UPDATE direct_overrides SET active=0 WHERE trip_id=?',(trip_id,))
            self._validate_adoption_constraints(c,trip_id,candidate,handled)
            remaining = [dict(r) for r in c.execute("SELECT id,instruction FROM ai_instructions WHERE trip_id=? AND state='pending' ORDER BY created_at,id",(trip_id,)) if r['id'] not in handled]
            revision = dict(trip_version=version+1,effective_hash=self._digest(self._canonical_json(candidate)),
                            instructions_hash=self._digest(self._canonical_json(remaining)))
            receipt = dict(request_id=identity,receipt_id=str(uuid4()),status='committed',kind='trip',action=action,
                           entity_id=trip_id,committed_at=timestamp,previous_revision=expected,revision=revision,
                           coordinates=counts,handled_instruction_ids=list(handled),trip=candidate)
            journal = dict(version=4,kind='rdc',trip_id=trip_id,old_version=version,old_hash=old_hash,
                           candidate_hash=self._digest(payload),payload_hash=digest,receipt=receipt)
            staging = self._staging_path(trip_id,journal['candidate_hash'])
            self._write_file(staging,payload)
            self._write_journal(self._journal_path(trip_id),journal)
            # From here, failure means unknown until journal recovery/lookup.
            path.parent.mkdir(parents=True,exist_ok=True)
            if action == 'create':
                os.link(staging,path)  # Do not overwrite even an unregistered file.
            else:
                self._replace_current(staging,path)
            self._after_candidate_replace()
            self._finalize_rdc_trip(c,journal)
        with self._command() as c:
            c.execute('BEGIN IMMEDIATE')
            self._cleanup_rdc_journal(journal)
        return dict(status='committed',resolution='new',receipt=receipt)

    def _finalize_rdc_trip(self,c,journal):
        receipt=journal['receipt'];tid=journal['trip_id'];stamp=receipt['committed_at']
        c.execute("INSERT OR IGNORE INTO trips (id,visibility,created_at,updated_at) VALUES (?,'owner',?,?)",(tid,stamp,stamp))
        c.execute('UPDATE trips SET version=?,updated_at=? WHERE id=?',(journal['old_version']+1,stamp,tid))
        c.execute('UPDATE direct_overrides SET active=0 WHERE trip_id=?',(tid,))
        self._complete_chat_instructions(c,tid,receipt['handled_instruction_ids'],stamp)
        c.execute('INSERT INTO schedule_receipts VALUES (?,?,?)',(receipt['request_id'],journal['payload_hash'],encoded(receipt)))

    def _cleanup_rdc_journal(self,journal):
        path=self._journal_path(journal['trip_id'])
        if not path.exists() or json.loads(path.read_text()) != journal:
            return
        self._remove_adoption_file(self._staging_path(journal['trip_id'],journal['candidate_hash']))
        self._remove_adoption_file(self._journal_path(journal['trip_id']))

    def _recover_rdc_trip(self,c,trip_id,journal):
        if journal['trip_id'] != trip_id or journal['version'] != 4:
            raise ConflictError('invalid RDC adoption journal')
        prior=c.execute('SELECT * FROM schedule_receipts WHERE request_id=?',(journal['receipt']['request_id'],)).fetchone()
        if prior:
            if prior['payload_hash'] != journal['payload_hash'] or json.loads(prior['receipt_json']) != journal['receipt']:
                raise ConflictError('receipt conflicts with adoption journal')
            status='adopted'
        else:
            path=self._trip_path(trip_id)
            current=self._digest(path.read_bytes()) if path.exists() else None
            row=c.execute('SELECT version FROM trips WHERE id=?',(trip_id,)).fetchone()
            version=row['version'] if row else 0
            if version != journal['old_version']:
                raise ConflictError('Trip changed during recovery')
            if current == journal['candidate_hash']:
                self._finalize_rdc_trip(c,journal)
                status='adopted'
            elif current == journal['old_hash']:
                status='not_adopted'
            else:
                raise ConflictError('Trip file conflicts with adoption journal')
        # Commit before cleanup: a second recovery can always find the receipt.
        c.commit()
        c.execute('BEGIN IMMEDIATE')
        self._cleanup_rdc_journal(journal)
        return dict(status=status,trip_id=trip_id,recovered=True)
