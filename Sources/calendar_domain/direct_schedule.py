"""Small direct schedule operations; no search, AI or Working mutation."""
from uuid import NAMESPACE_URL, uuid5
from .errors import ConflictError, ValidationError
from scripts.validate_trip import validate_value, semantic_errors


def change(domain, command_id, trip_id, action, payload):
    domain._require_text(command_id, 'command_id')
    if not isinstance(payload, dict):
        raise ValidationError('予定の入力を確認してください。')
    with domain._command() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if domain._journal_path(trip_id).exists():
            raise ConflictError('pending Trip adoption')
        trip = domain.get_effective_trip(trip_id)
        day = next((d for d in trip['days'] if d['id'] == payload.get('day_id')), None)
        if day is None:
            raise ValidationError('対象日を確認してください。')
        entries = sorted(day['scheduleItems'] + [t for t in trip['transports'] if t['id'] in day['transportIds']],
                         key=lambda i: (i['order'], i['id']))
        changes = []
        if action == 'add':
            identity = 'item-' + uuid5(NAMESPACE_URL, f'calendar:direct:{trip_id}:{command_id}').hex
            if domain._item_matches(trip, identity):
                raise ConflictError('この予定は追加済みです。')
            if 'text' in payload:
                text = payload['text']
                if not isinstance(text, str):
                    raise ValidationError('貼付内容を確認してください。')
                review = domain.parse_chat_paste('旅行名: 1予定追加\n日付: ' + day['date'] + '\n' + text)
                from .chat_paste import build_import_trip
                if review['unresolved']:
                    raise ValidationError('未解決の行があります。貼付内容を修正してください。')
                draft = build_import_trip(review['draft'], command_id)
                if len(draft['days']) != 1 or len(draft['days'][0]['scheduleItems']) != 1 or draft['transports'] or draft['days'][0]['date'] != day['date']:
                    raise ValidationError('対象日の予定を1件だけ貼り付けてください。')
                item = draft['days'][0]['scheduleItems'][0]
                for place in draft['places']:
                    changes.append((trip_id, '/places/@' + place['id'], place))
            else:
                title, category = payload.get('title'), payload.get('category')
                if not isinstance(title, str) or not title.strip():
                    raise ValidationError('予定名を入力してください。')
                start, end = payload.get('start'), payload.get('end')
                from .trip_detail import input_time_spec
                item = dict(status=payload.get('status', 'undecided'), action=title, category=category, summary=payload.get('normal_comment'), details=[],
                            time=input_time_spec(start, end, payload.get('show_duration', False)),
                            placeSelection=dict(candidatePlaceIds=[], selection=[], minSelections=None, maxSelections=None))
                name = payload.get('place_name')
                if isinstance(name, str) and name.strip():
                    pid = 'place-' + uuid5(NAMESPACE_URL, f'calendar:direct:{trip_id}:{command_id}').hex
                    place = dict(id=pid,name=name,summary=None,category='other',rating=None,address=None,location=None,urls=[])
                    changes.append((trip_id, '/places/@' + pid, place))
                    item['placeSelection']['candidatePlaceIds'] = [pid]
                    item['placeSelection']['selection'] = [pid]
                else:
                    item['searchQuery'] = payload.get('search_query') or title
            item.update(id=identity, dayId=day['id'], order=max([i['order'] for i in entries] + [-1]) + 1)
            after = payload.get('after_item_id')
            if after is not None:
                index = next((n for n, entry in enumerate(entries) if entry['id'] == after), None)
                if index is None:
                    raise ConflictError('追加位置の予定が変わりました。再読込してください。')
                item['order'] = index + 1
                changes.extend((entry['id'], '/order', n if n <= index else n + 1)
                               for n, entry in enumerate(entries))
            changes.append((day['id'], '/scheduleItems/@' + identity, item))
        elif action == 'delete':
            identity = payload.get('source_item_id')
            item = next((i for i in entries if i['id'] == identity), None)
            if item is None:
                raise ValidationError('対象予定を確認してください。')
            # Do not silently detach a Todo from its referenced itinerary item.
            if connection.execute('SELECT 1 FROM todos WHERE trip_id = ? AND trip_item_id = ?', (trip_id, identity)).fetchone():
                raise ConflictError('この予定を参照するTodoを先に変更してください。')
            transport = identity in day['transportIds']
            changes.append((trip_id if transport else day['id'], ('/transports/@' if transport else '/scheduleItems/@') + identity, None))
            if transport:
                changes.append((day['id'], '/transportIds', [i for i in day['transportIds'] if i != identity]))
            connection.execute('UPDATE direct_overrides SET active = 0 WHERE trip_id = ? AND source_item_id = ?', (trip_id, identity))
        elif action == 'reorder':
            ids = payload.get('item_ids')
            if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids) or len(ids) != len(entries) or set(ids) != {i['id'] for i in entries}:
                raise ConflictError('予定一覧が変わりました。再読込してください。')
            changes.extend((identity, '/order', index) for index, identity in enumerate(ids))
        else:
            raise ValidationError('未知の予定操作です。')
        for target, path, value in changes:
            domain._apply_value(trip, target, path, value)
        if validate_value(trip, domain._trip_schema) + semantic_errors(trip):
            raise ValidationError('予定の時刻・カテゴリ・参照を確認してください。')
        for target, path, value in changes:
            domain._store_trip_fields(connection, command_id, trip_id, target, {path: value}, {path: path})
    return dict(view=domain.get_trip_detail_view(trip_id), trip=domain.get_effective_trip(trip_id))
