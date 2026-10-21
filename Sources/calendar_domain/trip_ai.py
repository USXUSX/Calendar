"""CAL Trip proposals: AI interpretation, deterministic review, explicit formal save.

No Working state, auto adoption, provider routing, or database authority in the UI.
"""
import copy
import json
from pathlib import Path
from uuid import uuid4

from .errors import ConflictError, ValidationError
from .map_locations import complete, prepare
from .schedule_chat import request_id


def changes(before, after, path=""):
    """Stable-ID object diffs, including exact old/new values for user review."""
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        result = []
        for key in sorted(before.keys() | after.keys()):
            result += changes(before.get(key), after.get(key), path + "/" + key)
        return result
    if isinstance(before, list) and isinstance(after, list) and all(
        isinstance(x, dict) and isinstance(x.get('id'), str) for x in before + after
    ):
        old = {x['id']: x for x in before}; new = {x['id']: x for x in after}
        result = []
        if list(old) != list(new):
            result.append(dict(path=path + '/順序・構成', before=list(old), after=list(new)))
        for key in dict.fromkeys([*old, *new]):
            result += changes(old.get(key), new.get(key), path + '/' + key)
        return result
    return [dict(path=path or '/', before=before, after=after)]


class TripAIMixin:
    def propose_trip_update(self, trip_id, expected_revision, instruction, transport=None):
        if not isinstance(instruction, str) or not instruction.strip():
            raise ValidationError('AI指示を入力してください。')
        context = self.get_trip_command_context(trip_id)
        if expected_revision != context['revision']:
            raise ConflictError('revision_conflict')
        if transport is None:
            import os
            from Sources.aig_trip_generation import command_transport
            try:
                argv = json.loads(os.environ.get('CAL_TRIP_AI_COMMAND', 'null'))
                if not isinstance(argv, list):
                    raise ValueError
                transport = command_transport(argv, 240)
            except (ValueError, TypeError):
                raise ValidationError('AI生成の実行設定がありません。CAL_TRIP_AI_COMMANDを設定してください。') from None
        identity = str(uuid4())
        baseline = context['trip']
        # Reuse only AIG's existing stateless complete-Trip transport envelope.
        # These compatibility fields do not read or write legacy Working state.
        package = dict(
            format='cal.complete-trip-regeneration.v1', trip_id=trip_id,
            authoritative_trip=copy.deepcopy(baseline), effective_trip=copy.deepcopy(baseline),
            working=dict(base_effective_revision=expected_revision,
                         current_effective_revision=expected_revision, stale=False),
            user_intent=dict(instruction=instruction, item_changes=[], temporary_items=[], day_instructions=[]),
            task=dict(instruction=instruction, rules=[
                'Apply only the requested changes. Preserve all unrelated data and stable IDs, bookings, adopted selections, locations and references.',
                'Do not invent facts, reservations or coordinates. Do not automatically adopt candidates.',
                'Return one complete Trip; CAL validates and the user approves before saving.']),
            schema=self._trip_schema,
            generation_guide=(Path(__file__).resolve().parents[2] / 'docs/trip-json-generation.md').read_text(),
        )
        envelope = dict(contract_version='cal.aig.complete-trip-generation.v1',
                        generation_id=identity, trip_id=trip_id, working_export_package=package)
        try:
            result = transport(envelope)
        except Exception:
            raise ValidationError('AI生成に失敗しました。旅程は変更していません。') from None
        if not isinstance(result, dict) or result.get('generation_id') != identity or result.get('trip_id') != trip_id:
            raise ValidationError('AI生成結果の識別情報が一致しません。')
        if result.get('status') != 'succeeded' or not isinstance(result.get('candidate'), dict):
            raise ValidationError('AI生成に失敗しました。旅程は変更していません。')
        candidate, _ = self._validated_candidate(trip_id, result['candidate'])
        # Resolve only within the proposal, without restoring old coordinates over
        # explicitly changed locations. No external lookup or invented coordinates.
        candidate, plan = prepare(candidate)
        attempts = {point['place_id']: None for point in plan if point['location'] is None and not point.get('skip_search')}
        candidate, _ = complete(candidate, attempts, require_attempts=True)
        candidate, _ = self._validated_candidate(trip_id, candidate)
        if self.get_trip_command_context(trip_id)['revision'] != expected_revision:
            raise ConflictError('revision_conflict')
        summary = changes(baseline, candidate)
        if not summary:
            raise ValidationError('変更はありません。指示を確認してください。')
        proposal = dict(proposal_id=identity, request_id=identity, trip_id=trip_id,
                        expected_revision=expected_revision, instruction=instruction, changes=summary)
        save_request = dict(request_id=identity, kind='trip', action='save', trip=candidate,
                            expected_revision=expected_revision, handled_instruction_ids=[], coordinate_results=attempts)
        # Persist the reviewed request locally so unknown-result lookup/resend also
        # survives a server restart. This is never a formal Trip or shared data.
        self._write_file(self._trip_ai_path(identity), self._canonical_json(dict(proposal=proposal, request=save_request)))
        return dict(status='proposed', **proposal)

    def _trip_ai_path(self, identity):
        request_id(identity)
        # Proposal identities are server-generated UUIDs, never client paths.
        from uuid import UUID
        try:
            if str(UUID(identity)) != identity:
                raise ValueError
        except (ValueError, TypeError, AttributeError):
            raise ValidationError('invalid_proposal_id') from None
        return self.trip_root / '.trip-ai' / (identity + '.json')

    def apply_trip_ai_update(self, request):
        if set(request) != {'request_id', 'trip_id', 'operation', 'expected_revision', 'values'}:
            raise ValidationError('invalid_trip_operation')
        values = request['values']
        if not isinstance(values, dict) or set(values) != {'proposal_id', 'confirmed'} or values['confirmed'] is not True:
            raise ValidationError('本人承認が必要です。')
        try:
            frozen = json.loads(self._trip_ai_path(values['proposal_id']).read_text())
        except (OSError, json.JSONDecodeError):
            raise ValidationError('変更案が見つかりません。再生成してください。') from None
        proposal = frozen['proposal']
        if any(request[k] != proposal[k] for k in ('request_id', 'trip_id', 'expected_revision')):
            raise ConflictError('proposal_identity_conflict')
        return self.apply_trip_request(frozen['request'], preserve_locations=False)
