"""Read-only visit grouping. No coordinate lookup, storage, or route generation."""
import copy


def _access_bounds(days):
    """Trim access on first/last day; car departures retain their full itinerary."""
    def boundary(day, outbound):
        entries = day['entries']
        flights = [e for e in entries if e['transport_mode'] == 'flight']
        if flights:
            return flights[0 if outbound else -1]
        rails = [e for e in entries if e['transport_mode'] == 'shinkansen']
        if rails:
            return rails[0 if outbound else -1]
        transports = [e for e in entries if e['source_type'] == 'transport']
        edge = transports[0 if outbound else -1] if transports else None
        return edge if edge and edge['transport_mode'] == 'train' else None
    start = boundary(days[0], True) if days else None
    end = boundary(days[-1], False) if days else None
    if start is end:
        end = None
    return start, end


def build_map_stops(days, trip):
    places = {p['id']: p for p in trip['places']}
    items = {i['id']: i for day in trip['days'] for i in day['scheduleItems']}
    # Only exact names and addresses coalesce distinct Place IDs; no fuzzy matching.
    identities = {}
    canonical = {}
    for p in places.values():
        address = (p.get('address') or '').strip()
        identity = (p['name'].strip(), address) if address else p['id']
        canonical[p['id']] = identities.setdefault(identity, p['id'])
    start, end = _access_bounds(days)
    def key(entry):
        return entry['source_type'] + ':' + entry['source_item_id']
    def point(pid):
        p = places[pid]
        return dict(place_id=pid, name=p['name'], location=copy.deepcopy(p['location']),
                    comment=p['summary'], links=list(dict.fromkeys(filter(None, [p.get('officialUrl'), *p['urls']]))))
    for day in days:
        groups = {}
        def add(identity, name, ids, candidate, entry, role):
            group = groups.setdefault(identity, dict(stop_id=identity, name=name, candidate=candidate,
                                                     points=[point(pid) for pid in ids], references=[], categories=[], _visits=[], _departures=[], _orders=[]))
            ref = dict(entry_key=key(entry), role=role)
            if ref not in group['references']: group['references'].append(ref)
            if entry['category'] not in group['categories']: group['categories'].append(entry['category'])
            group['_orders'].append(entry['order'])
            if role == 'visit': group['_visits'].append(entry['order'])
            if role == 'departure': group['_departures'].append(entry['order'])
        for entry in day['entries']:
            if day is days[0] and start and entry['order'] < start['order']: continue
            if day is days[-1] and end and entry['order'] > end['order']: continue
            if entry['source_type'] == 'transport':
                for p in entry['map_points']:
                    if entry is start and p['role'] == 'departure': continue
                    if entry is end and p['role'] == 'arrival': continue
                    pid = canonical[p['place_id']]
                    add('place:'+pid, places[pid]['name'], [pid], False, entry, p['role'])
            else:
                item = items[entry['source_item_id']]
                if 'mapPlaceId' in item:
                    ids = [item['mapPlaceId']] if item['mapPlaceId'] else []
                    candidate = False
                else:
                    selection = item['placeSelection']
                    ids = selection['selection'] or selection['candidatePlaceIds']
                    candidate = not bool(selection['selection'])
                ids = list(dict.fromkeys(canonical[pid] for pid in ids))
                if candidate and ids:
                    add('candidates:'+':'.join(sorted(ids)), entry['title']+'（候補）', ids, True, entry, 'visit')
                else:
                    for pid in ids:
                        add('place:'+pid, places[pid]['name'], [pid], False, entry, 'visit')
        # A visit fixes its position. A transport-only hub is shown at final departure,
        # so station lunch stays before the station/airport used to leave the region.
        def order(g):
            return min(g['_visits']) if g['_visits'] else max(g['_departures']) if g['_departures'] else min(g['_orders'])
        result = sorted(groups.values(), key=order)
        for g in result:
            for field in ('_visits', '_departures', '_orders'): del g[field]
        day['map_stops'] = result
