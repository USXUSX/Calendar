import copy
import unittest
from datetime import date
from Sources.calendar_domain.weather import JmaAdapter, build_weather_by_day, _contains

TODAY = date(2026, 10, 2)
LOCATION = {'latitude': 35.6, 'longitude': 140.1}


def series(times, code, name, **values):
    return {'timeDefines': ['2026-10-' + t + ':00+09:00' for t in times],
            'areas': [{'area': {'code': code, 'name': name}, **values}]}


def fixtures():
    return {
        'common/const/geojson/class10s.json': {'features': [
            {'properties': {'code': '120010'}, 'geometry': {'type': 'Polygon', 'coordinates': [
                [[140, 35], [141, 35], [141, 36], [140, 36], [140, 35]]]}},
            {'properties': {'code': '120030'}, 'geometry': {'type': 'MultiPolygon', 'coordinates': [[
                [[140, 34], [141, 34], [141, 35], [140, 35], [140, 34]]]]}}]},
        'common/const/area.json': {'class10s': {
            '120010': {'name': '北西部', 'parent': '120000'},
            '120030': {'name': '南部', 'parent': '120000'}}, 'offices': {'120000': {'name': '千葉県'}}},
        'forecast/const/forecast_area.json': {'120000': [
            {'class10': '120010', 'amedas': ['45212']}, {'class10': '120030', 'amedas': ['45401']}]},
        'forecast/const/week_area05.json': {'120010': ['120000'], '120030': ['120000']},
        'forecast/const/week_area.json': {'120000': [{'week': '120000', 'amedas': '45148'}]},
        'forecast/const/week_area_name.json': {'120000': {'jp': '千葉県'}},
        'forecast/data/forecast/120000.json': [
            {'reportDatetime': '2026-10-02T05:00:00+09:00', 'timeSeries': [
                series(['02T05:00', '03T00:00'], '120010', '北西部', weatherCodes=['203', '101'], weathers=['くもり　時々　雨', '晴れ　朝晩　くもり']),
                series(['02T05:00', '03T00:00'], '120030', '南部', weatherCodes=['203', '101'], weathers=['くもり　時々　雨', '晴れ　朝晩　くもり']),
                series(['02T06:00', '02T12:00', '02T18:00', '03T00:00', '03T06:00', '03T12:00', '03T18:00'],
                       '120010', '北西部', pops=['50', '', '0', '10', '0', '0', '10']),
                series(['02T09:00', '02T00:00', '03T00:00', '03T09:00'], '45212', '千葉', temps=['22', '23', '19', '24'])]},
            {'reportDatetime': '2026-10-01T17:00:00+09:00', 'timeSeries': [
                series(['04T00:00', '05T00:00'], '120000', '千葉県', weatherCodes=['201', '200'], pops=['30', '']),
                series(['04T00:00', '05T00:00'], '45148', '銚子', tempsMin=['19', ''], tempsMax=['23', ''])]}],
        'jmatile/data/wdist/VPFD/120010.json': {
            'firstAreaCode': '120010', 'reportDateTime': '2026-10-02T05:00:00+09:00',
            'areaTimeSeries': {'timeDefines': [
                {'dateTime': '2026-10-02T06:00:00+09:00', 'duration': 'PT3H'},
                {'dateTime': '2026-10-02T12:00:00+09:00', 'duration': 'PT3H'},
                {'dateTime': '2026-10-02T18:00:00+09:00', 'duration': 'PT3H'}], 'weather': ['くもり', '雨', '']},
            'pointTimeSeries': {'pointNameJP': '千葉', 'timeDefines': [
                {'dateTime': '2026-10-02T06:00:00+09:00'}, {'dateTime': '2026-10-02T12:00:00+09:00'},
                {'dateTime': '2026-10-02T18:00:00+09:00'}], 'temperature': [22, '', 20]}}}


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.data = fixtures()
        self.calls = []
        self.clock = [0]
        def transport(path):
            self.calls.append(path)
            return copy.deepcopy(self.data[path])
        self.adapter = JmaAdapter(transport=transport, today=lambda: TODAY, clock=lambda: self.clock[0])

    def forecast(self, target=TODAY):
        return self.adapter.forecast(LOCATION, target)

    def test_short_pop_intervals_missing_zero_and_today_maximum(self):
        result = self.forecast()
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['area_name'], '千葉県 北西部')
        self.assertEqual(result['weather_label'], 'くもり 時々 雨')
        self.assertEqual(result['temperature_location'], '千葉')
        self.assertEqual(result['temperature_max'], 22)
        self.assertIsNone(result['temperature_min'])  # 23 in 00:00 is not a minimum
        self.assertEqual(result['precipitation_periods'], [
            {'start_hour': 6, 'end_hour': 12, 'probability': 50},
            {'start_hour': 12, 'end_hour': 18, 'probability': None},
            {'start_hour': 18, 'end_hour': 24, 'probability': 0}])
        self.assertNotIn('precipitation_probability_max', result)
        self.assertNotIn('precipitation_sum', result)
        self.assertEqual(result['issued_at'], '2026-10-02T05:00:00+09:00')

    def test_three_hour_details_no_interpolation_or_probability(self):
        result = self.forecast()
        self.assertEqual([p['time'] for p in result['periods']], ['06:00', '12:00', '18:00'])
        self.assertIsNone(result['periods'][1]['temperature'])
        self.assertEqual(result['periods'][2]['weather_label'], '天気欠測')
        self.assertTrue(all('precipitation_probability' not in p for p in result['periods']))
        self.assertEqual(result['details_temperature_location'], '千葉')

    def test_tomorrow_and_17_hour_temperature_slots(self):
        tomorrow = date(2026, 10, 3)
        result = self.forecast(tomorrow)
        self.assertEqual((result['temperature_min'], result['temperature_max']), (19, 24))
        product = self.data['forecast/data/forecast/120000.json'][0]
        product['reportDatetime'] = '2026-10-02T17:00:00+09:00'
        product['timeSeries'][-1] = series(['03T00:00', '03T09:00'], '45212', '千葉', temps=['19', '24'])
        self.clock[0] = 901
        self.assertIsNone(self.forecast()['temperature_max'])
        result = self.forecast(tomorrow)
        self.assertEqual((result['temperature_min'], result['temperature_max']), (19, 24))

    def test_weekly_region_station_pop_and_no_detail_fetch(self):
        result = self.forecast(date(2026, 10, 4))
        self.assertEqual((result['area_code'], result['area_name']), ('120000', '千葉県'))
        self.assertEqual(result['temperature_location'], '銚子')
        self.assertEqual((result['temperature_min'], result['temperature_max']), (19, 23))
        self.assertEqual(result['precipitation_probability'], 30)
        self.assertEqual(result['weather_label'], '曇時々晴')
        self.assertEqual(result['periods'], [])
        self.assertFalse(any('VPFD' in p for p in self.calls))
        result = self.forecast(date(2026, 10, 5))
        self.assertIsNone(result['precipitation_probability'])
        self.assertIsNone(result['temperature_max'])

    def test_weekly_uses_available_regional_split_and_its_station(self):
        self.data['forecast/const/week_area05.json']['120010'] = ['120000', '120100']
        self.data['forecast/const/week_area_name.json']['120100'] = {'jp': '合成県北部'}
        self.data['forecast/const/week_area.json']['120000'].append({'week': '120100', 'amedas': '99999'})
        self.data['forecast/data/forecast/120000.json'][1]['timeSeries'] = [
            series(['04T00:00'], '120100', '合成県北部', weatherCodes=['203'], pops=['70']),
            series(['04T00:00'], '99999', '合成代表地点', tempsMin=['10'], tempsMax=['20'])]
        result = self.forecast(date(2026, 10, 4))
        self.assertEqual((result['area_code'], result['area_name']), ('120100', '合成県北部'))
        self.assertEqual(result['temperature_location'], '合成代表地点')
        self.assertEqual(result['precipitation_probability'], 70)

    def test_forecast_horizon_unpublished_and_failure_distinct(self):
        self.assertEqual(self.forecast(date(2026, 10, 10))['status'], 'outside_forecast')
        self.assertEqual(self.calls, [])
        self.assertEqual(self.forecast(date(2026, 10, 9))['status'], 'outside_forecast')
        self.assertEqual(self.adapter.forecast({'latitude': 48, 'longitude': 2}, TODAY)['status'], 'location_unknown')
        del self.data['forecast/data/forecast/120000.json']
        self.clock[0] = 901
        self.assertEqual(self.forecast()['status'], 'unavailable')

    def test_detail_failure_keeps_daily_but_reports_failure(self):
        del self.data['jmatile/data/wdist/VPFD/120010.json']
        result = self.forecast()
        self.assertEqual(result['status'], 'available')
        self.assertEqual(result['details_status'], 'unavailable')

    def test_expired_cache_does_not_serve_stale_forecasts(self):
        self.forecast()
        self.forecast()
        self.assertEqual(self.calls.count('forecast/data/forecast/120000.json'), 1)
        self.clock[0] = 901
        del self.data['forecast/data/forecast/120000.json']
        self.assertEqual(self.forecast()['status'], 'unavailable')
        self.assertEqual(self.calls.count('forecast/data/forecast/120000.json'), 2)

    def test_only_day_areas_deduplicated_in_order_and_no_mutation(self):
        areas = [{'name': '施設A', 'location': LOCATION}, {'name': '施設B', 'location': LOCATION},
                 {'name': '南の地点', 'location': {'latitude': 34.5, 'longitude': 140.1}},
                 {'name': '位置なし', 'location': None}]
        trip = {'days': [{'id': 'day-1', 'date': TODAY.isoformat(), 'areas': areas}],
                'places': [{'name': 'not used', 'location': {'latitude': 30, 'longitude': 130}}]}
        original = copy.deepcopy(trip)
        result = build_weather_by_day(trip, self.adapter, today=TODAY)['day-1']
        self.assertEqual([r.get('area_code') for r in result['locations']], ['120010', '120030', None])
        self.assertEqual(result['locations'][-1]['status'], 'location_unknown')
        trip['days'][0]['date'] = '2026-10-04'
        result = build_weather_by_day(trip, self.adapter, today=TODAY)['day-1']
        self.assertEqual([r.get('area_code') for r in result['locations']], ['120000', None])
        trip['days'][0]['date'] = TODAY.isoformat()
        self.assertEqual(trip, original)
        trip['days'][0]['areas'] = []
        before = len(self.calls)
        self.assertEqual(build_weather_by_day(trip, self.adapter, today=TODAY)['day-1']['status'], 'location_unknown')
        self.assertEqual(len(self.calls), before)

    def test_polygon_holes_and_border(self):
        geometry = {'type': 'Polygon', 'coordinates': [
            [[0,0],[4,0],[4,4],[0,4],[0,0]], [[1,1],[2,1],[2,2],[1,2],[1,1]]]}
        self.assertTrue(_contains(geometry, {'latitude': 3, 'longitude': 3}))
        self.assertFalse(_contains(geometry, {'latitude': 1.5, 'longitude': 1.5}))
        self.assertTrue(_contains(geometry, {'latitude': 0, 'longitude': 2}))


if __name__ == '__main__':
    unittest.main()
