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
        return dict(place_id=pid, name=p['name'], mapDisplayName=p.get('mapDisplayName'), location=copy.deepcopy(p['location']), googlePlaceId=p.get('googlePlaceId'),
                    category=p['category'], official_url=p.get('officialUrl'), comment=p['summary'], links=list(dict.fromkeys(filter(None, [p.get('officialUrl'), *p['urls']]))))
    for day in days:
        groups = {}
        def add(identity, name, ids, candidate, entry, role, display_points=None):
            group = groups.setdefault(identity, dict(stop_id=identity, name=name, candidate=candidate,
                                                     points=[point(pid) for pid in ids], references=[], categories=[], _visits=[], _arrivals=[], _departures=[], _orders=[]))
            if display_points is not None:
                group.update(points=display_points, candidate=candidate)
            ref = dict(entry_key=key(entry), role=role)
            if ref not in group['references']: group['references'].append(ref)
            if entry['category'] not in group['categories']: group['categories'].append(entry['category'])
            group['_orders'].append(entry['order'])
            if role == 'visit': group['_visits'].append(entry['order'])
            if role == 'arrival': group['_arrivals'].append(entry['order'])
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
                selection = item['placeSelection']
                ids = selection['selection'] or selection['candidatePlaceIds']
                candidate = not bool(selection['selection'])
                if 'mapPlaceId' in item:
                    if item['mapPlaceId'] is None:
                        continue
                    target = canonical[item['mapPlaceId']]
                    # The display target groups the visit; it must not erase candidates.
                    # Use the explicit area's position only when a candidate lacks its own.
                    display_points = [point(pid) for pid in dict.fromkeys(ids or [target])]
                    for p in display_points:
                        if p['location'] is None:
                            p['location'] = copy.deepcopy(places[target]['location'])
                            p['location_place_id'] = target
                    add('place:'+target, places[target]['name'], [target], candidate and bool(ids),
                        entry, 'visit', display_points)
                    continue
                ids = list(dict.fromkeys(canonical[pid] for pid in ids))
                if candidate and ids:
                    add('candidates:'+':'.join(sorted(ids)), entry['title']+'（候補）', ids, True, entry, 'visit')
                else:
                    for pid in ids:
                        add('place:'+pid, places[pid]['name'], [pid], False, entry, 'visit')
        # Visits fix their position. Before the final day, a hub with a later
        # departure belongs at first arrival; final-day hubs retain exit order.
        def order(g):
            if g['_visits']:
                return min(g['_visits'])
            if day is not days[-1] and g['_arrivals'] and g['_departures']:
                arrival = min(g['_arrivals'])
                if arrival < max(g['_departures']):
                    return arrival
            return max(g['_departures']) if g['_departures'] else min(g['_orders'])
        result = sorted(groups.values(), key=order)
        for g in result:
            for field in ('_visits', '_arrivals', '_departures', '_orders'): del g[field]
        day['map_stops'] = result
        day['map_routes'] = [dict(route_id=t['id'], mode=t['mode'],
                                  origin=point(t['fromPlaceId']), destination=point(t['toPlaceId']))
                             for t in sorted(trip['transports'], key=lambda t: t['order'])
                             if t['dayId'] == day['day_id'] and t.get('showOnMap', False)]
