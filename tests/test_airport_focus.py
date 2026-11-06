import copy
import unittest
from unittest.mock import Mock, patch

from airport_focus import load_focus, focus_municipal, distance_km
from notification_state import NotificationState
from official_data import parse_poa_stations, parse_poa_alerts, compare_sources
from operational_notices import civil_defense_notice
from test_rain_alert import NOW
from test_operational_notices import alert


def product(order=1, text='Chuva intensa prevista'):
    config = load_focus()
    name = next(r['name'] for r in config['regions'] if r['order'] == order)
    rows = [dict(order=r['order'], name=r['name'], alert=alert(alert_description=text) if r['order'] == order else None)
            for r in config['regions']]
    return dict(status='ok', **parse_poa_alerts(rows, NOW))


class AirportFocusTests(unittest.TestCase):
    def test_official_regions_overlap_and_border(self):
        c = load_focus()
        selected = {r['order'] for r in c['regions'] if r['distance_km'] <= 4.1}
        self.assertEqual(selected, {1, 2, 3, 5, 14, 16, 17})
        self.assertEqual(next(r['distance_km'] for r in c['regions'] if r['order'] == 1), 0)
        self.assertGreater(next(r['distance_km'] for r in c['regions'] if r['order'] == 13), 18)

    def test_extremo_sul_never_notifies_local_channel(self):
        raw = product(13)
        local = focus_municipal(raw)
        notify = Mock(return_value=True)
        self.assertEqual(NotificationState().municipal(local, NOW, notify), [])
        notify.assert_not_called()
        self.assertEqual(len(local['regional_alerts']), 1)
        self.assertEqual(local['excluded_alerts'][0]['reason'], 'outside_airport_focus')
        self.assertEqual(len(raw['alerts']), 1)

    def test_source_test_inside_airport_is_not_real_alert(self):
        for text in ['TESTE DE AVISO PARA POACLIMA Siga as orientações', 'Simulado de aviso', 'TESTE — DADOS SIMULADOS']:
            local = focus_municipal(product(1, text))
            self.assertEqual(local['alerts'], [])
            self.assertEqual(local['excluded_alerts'][0]['reason'], 'source_test')

    def test_actual_hazard_mentioning_tests_is_not_suppressed(self):
        local = focus_municipal(product(1, 'Chuva forte: testes de drenagem em andamento.'))
        self.assertEqual(len(local['alerts']), 1)

    def test_group_only_keeps_local_regions_and_accepts_only_those(self):
        p = product(1)
        p['alerts'][0]['regions'].append(dict(order=13, name='EXTREMO SUL'))
        local = focus_municipal(p)
        self.assertEqual([r['order'] for r in local['alerts'][0]['regions']], [1])
        state = NotificationState()
        state.municipal(local, NOW, Mock(return_value=True))
        self.assertEqual(set(state.data['events']), {'municipal:1'})

    def test_unknown_mapping_is_conservative_and_partial(self):
        p = product(13)
        p['alerts'][0]['regions'][0]['name'] = 'NOME ALTERADO PELA FONTE'
        local = focus_municipal(p)
        self.assertEqual(local['status'], 'partial')
        self.assertEqual(len(local['alerts']), 1)
        notice = civil_defense_notice(local, NOW)
        self.assertIn('ABRANGÊNCIA A CONFIRMAR', notice['body'])

    def test_boundary_margin_and_inclusive_reference(self):
        c = copy.deepcopy(load_focus())
        c['regions'][0]['distance_km'] = 4.0
        self.assertEqual(len(focus_municipal(product(1), c)['alerts']), 1)
        c['regions'][0]['distance_km'] = 4.1
        self.assertEqual(len(focus_municipal(product(1), c)['alerts']), 1)
        c['regions'][0]['distance_km'] = 4.101
        self.assertEqual(focus_municipal(product(1), c)['alerts'], [])

    def test_station_distance_priority_and_no_twelve_hour_claim(self):
        c = load_focus()['center']
        rows = [dict(id=str(i), name=f'Estação {i}', latitude=c['lat'] + offset, longitude=c['lon'],
                     station_type='METEOROLOGICAL', sensor_readings=[dict(sensor_type='accumulated_rain', value=22, unit='mm')])
                for i, offset in enumerate([.06, .03, .01, .02])]
        result = parse_poa_stations(rows, NOW)
        self.assertEqual([s['name'] for s in result['stations']], ['Estação 2', 'Estação 3', 'Estação 1'])
        self.assertTrue(all(s['within_focus'] for s in result['stations']))
        self.assertIn('não usar para validar 20 mm/12h', result['limitation'])
        self.assertTrue(result['optional'])

    def test_only_far_station_is_explicitly_outside(self):
        c = load_focus()['center']
        row = dict(id='far', name='Externa', latitude=c['lat'] + .06, longitude=c['lon'],
                   station_type='METEOROLOGICAL', sensor_readings=[])
        result = parse_poa_stations([row], NOW)
        self.assertFalse(result['stations'][0]['within_focus'])

    def test_unavailable_source_does_not_become_empty_ok(self):
        raw = dict(status='unavailable', error='Falha')
        self.assertEqual(focus_municipal(raw), raw)

    def test_cptec_near_point_can_warn_but_regional_point_is_context(self):
        primary = dict(status='ok', triggered=False, start='a', end='b')
        cptec = dict(status='ok', signal_12h=True, start='a', end='b')
        for km, expected in [(3, True), (4.1, True), (7.4, False)]:
            result = compare_sources(primary, {'cptec': dict(cptec, airport_distance_km=km)})
            self.assertTrue(result['cptec_regional_attention'])
            self.assertEqual(result['cptec_attention'], expected)


if __name__ == '__main__':
    unittest.main()
