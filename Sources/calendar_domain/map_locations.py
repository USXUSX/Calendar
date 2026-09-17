"""Coordinate-only import and edit rules. Search runs in the Maps browser client."""
import copy
from .errors import ConflictError, NotFoundError, ValidationError
from .trip_detail import build_trip_detail_view
from Sources.place_acquisition import valid_field


def identity(place):
    address = (place.get('address') or '').strip()
    return (place['name'].strip(), address) if address else place['id']


def prepare(trip, existing=None):
    candidate = copy.deepcopy(trip)
    saved = {p['id']: p['location'] for p in (existing or {}).get('places', []) if p['location'] is not None}
    for p in candidate['places']:
        if p['id'] in saved:
            p['location'] = copy.deepcopy(saved[p['id']])
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
        location = next((x['location'] for x in places if x['location'] is not None), None)
        if location is not None:
            for x in places:
                if x['location'] is None:
                    x['location'] = copy.deepcopy(location)
        hint = (p.get('address') or '').strip() or targets[p['id']]
        plan.append(dict(place_id=p['id'], name=p['name'], query=' '.join(filter(None, [p['name'].strip(), hint])),
                         location=copy.deepcopy(location), place_ids=[x['id'] for x in places]))
    return candidate, plan


def complete(trip, results=None, existing=None):
    candidate, plan = prepare(trip, existing)
    if results is not None and not isinstance(results, dict):
        raise ValidationError('座標検索結果は地点IDごとに指定してください。')
    results = results or {}
    places = {p['id']: p for p in candidate['places']}
    counts = dict(filled=0, missing=0, existing=0)
    for point in plan:
        if point['location'] is not None:
            counts['existing'] += 1
            continue
        location = results.get(point['place_id'])
        if location is not None and valid_field('location', location):
            for pid in point['place_ids']:
                if places[pid]['location'] is None:
                    places[pid]['location'] = copy.deepcopy(location)
            counts['filled'] += 1
        else:
            counts['missing'] += 1
    return candidate, counts


def target(domain, trip_id, place_id):
    trip = domain.get_effective_trip(trip_id)
    _, plan = prepare(trip)
    point = next((p for p in plan if place_id in p['place_ids']), None)
    if point is None:
        raise NotFoundError('地図表示対象の地点を確認してください。')
    return point


def save(domain, command_id, trip_id, place_id, location, expected_location):
    domain._require_text(command_id, 'command_id')
    if location is None or not valid_field('location', location):
        raise ValidationError('緯度・経度の値を確認してください。')
    with domain._command() as connection:
        connection.execute('BEGIN IMMEDIATE')
        if domain._journal_path(trip_id).exists():
            raise ConflictError('pending Trip adoption')
        point = target(domain, trip_id, place_id)
        if point['location'] != expected_location:
            raise ConflictError('位置が変更されています。再読み込みしてください。')
        for pid in point['place_ids']:
            domain._store_trip_fields(connection, command_id, trip_id, pid, {'location': location}, {'location': '/location'})
    return dict(status='saved', view=domain.get_trip_detail_view(trip_id))
