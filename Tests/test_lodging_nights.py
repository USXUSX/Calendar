from copy import deepcopy
import unittest
from Sources.calendar_domain.trip_lifecycle import lodging_nights


class LodgingNightsTests(unittest.TestCase):
    def test_stays_checkout_duplicates_and_flight_nights(self):
        def item(action, category='accommodation'):
            return dict(action=action, category=category)
        trip=dict(dateRange=dict(start='2027-01-01',end='2027-01-06'), days=[
            dict(date='2027-01-01',scheduleItems=[item('機内泊')]),
            dict(date='2027-01-02',scheduleItems=[item('チェックイン'),item('ホテル宿泊')]),
            dict(date='2027-01-03',scheduleItems=[item('チェックアウト'),item('次のホテルに宿泊')]),
            dict(date='2027-01-04',scheduleItems=[item('宿泊')]),
            dict(date='2027-01-05',scheduleItems=[item('宿泊'),item('ホテルの夕食')]),
            dict(date='2027-01-06',scheduleItems=[item('チェックアウト')])])
        before=deepcopy(trip)
        self.assertEqual(lodging_nights(trip),4)
        self.assertEqual(trip,before)
        trip['days'][4]['scheduleItems']=[item('ホテルのチェックアウト'),item('機内泊')]
        self.assertEqual(lodging_nights(trip),3)
        trip['days'][3]['scheduleItems']=[item('Hotel check-out'),item('帰国便','other')]
        self.assertEqual(lodging_nights(trip),2)
        self.assertEqual(lodging_nights(dict(dateRange=dict(start='2027-01-01',end='2027-01-01'),days=[trip['days'][0]])),0)
