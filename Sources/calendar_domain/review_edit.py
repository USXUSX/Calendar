"""Item sheet commands for the Calendar #116 review."""
from uuid import NAMESPACE_URL, uuid4, uuid5
from .errors import ValidationError
from scripts.validate_trip import validate_value, semantic_errors


def edit_item(domain, command_id, trip_id, source_type, source_item_id, changes):
    from .service import _now
    paths = dict(status='/status', start='/time/start', end='/time/end',
                 time_mode='/time/mode', duration_minutes='/time/durationMinutes')
    if source_type == 'scheduleItem':
        paths.update(category='/category', title='/action', normal_comment='/summary', selection='/placeSelection/selection',
                     candidate_judgments='/candidateJudgments')
        extra = {'place', 'ai_instruction', 'adopt_place_id'}
    else:
        paths.update(important='/important', transport_mode='/mode', service_name='/serviceName')
        extra = {'from_place', 'to_place', 'ai_instruction'}
    extra.update({'show_duration', 'important_comments'})
    if set(changes) - set(paths) - extra:
        raise ValidationError('編集項目を確認してください。')
    with domain._command() as connection:
        connection.execute('BEGIN IMMEDIATE')
        trip = domain.get_effective_trip(trip_id)
        matches = domain._item_matches(trip, source_item_id)
        if len(matches) != 1 or (source_type == 'transport') != (matches[0] in trip['transports']):
            raise ValidationError('編集対象を確認してください。')
        item = matches[0]
        edits = [(source_item_id, paths[k], v) for k,v in changes.items() if k in paths]
        for field in extra - {'ai_instruction', 'show_duration', 'adopt_place_id', 'important_comments'}:
            if field not in changes:
                continue
            supplied = changes[field]
            if supplied is None and field == 'place':
                edits.append((source_item_id, '/placeSelection/selection', []))
                continue
            if not isinstance(supplied, dict) or not isinstance(supplied.get('name'), str) or not supplied['name'].strip():
                raise ValidationError('場所名を入力してください。')
            identity = supplied.get('id')
            existing = next((p for p in trip['places'] if p['id'] == identity), None)
            if existing and existing['name'] == supplied['name']:
                pass
            else:
                identity = 'place-' + uuid5(NAMESPACE_URL, f'{trip_id}:{command_id}:{field}').hex
                place = dict(id=identity, name=supplied['name'].strip(), summary=None, category='other',
                             rating=None, address=supplied.get('address'), location=supplied.get('location'), urls=supplied.get('urls', []), officialUrl=supplied.get('officialUrl'))
                edits.append((trip_id, '/places/@' + identity, place))
            if field == 'place':
                ids = list(item['placeSelection']['candidatePlaceIds'])
                if identity not in ids: ids.append(identity)
                edits.extend([(source_item_id, '/placeSelection/candidatePlaceIds', ids),
                              (source_item_id, '/placeSelection/selection', [identity])])
            else:
                edits.append((source_item_id, '/fromPlaceId' if field == 'from_place' else '/toPlaceId', identity))
        if 'adopt_place_id' in changes:
            pid = changes['adopt_place_id']
            if not isinstance(pid, str) or pid not in item['placeSelection']['candidatePlaceIds'] or set(changes) != {'adopt_place_id'}:
                raise ValidationError('正式採用する候補を確認してください。')
            place = next(p for p in trip['places'] if p['id'] == pid)
            title = item['action']
            old_names = [p['name'] for p in trip['places'] if p['id'] in item['placeSelection']['selection']]
            old_name = next((name for name in sorted(old_names, key=len, reverse=True) if name in title), None)
            if old_name:
                title = title.replace(old_name, place['name'])
            elif place['name'] not in title:
                title = place['name'] + 'で' + (title.split('で', 1)[1] if 'で' in title else title)
            edits.extend([(source_item_id, '/placeSelection/selection', [pid]),
                          (source_item_id, '/action', title)])
        if 'candidate_judgments' in changes:
            votes = changes['candidate_judgments']
            if not isinstance(votes, dict) or set(votes) - set(item['placeSelection']['candidatePlaceIds']) or any(v not in {'ok','ng'} for v in votes.values()):
                raise ValidationError('候補のOK/NGを確認してください。')
        if 'important_comments' in changes:
            from .trip_detail import important_comment_fields
            allowed = {field['source_id'] for field in important_comment_fields(item, trip['bookings'])}
            comments = changes['important_comments']
            if not isinstance(comments, dict) or set(comments) - allowed or any(not isinstance(v, str) for v in comments.values()):
                raise ValidationError('重要コメントの保存先と文字列を確認してください。')
            edits.extend((identity, '/importantComment' if identity == source_item_id else '/notes', comment or None)
                         for identity, comment in comments.items())
        if 'show_duration' in changes or changes.get('time_mode') in {'none', 'undecided'}:
            from .trip_detail import input_time_spec
            time = input_time_spec(changes.get('start', item['time']['start']),
                                   changes.get('end', item['time']['end']), changes.get('show_duration', False), changes.get('time_mode'))
            edits = [(target, path, value) for target, path, value in edits if not path.startswith('/time/')]
            edits.extend((source_item_id, '/time/' + field, value) for field, value in time.items())
        elif changes.get('time_mode') == 'range':
            start = changes.get('start')
            duration = changes.get('duration_minutes')
            if not isinstance(start, str) or type(duration) is not int or duration <= 0:
                raise ValidationError('開始時刻と滞在時間を入力してください。')
            try:
                hours, minutes = map(int, start.split(':'))
                total = hours * 60 + minutes + duration
                end = f'{total // 60 % 24:02d}:{total % 60:02d}'
            except ValueError as error:
                raise ValidationError('開始時刻を確認してください。') from error
            edits = [(target,path,value) for target,path,value in edits if path != '/time/end']
            edits.append((source_item_id, '/time/end', end))
        for target,path,value in edits: domain._apply_value(trip,target,path,value)
        errors = validate_value(trip, domain._trip_schema)
        if not errors:
            errors = semantic_errors(trip)
        if errors:
            raise ValidationError('予定を保存できません: ' + '\n'.join(errors))
        instruction = changes.get('ai_instruction')
        if 'ai_instruction' in changes:
            if not isinstance(instruction, str): raise ValidationError('AI指示は文字列で入力してください。')
            target_id = f'item:{trip_id}:{source_item_id}'
            pending = [row for row in connection.execute(
                "SELECT id, instruction FROM ai_instructions WHERE trip_id=? AND state='pending'", (trip_id,))
                if row['id'] == target_id or row['id'].startswith(target_id + ':')]
            instruction = instruction.strip()
            # An unchanged sheet save preserves the pending instruction identity.
            if not (len(pending) == 1 and pending[0]['instruction'] == instruction):
                now = _now()
                for row in pending:
                    connection.execute("UPDATE ai_instructions SET state='cancelled', updated_at=? WHERE id=?",
                                       (now, row['id']))
                if instruction:
                    identity = target_id + ':' + uuid4().hex
                    connection.execute("INSERT INTO ai_instructions (id,trip_id,instruction,state,created_at,updated_at) VALUES (?,?,?,?,?,?)",
                                       (identity,trip_id,instruction,'pending',now,now))

        for target,path,value in edits:
            domain._store_trip_fields(connection,command_id,trip_id,target,{path:value},{path:path})
    return dict(trip=domain.get_effective_trip(trip_id), view=domain.get_trip_detail_view(trip_id), updated_fields=sorted(changes))
