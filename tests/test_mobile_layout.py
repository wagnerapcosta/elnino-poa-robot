import copy
from email.header import decode_header, make_header
import unittest
from unittest.mock import Mock, patch

import robot
from mobile_layout import integer, forecast_body, short_reason
from notification_essential_test import examples, run_test
from operational_notices import civil_defense_notice
from test_notification_state import forecast
from test_operational_notices import municipal, regions, alert
from test_rain_alert import NOW


class EssencialTests(unittest.TestCase):
    def test_summary_keeps_requested_fields_without_diagnostics(self):
        f = forecast(10)
        f.update(p24_max_mm=50.9, p72_max_mm=55.9, gust_max_kmh=47.5)
        original = copy.deepcopy(f)
        body = robot.build_mobile_summary('laranja', 'amarelo', f, {'failed_sources': ['Fonte ruim']},
                                          {'status': 'ok'}, ['Alinhamento preventivo.'],
                                          ['Previsão quantitativa: Chuva prevista em nível laranja: 24h=50.9 mm; 72h=55.9 mm.'])
        for text in ['Risco: LARANJA', 'Chuva 12h: 10 mm', 'Chuva dia (máx.): 51 mm',
                     'Chuva 3 dias (máx.): 56 mm', 'Rajada máx.: 48 km/h', 'Motivo:', 'Ação:']:
            self.assertIn(text, body)
        for removed in ['tático', 'ENOS', 'Confiabilidade', 'METAR', 'Fontes com erro', 'Fonte ruim', '50.9', '47.5']:
            self.assertNotIn(removed, body)
        self.assertEqual(f, original)

    def test_rounding_does_not_turn_below_threshold_into_twenty(self):
        for value, label, triggered in [(19.99, '<20', False), (20, '20', True), (20.01, '20', True)]:
            f = forecast(value)
            self.assertEqual(f['rain_12h']['triggered'], triggered)
            self.assertIn(f'Chuva 12h: {label} mm', forecast_body(f))
            self.assertEqual(f['rain_12h']['total_mm'], value)

    def test_round_half_up_and_invalid_values(self):
        self.assertEqual(integer(47.5), '48')
        self.assertEqual(integer(2.5), '3')
        for invalid in [None, True, float('nan'), float('inf'), -1]:
            self.assertEqual(integer(invalid), 'indisponível')

    def test_failed_hourly_not_shown_as_zero(self):
        f = forecast(0)
        f['rain_12h'].update(status='unavailable', total_mm=None)
        self.assertIn('Chuva 12h: indisponível', forecast_body(f))
        self.assertNotIn('Chuva 12h: 0 mm', forecast_body(f))
        self.assertNotIn('atingiu', short_reason('Chuva 12h: INDISPONÍVEL — falha'))

    def test_exact_requested_municipal_title_and_conditions_first(self):
        p = regions()
        p[0]['alert'] = alert(criticality='very_high_risk', alert_description='Chuva de 20,5 mm e rajadas de 47.5 km/h.')
        product = municipal(p)
        original = copy.deepcopy(product)
        notice = civil_defense_notice(product, NOW)
        self.assertEqual(notice['title'], 'SBPA | Defesa Civil | Alerta Vermelho')
        self.assertTrue(notice['body'].startswith('Chuva intensa'))
        self.assertIn('21 mm', notice['body'])
        self.assertIn('48 km/h', notice['body'])
        self.assertEqual(product, original)

    def test_utf8_title_and_native_source_action_without_network(self):
        title = 'TESTE — DADOS SIMULADOS | SBPA | Defesa Civil | Alerta Vermelho'
        with patch.dict('os.environ', {'NTFY_TOPIC': 'ISOLATED_TEST'}), patch.object(robot.requests, 'post') as post:
            self.assertTrue(robot.notify_ntfy(title, 'Condições fictícias.', 'vermelho'))
        headers = post.call_args.kwargs['headers']
        self.assertEqual(str(make_header(decode_header(headers['Title']))), title)
        self.assertNotIn('\n', headers['Title'])
        self.assertEqual(headers['Priority'], 'urgent')
        self.assertEqual(headers['Actions'], 'view, Abrir fonte, https://prefeitura.poa.br/poaclima/')
        self.assertEqual(post.call_args.kwargs['data'], 'Condições fictícias.'.encode('utf-8'))

    def test_three_examples_are_unambiguously_simulated(self):
        rows = examples(NOW)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertTrue(row['title'].startswith('TESTE — DADOS SIMULADOS'))
            self.assertTrue(row['body'].startswith('TESTE — DADOS SIMULADOS'))
            self.assertIn('nenhuma ação operacional é necessária', row['body'])
            self.assertLess(len(row['body'].encode('utf-8')), 4096)
        self.assertIn('Defesa Civil | Alerta Vermelho', rows[1]['title'])
        self.assertIn('Chuva 12h: 20 mm', rows[2]['body'])


if __name__ == '__main__':
    unittest.main()
