"""JMA forecast context. Only in-memory caching; never writes Trip or SQLite."""
from __future__ import annotations

import gzip
import json
import math
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

_SOURCE = 'https://www.jma.go.jp/bosai/forecast/'
_BASE = 'https://www.jma.go.jp/bosai/'
_JST = timezone(timedelta(hours=9))
_CODES = json.loads(Path(__file__).with_name('jma_weather_codes.json').read_text())
_DAYPARTS = (('morning', '朝', 6), ('noon', '昼', 12), ('evening', '夕', 18), ('night', '夜', 21))


def _local_today():
    return datetime.now(_JST).date()


def _valid_location(location):
    return (isinstance(location, dict) and set(location) == {'latitude', 'longitude'}
            and all(type(location.get(key)) in (int, float) and math.isfinite(location[key])
                    and abs(location[key]) <= bound
                    for key, bound in (('latitude', 90), ('longitude', 180))))


def _in_ring(x, y, ring):
    inside = False
    for a, b in zip(ring, ring[1:] + ring[:1]):
        if min(a[0], b[0]) <= x <= max(a[0], b[0]) and min(a[1], b[1]) <= y <= max(a[1], b[1]):
            if abs((x-a[0])*(b[1]-a[1]) - (y-a[1])*(b[0]-a[0])) < 1e-12:
                return True
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def _contains(geometry, location):
    polygons = geometry['coordinates']
    if geometry['type'] == 'Polygon':
        polygons = [polygons]
    elif geometry['type'] != 'MultiPolygon':
        raise ValueError('unsupported area geometry')
    x, y = location['longitude'], location['latitude']
    return any(_in_ring(x, y, rings[0]) and not any(_in_ring(x, y, hole) for hole in rings[1:])
               for rings in polygons)


def _number(value):
    if value is None or value == '':
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('invalid forecast value')
    return int(number) if number.is_integer() else number


def _stamp(value):
    return datetime.fromisoformat(value).astimezone(_JST)


def _series(product, field, code):
    for series in product['timeSeries']:
        for area in series['areas']:
            if area['area']['code'] == code and field in area:
                return series['timeDefines'], area
    return [], {}


def _values(times, area, field, target):
    return [(stamp, area[field][i]) for i, value in enumerate(times)
            for stamp in [_stamp(value)] if stamp.date() == target]


def _condition(code, label=None):
    item = _CODES.get(str(code), {})
    return {'weather_code': code, 'weather_kind': item.get('kind', 'unknown'),
            'weather_label': ' '.join((label or item.get('label', '天気欠測')).split())}


