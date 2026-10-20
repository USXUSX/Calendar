import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from Sources.calendar_domain.rail_routes import extract, route_geometry, Unavailable


def feature(points, station=None, code=None, line='本線', operator='試験鉄道', kind='2'):
    properties = dict(N02_001='11', N02_002=kind, N02_003=line, N02_004=operator)
    if station:
        properties.update(N02_005=station, N02_005c=code or station)
    return dict(properties=properties, geometry=dict(type='LineString', coordinates=points))


def leg(a='甲', b='乙', **extra):
    return dict(operator='試験鉄道', line='本線', **{'from':a, 'to':b}, **extra)


class RailRoutesTest(unittest.TestCase):
    def setUp(self):
        self.sections = [feature([[0,0],[1,1],[2,0],[3,1],[4,0]])]
        self.stations = [feature([[0,0]],'甲'),feature([[4,0]],'乙'),feature([[2,0]],'中')]
        self.spec = dict(legs=[leg()])

    def extract(self, spec=None):
        return extract(self.sections, self.stations, spec or self.spec, 'train')

    def test_direction_explicit_line_and_station_identity(self):
        self.assertEqual(self.extract()[0], [[0,0],[1,1],[2,0],[3,1],[4,0]])
        self.assertEqual(self.extract(dict(legs=[leg('乙','甲')]))[0], self.extract()[0][::-1])
        self.stations.append(feature([[10,0]],'甲',code='another'))
        with self.assertRaisesRegex(Unavailable,'ambiguous_station'):self.extract()
        with self.assertRaisesRegex(Unavailable,'line_not_found'):
            self.extract(dict(legs=[dict(leg(),line='別線')]))
        with self.assertRaisesRegex(Unavailable,'mode_mismatch'):
            extract(self.sections,self.stations,self.spec,'shinkansen')

    def test_branch_disconnection_ring_and_explicit_via(self):
        self.sections.append(feature([[2,0],[2,2]]))
        self.assertEqual(len(self.extract()[0]),5)  # dead-end branch is not an alternative
        self.sections.append(feature([[0,0],[2,-1],[4,0]]))
        with self.assertRaisesRegex(Unavailable,'ambiguous_path'):self.extract()
        self.assertEqual(self.extract(dict(legs=[leg(via=['中'])]))[0], self.sections[0]['geometry']['coordinates'])
        self.sections = [feature([[0,0],[1,1]]),feature([[3,1],[4,0]])]
        with self.assertRaisesRegex(Unavailable,'disconnected'):self.extract()

    def test_multiple_lines_and_platforms(self):
        self.stations.append(feature([[0,0]],'甲'))  # same station code, platform duplicate
        self.assertEqual(len(self.extract()[0]),5)
        self.sections.append(feature([[4,0],[5,1],[6,0]],line='支線'))
        self.stations.extend([feature([[4,0]],'乙',line='支線'),feature([[6,0]],'丙',line='支線')])
        parts=self.extract(dict(legs=[leg(),dict(leg('乙','丙'),line='支線')]))
        self.assertEqual(len(parts),2)
        with self.assertRaisesRegex(Unavailable,'leg_connection_mismatch'):
            self.extract(dict(legs=[leg(),dict(leg('甲','丙'),line='支線')]))

    def test_cache_tracks_endpoints_specification_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'rail/N02-25/N02-25_GML.zip';source.parent.mkdir(parents=True)
            def write():
                with zipfile.ZipFile(source,'w') as z:
                    for kind,values in [('RailroadSection',self.sections),('Station',self.stations)]:
                        z.writestr('N02-25_GML/UTF-8/N02-25_'+kind+'.geojson',json.dumps({'features':values}))
            write()
            transport=dict(mode='train',railRoute=self.spec)
            a={'name':'甲駅','location':None};b={'name':'乙駅','location':None}
            original=copy.deepcopy(transport)
            first=route_geometry(root,transport,a,b)
            self.assertEqual(first['status'],'ready')
            self.assertEqual(route_geometry(root,transport,a,b),first)
            transport['railRoute']={'legs':[leg('甲','中')]}
            self.assertEqual(route_geometry(root,transport,a,b)['reason'],'endpoint_mismatch')
            changed=route_geometry(root,transport,a,{'name':'中'})
            self.assertNotEqual(first['cache_key'],changed['cache_key'])
            self.assertEqual(changed['geometry']['coordinates'][0][-1],[2,0])
            self.sections[0]['geometry']['coordinates'][1]=[1,1.5];write()
            fresh=route_geometry(root,original,a,b)
            self.assertNotEqual(first['source_sha256'],fresh['source_sha256'])
            self.assertEqual(fresh['geometry']['coordinates'][0][1],[1,1.5])
            self.assertEqual(route_geometry(root,{'mode':'train'},a,b)['reason'],'route_unspecified')
            source.unlink()
            self.assertEqual(route_geometry(root,original,a,b)['reason'],'data_unavailable')

if __name__ == '__main__':unittest.main()
