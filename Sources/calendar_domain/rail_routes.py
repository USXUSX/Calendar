"""N02 railway shapes: explicit line/station paths, local derived cache only."""
from collections import defaultdict
import heapq
import math
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import zipfile

VERSION = 'N02-25'
ALGORITHM_VERSION = 2
SOURCE = 'https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-2025.html'
ATTRIBUTION = '国土交通省「国土数値情報（鉄道データ）2025年度版」を加工（CC BY 4.0）'


class Unavailable(Exception):
    pass


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


@lru_cache(maxsize=2)
def _dataset(path, modified, size):
    payload = Path(path).read_bytes()
    import io
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        values = [json.loads(archive.read(f'N02-25_GML/UTF-8/N02-25_{kind}.geojson'))['features']
                  for kind in ('RailroadSection', 'Station')]
    return hashlib.sha256(payload).hexdigest(), values


def _name(value):
    value = value.strip()
    return value[:-1] if value.endswith('駅') else value


def _distance(a, b):
    """Great-circle metres between adjacent N02 vertices, not station chords."""
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1, h)))


def _has_alternative(graph, path, blocked):
    positions = {node: i for i, node in enumerate(path)}
    on_path = set(path)
    visited = set(blocked)
    # An off-path component joining two path nodes gives an alternative.
    for node in path:
        for other in graph[node]:
            if other in on_path:
                if abs(positions[node] - positions[other]) != 1:
                    return True
                continue
            if other in visited:
                continue
            attached = {node}
            pending = [other]
            visited.add(other)
            while pending:
                current = pending.pop()
                for adjacent in graph[current]:
                    if adjacent in on_path:
                        attached.add(adjacent)
                    elif adjacent not in visited:
                        visited.add(adjacent)
                        pending.append(adjacent)
            if len(attached) > 1:
                return True
    return False


def _path(graph, start, end, blocked):
    """Shortest rail distance; stable coordinate order breaks exact ties."""
    parents = {start: None}
    distances = {start: 0.0}
    queue = [(0.0, start)]
    while queue:
        distance, node = heapq.heappop(queue)
        if distance != distances[node]:
            continue
        if node == end:
            break
        for other in sorted(graph[node]):
            if other in blocked:
                continue
            candidate = distance + _distance(node, other)
            # Equal distances keep the first predecessor. Heap and neighbours
            # both use (longitude, latitude) order, independent of source order.
            if candidate < distances.get(other, math.inf):
                distances[other] = candidate
                parents[other] = node
                heapq.heappush(queue, (candidate, other))
    if end not in parents:
        raise Unavailable('disconnected')
    path = []
    node = end
    while node is not None:
        path.append(node)
        node = parents[node]
    path.reverse()
    return [list(p) for p in path], _has_alternative(graph, path, blocked)


def extract(sections, stations, specification, mode):
    lines = []
    reference_route = False
    prior = None
    legs = specification['legs']
    for leg in legs:
        if prior is not None and prior != leg['from']:
            raise Unavailable('leg_connection_mismatch')
        selected = lambda f: f['properties']['N02_003'] == leg['line'] and f['properties']['N02_004'] == leg['operator']
        matching_stations = [s for s in stations if selected(s)]
        if not matching_stations:
            raise Unavailable('line_not_found')
        # Shinkansen versus conventional rail must match the explicit transport.
        kinds = {s['properties']['N02_002'] for s in matching_stations}
        if (mode == 'shinkansen' and kinds != {'1'}) or (mode == 'train' and '1' in kinds):
            raise Unavailable('mode_mismatch')
        graph = defaultdict(set)
        for feature in [s for s in sections if selected(s)] + matching_stations:
            pts = [tuple(p) for p in feature['geometry']['coordinates']]
            for a, b in zip(pts, pts[1:]):
                if a != b:
                    graph[a].add(b)
                    graph[b].add(a)
        names = [leg['from'], *leg.get('via', []), leg['to']]
        if len(names) != len(set(names)):
            raise Unavailable('repeated_station')
        anchors = []
        for name in names:
            matches = [s for s in matching_stations if s['properties']['N02_005'] == name]
            if not matches or len({s['properties']['N02_005c'] for s in matches}) != 1:
                raise Unavailable('ambiguous_station' if matches else 'station_not_found')
            # N02 may have multiple platform geometries with the same station code.
            pts = matches[0]['geometry']['coordinates']
            anchors.append(tuple(pts[len(pts)//2]))
        line = []
        for i, (a, b) in enumerate(zip(anchors, anchors[1:])):
            blocked = set(anchors) - {a, b}
            segment, selected = _path(graph, a, b, blocked)
            reference_route = reference_route or selected
            line.extend(segment if not line else segment[1:])
        lines.append(line)
        prior = leg['to']
    return lines, reference_route


def route_geometry(root, transport, origin, destination):
    """No network, no formal writes. A cache is selected by all relevant inputs."""
    if transport['mode'] not in ('train', 'shinkansen'):
        return None
    result = dict(status='unavailable', source_url=SOURCE, source_version=VERSION,
                  attribution=ATTRIBUTION, license_url='https://creativecommons.org/licenses/by/4.0/')
    spec = transport.get('railRoute')
    if not spec:
        return dict(result, reason='route_unspecified')
    legs = spec['legs']
    if _name(origin['name']) != legs[0]['from'] or _name(destination['name']) != legs[-1]['to']:
        return dict(result, reason='endpoint_mismatch')
    source = Path(root)/'rail'/VERSION/f'{VERSION}_GML.zip'
    try:
        stat = source.stat()
        digest, (sections, stations) = _dataset(str(source), stat.st_mtime_ns, stat.st_size)
        key = fingerprint(dict(algorithm=ALGORITHM_VERSION, source=digest, mode=transport['mode'], specification=spec,
                               origin=origin, destination=destination))
        cache = Path(root)/'rail'/'derived'/f'{key}.json'
        if cache.is_file():
            return json.loads(cache.read_text())
        lines, reference_route = extract(sections, stations, spec, transport['mode'])
        result = dict(result, status='ready', source_sha256=digest, cache_key=key, reference_route=reference_route,
                      geometry=dict(type='MultiLineString', coordinates=lines))
        cache.parent.mkdir(parents=True, exist_ok=True)
        # Atomic replace also allows concurrent reads of the same derived result.
        import os, tempfile
        with tempfile.NamedTemporaryFile(mode='w', dir=cache.parent, delete=False) as handle:
            json.dump(result, handle, ensure_ascii=False)
            temporary = handle.name
        os.replace(temporary, cache)
        return result
    except Unavailable as error:
        return dict(result, reason=str(error))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return dict(result, reason='data_unavailable')


def add_rail_routes(view, trip, root):
    transports = {t['id']: t for t in trip['transports']}
    for day in view['days']:
        for route in day['map_routes']:
            rail = route_geometry(root, transports[route['route_id']], route['origin'], route['destination'])
            if rail is not None:
                route['rail'] = rail