class JmaAdapter:
    """Official website JSON, with no other provider, retry, or disk cache."""

    def __init__(self, *, transport=None, timeout=10, cache_seconds=900, clock=None, today=None):
        if not 0 < timeout <= 30 or not 0 <= cache_seconds <= 3600:
            raise ValueError('invalid weather timeout/cache')
        self.transport = transport or self._http
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self.clock = clock or time.monotonic
        self.today = today or _local_today
        self._cache = {}

    def _http(self, path):
        request = Request(_BASE + path, headers={'Accept': 'application/json', 'User-Agent': 'Calendar/0.1'})
        with urlopen(request, timeout=self.timeout) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError('weather response too large')
        if payload[:2] == b'\x1f\x8b':
            payload = gzip.decompress(payload)
        if len(payload) > 2_000_000:
            raise ValueError('weather response too large')
        return json.loads(payload)

    def _get(self, path, *, metadata=False):
        now = self.clock()
        held = self._cache.get(path)
        if held and held[0] > now:
            return held[1]
        self._cache.pop(path, None)
        value = self.transport(path)
        ttl = 86400 if metadata else self.cache_seconds
        if ttl:
            self._cache[path] = (now + ttl, value)
        return value

    def _region(self, location):
        polygons = self._get('common/const/geojson/class10s.json', metadata=True)
        code = next((f['properties']['code'] for f in polygons['features']
                     if _contains(f['geometry'], location)), None)
        if code is None:
            return None
        areas = self._get('common/const/area.json', metadata=True)
        area = areas['class10s'][code]
        office = area['parent']
        office_name = areas['offices'][office]['name']
        name = area['name'] if area['name'].startswith(office_name) else office_name + ' ' + area['name']
        return {'area_code': code, 'area_name': name, 'office': office}

    def forecast(self, location, target_date):
        if not _valid_location(location) or not isinstance(target_date, date):
            raise ValueError('invalid weather request')
        current = self.today()
        if not current <= target_date <= current + timedelta(days=7):
            return {'status': 'outside_forecast'}
        region = {}
        try:
            region = self._region(location)
            if region is None:
                return {'status': 'location_unknown'}
            # The JMA site serves these two offices in the same prefectural files.
            path_code = {'014030': '014100', '460040': '460100'}.get(region['office'], region['office'])
            products = self._get(f'forecast/data/forecast/{path_code}.json')
            if target_date <= current + timedelta(days=1):
                result = self._short(products[0], region, target_date)
            else:
                result = self._weekly(products[1], region, target_date)
            return {**region, **result}
        except (OSError, ValueError, KeyError, IndexError, TypeError, StopIteration):
            return {**(region or {}), 'status': 'unavailable'}

    def _short(self, product, region, target):
        code, office = region['area_code'], region['office']
        times, weather = _series(product, 'weatherCodes', code)
        days = _values(times, weather, 'weatherCodes', target)
        if not days:
            return {'status': 'outside_forecast'}
        index = next(i for i, value in enumerate(times) if _stamp(value).date() == target)
        result = {'status': 'available', 'forecast_type': 'short',
                  'issued_at': product['reportDatetime'], **_condition(days[0][1], weather['weathers'][index]),
                  'temperature_max': None, 'temperature_min': None, 'temperature_location': None,
                  'precipitation_periods': [], 'periods': []}
        times, pops = _series(product, 'pops', code)
        for stamp, value in _values(times, pops, 'pops', target):
            result['precipitation_periods'].append({'start_hour': stamp.hour, 'end_hour': stamp.hour + 6,
                                                    'probability': _number(value)})
        mapping = self._get('forecast/const/forecast_area.json', metadata=True)
        stations = next(row['amedas'] for row in mapping[office] if row['class10'] == code)
        times, temps = _series(product, 'temps', stations[0])
        if temps:
            result['temperature_location'] = temps['area']['name']
            values = _values(times, temps, 'temps', target)
            issued = _stamp(product['reportDatetime'])
            # JMA duplicates today's daytime maximum in the 00:00 slot; it is NOT a minimum.
            if target == issued.date():
                if issued.hour < 17 and values:
                    result['temperature_max'] = _number(values[0][1])
            else:
                for stamp, value in values:
                    if stamp.hour == 0:
                        result['temperature_min'] = _number(value)
                    elif stamp.hour == 9:
                        result['temperature_max'] = _number(value)
        try:
            detail = self._get(f'jmatile/data/wdist/VPFD/{code}.json')
            if detail['firstAreaCode'] != code:
                raise ValueError('wrong time series area')
            result.update(self._periods(detail, target))
        except (OSError, ValueError, KeyError, IndexError, TypeError):
            result['details_status'] = 'unavailable'
        return result

    def _weekly(self, product, region, target):
        candidates = self._get('forecast/const/week_area05.json', metadata=True)[region['area_code']]
        chosen = next((code for code in candidates if _series(product, 'weatherCodes', code)[1]), None)
        if chosen is None:
            return {'status': 'location_unknown'}
        times, weather = _series(product, 'weatherCodes', chosen)
        days = _values(times, weather, 'weatherCodes', target)
        names = self._get('forecast/const/week_area_name.json', metadata=True)
        context = {'area_code': chosen, 'area_name': names[chosen]['jp']}
        if not days:
            return {**context, 'status': 'outside_forecast'}
        index = next(i for i, value in enumerate(times) if _stamp(value).date() == target)
        mapping = self._get('forecast/const/week_area.json', metadata=True)[region['office']]
        station = next(row['amedas'] for row in mapping if row['week'] == chosen)
        times, temps = _series(product, 'tempsMin', station)
        result = {**context, 'status': 'available', 'forecast_type': 'weekly',
                  'issued_at': product['reportDatetime'], **_condition(days[0][1]),
                  'precipitation_probability': _number(weather['pops'][index]),
                  'temperature_max': None, 'temperature_min': None,
                  'temperature_location': temps.get('area', {}).get('name'),
                  'periods': [], 'precipitation_periods': []}
        for field, output in (('tempsMin', 'temperature_min'), ('tempsMax', 'temperature_max')):
            values = _values(times, temps, field, target)
            if values:
                result[output] = _number(values[0][1])
        return result

    def _periods(self, detail, target):
        area, point = detail['areaTimeSeries'], detail['pointTimeSeries']
        weather = {_stamp(t['dateTime']): (area['weather'][i], t['duration'])
                   for i, t in enumerate(area['timeDefines'])}
        temps = {_stamp(t['dateTime']): _number(point['temperature'][i])
                 for i, t in enumerate(point['timeDefines'])}
        periods = []
        for key, label, hour in _DAYPARTS:
            stamp = datetime(target.year, target.month, target.day, hour, tzinfo=_JST)
            condition, duration = weather.get(stamp, (None, None))
            temperature = temps.get(stamp)
            if condition in (None, '') and temperature is None:
                continue
            if condition and duration != 'PT3H':
                raise ValueError('unexpected weather duration')
            periods.append({'key': key, 'label': label, 'time': f'{hour:02}:00',
                            'weather_label': condition or '天気欠測',
                            'weather_kind': ('snow' if condition and '雪' in condition else
                                             'rain' if condition and '雨' in condition else
                                             'clear' if condition == '晴れ' else
                                             'cloudy' if condition == 'くもり' else 'unknown'),
                            'temperature': temperature})
        return {'periods': periods, 'details_status': 'available' if periods else 'outside_forecast',
                'details_issued_at': detail['reportDateTime'],
                'details_temperature_location': point['pointNameJP']}


def build_weather_by_day(trip, adapter, *, today=None):
    """Use only Day.areas and collapse identical forecast regions in itinerary order."""
    if not isinstance(trip, dict) or adapter is None:
        raise ValueError('trip and weather adapter are required')
    current = today or _local_today()
    if not isinstance(current, date):
        raise ValueError('today must be a date')
    result = {}
    for day in trip['days']:
        target = date.fromisoformat(day['date'])
        common = {'forecast_date': day['date'], 'source': _SOURCE, 'attribution': '気象庁'}
        if not current <= target <= current + timedelta(days=7):
            result[day['id']] = {**common, 'status': 'outside_forecast'}
            continue
        forecasts, seen = [], set()
        for index, area in enumerate(day.get('areas', [])):
            value = (adapter.forecast(area['location'], target) if _valid_location(area.get('location'))
                     else {'status': 'location_unknown'})
            code = value.get('area_code')
            if code and code in seen:
                continue
            if code:
                seen.add(code)
            forecasts.append({**common, 'place_id': f"{day['id']}-area-{index}",
                              'place_name': area['name'], **value})
        result[day['id']] = ({**forecasts[0], 'locations': forecasts} if forecasts
                             else {**common, 'status': 'location_unknown'})
    return result
