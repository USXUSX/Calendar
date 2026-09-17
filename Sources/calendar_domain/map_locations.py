"""Location import and edit rules. Search runs in the Maps browser client."""
import copy
from .errors import ConflictError, NotFoundError, ValidationError
from .trip_detail import build_trip_detail_view
from Sources.place_acquisition import valid_field


def identity(place):
    address = (place.get('address') or '').strip()
    return (place['name'].strip(), address) if address else place['id']


def prepare(trip, existing=None):
    candidate = copy.deepcopy(trip)
    saved = {p['id']: p for p in (existing or {}).get('places', []) if p['location'] is not None}
    for p in candidate['places']:
        if p['id'] in saved:
            copy_location(p, saved[p['id']])
    groups = {}
    for p in candidate['places']:
        groups.setdefault(identity(p), []).append(p)
    targets = {}
    days = {d['id']: d for d in candidate['days']}
    for day in build_trip_detail_view(candidate)['days']:
        area = ' '.join(a['name'] for a in days[day['day_id']].get('areas', []))
        for stop in day['map_stops']:
            for point in stop['points']:
                # Search the actual candidate Place even when Phase 1 displayed an area's coordinate.
                targets.setdefault(point['place_id'], area)
    plan = []
    for places in groups.values():
        selected = [p for p in places if p['id'] in targets]
        if not selected:
            continue
        p = selected[0]
        source = next((x for x in places if x['location'] is not None), {})
        location = source.get('location')
        if location is not None:
            for x in places:
                if x['location'] is None:
                    copy_location(x, source)
        hint = (p.get('address') or '').strip() or targets[p['id']]
        plan.append(dict(place_id=p['id'], name=p['name'], query=' '.join(filter(None, [p['name'].strip(), hint])),
                         location=copy.deepcopy(location), googlePlaceId=source.get('googlePlaceId'), place_ids=[x['id'] for x in places]))
    saved_days = {d['id']: d for d in (existing or {}).get('days', [])}
    for day in candidate['days']:
        saved_areas = {a['name']: a for a in saved_days.get(day['id'], {}).get('areas', []) if a['location'] is not None}
        for index, area in enumerate(day.get('areas', [])):
            if area['name'] in saved_areas:
                copy_location(area, saved_areas[area['name']])
            key = f"area:{day['id']}:{index}"
            plan.append(dict(place_id=key, place_ids=[key], name=area['name'], query=area['name'], location=area['location'], googlePlaceId=area.get('googlePlaceId')))
    return candidate, plan


def complete(trip, results=None, existing=None):
    candidate, plan = prepare(trip, existing)
    if results is not None and not isinstance(results, dict):
        raise ValidationError('座標検索結果は地点IDごとに指定してください。')
    results = results or {}
    places = {p['id']: p for p in candidate['places']}
    places.update({f"area:{d['id']}:{i}": a for d in candidate['days'] for i, a in enumerate(d.get('areas', []))})
    counts = dict(filled=0, missing=0, existing=0)
    for point in plan:
        if point['location'] is not None:
            counts['existing'] += 1
            continue
        resolved = fields(results.get(point['place_id']))
        if resolved['location'] is not None:
            for pid in point['place_ids']:
                if places[pid]['location'] is None:
                    places[pid].update(copy.deepcopy(resolved))
            counts['filled'] += 1
        else:
            counts['missing'] += 1
    return candidate, counts


def target(domain, trip_id, place_id):
    trip = domain.get_effective_trip(trip_id)
    _, plan = prepare(trip)
    point = next((p for p in plan if place_id in p['place_ids']), None)
    if point is None:
        place = next((p for p in trip['places'] if p['id'] == place_id), None)
        if place is not None:
            day = next((d for d in trip['days'] if any(place_id in item['placeSelection']['candidatePlaceIds'] for item in d['scheduleItems'])), trip['days'][0])
            point = inputs(domain, trip_id, day['id'], [place])[0]
            point.update(place_id=place_id, place_ids=[p['id'] for p in trip['places'] if identity(p) == identity(place)])
    if point is None:
        raise NotFoundError('地図表示対象の地点を確認してください。')
    return point


def save(domain, command_id, trip_id, place_id, location, expected_location, google_place_id=None, expected_name=None):
    domain._require_text(command_id, 'command_id')
    if location is None or not valid_field('location', location):
        raise ValidationError('緯度・経度の値を確認してください。')
    with domain._command() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if domain._journal_path(trip_id).exists():
            raise ConflictError('pending Trip adoption')
        point = target(domain, trip_id, place_id)
        if point['location'] != expected_location or (expected_name is not None and point['name'] != expected_name):
            raise ConflictError('位置が変更されています。再読み込みしてください。')
        values = fields(dict(location=location, googlePlaceId=google_place_id))
        for pid in point['place_ids']:
            if pid.startswith('area:'):
                _, day_id, index = pid.split(':')
                day = next(d for d in domain.get_effective_trip(trip_id)['days'] if d['id'] == day_id)
                areas = copy.deepcopy(day['areas'])
                areas[int(index)].update(values)
                domain._store_trip_fields(connection, command_id, trip_id, day_id, {'areas': areas}, {'areas': '/areas'})
            else:
                domain._store_trip_fields(connection, command_id, trip_id, pid, values, {'location': '/location', 'googlePlaceId': '/googlePlaceId'})
    return dict(status='saved', view=domain.get_trip_detail_view(trip_id))


def fields(result):
    """Accept legacy coordinate results and the Places coordinate/ID pair."""
    result = result if isinstance(result, dict) else {}
    location = result.get('location', result)
    if not valid_field('location', location):
        return dict(location=None, googlePlaceId=None)
    place_id = result.get('googlePlaceId')
    return dict(location=copy.deepcopy(location), googlePlaceId=place_id if isinstance(place_id, str) and place_id.strip() else None)


def inputs(domain, trip_id, day_id, points):
    """One query rule for areas and screen-entered places; saved coordinates win."""
    trip = domain.get_effective_trip(trip_id)
    day = next((d for d in trip['days'] if d['id'] == day_id), None)
    if day is None or not isinstance(points, list):
        raise ValidationError('日付と地点を確認してください。')
    places = {p['id']: p for p in trip['places']}
    plan = []
    for index, supplied in enumerate(points):
        if not isinstance(supplied, dict) or not isinstance(supplied.get('name'), str) or not supplied['name'].strip():
            raise ValidationError('場所名を入力してください。')
        saved = places.get(supplied.get('id'))
        if not saved or saved['name'] != supplied['name']:
            saved = next((a for a in day.get('areas', []) if supplied.get('area') and a['name'] == supplied['name']), None)
        source = saved or supplied
        hint = (source.get('address') or '').strip() or ('' if supplied.get('area') else ' '.join(a['name'] for a in day.get('areas', [])))
        plan.append(dict(place_id=str(index), name=source['name'], query=' '.join(filter(None, [source['name'].strip(), hint])), skip_search=saved is not None, **fields(source)))
    return plan


def copy_location(target, source):
    target['location'] = copy.deepcopy(source['location'])
    if 'googlePlaceId' in source:
        target['googlePlaceId'] = source['googlePlaceId']
    else:
        target.pop('googlePlaceId', None)
