import copy
import unittest
from datetime import timedelta
from unittest.mock import patch
import requests
from official_data import parse_poa_alerts
from operational_notices import primary_failure_notice, civil_defense_notice, send_additional_notices
from test_rain_alert import NOW,payload


def regions():
    return [dict(order=i,name=f'Região {i}') for i in range(1,18)]


def alert(**kw):
    a=dict(id=1,criticality='high_risk',start_date=(NOW-timedelta(hours=1)).isoformat(),
           end_date=(NOW+timedelta(hours=3)).isoformat(),alert_types=[dict(name='Chuva intensa')],
           alert_description='<p>Alerta oficial de teste de unidade.</p>')
    a.update(kw)
    return a


def municipal(rows=None):
    if rows is None:
        rows=regions();rows[0]['alert']=alert()
    return dict(source='Defesa Civil POA',url='https://prefeitura.poa.br/poaclima/',fetched_at=NOW.isoformat(),
                status='ok',**parse_poa_alerts(rows,NOW))


class OperationalTests(unittest.TestCase):
    def test_complete_no_alert_is_not_api_failure(self):
        p=municipal(regions())
        self.assertEqual(p['region_count'],17)
        self.assertEqual(p['skipped_records'],0)
        self.assertEqual(p['alerts'],[])
        self.assertIsNone(civil_defense_notice(p,NOW))

    def test_expired_ignored_future_retained_and_explicit(self):
        p=regions();p[0]['alert']=alert(end_date=(NOW-timedelta(minutes=1)).isoformat())
        p[1]['alert']=alert(start_date=(NOW+timedelta(days=2)).isoformat(),end_date=(NOW+timedelta(days=3)).isoformat())
        r=municipal(p)
        self.assertEqual(len(r['alerts']),1)
        self.assertFalse(r['alerts'][0]['active_now'])
        self.assertIn('início futuro',civil_defense_notice(r,NOW)['body'])

    def test_group_same_alert_across_regions(self):
        p=regions();p[0]['alert']=alert();p[1]['alert']=alert()
        r=municipal(p)
        self.assertEqual(len(r['alerts']),1)
        self.assertEqual(len(r['alerts'][0]['regions']),2)
        n=civil_defense_notice(r,NOW)
        self.assertIn('Região 1, Região 2',n['body'])
        self.assertIn('DEFESA CIVIL POA',n['title'])
        self.assertIn('não equivalem',n['body'])

    def test_source_levels_and_priority_remain_distinct(self):
        for criticality,level,title in [('attention_notice','amarelo','AVISO DE ATENCAO'),('high_risk','laranja','RISCO ALTO'),('very_high_risk','vermelho','RISCO MUITO ALTO'),('extreme_risk','vermelho','RISCO EXTREMO')]:
            p=regions();p[0]['alert']=alert(criticality=criticality)
            n=civil_defense_notice(municipal(p),NOW)
            self.assertEqual(n['level'],level);self.assertIn(title,n['title'])

    def test_invalid_level_or_dates_degrades_not_no_risk(self):
        for a in [alert(criticality='unknown'),alert(start_date='invalid'),alert(end_date=(NOW-timedelta(days=3)).isoformat())]:
            p=regions();p[0]['alert']=a
            r=parse_poa_alerts(p,NOW)
            self.assertEqual(r['skipped_records'],1)
        with self.assertRaises(ValueError):parse_poa_alerts([],NOW)
        p=regions();p[1]['order']=1
        with self.assertRaises(ValueError):parse_poa_alerts(p,NOW)

    def test_missing_region_is_partial_coverage(self):
        r=parse_poa_alerts(regions()[:-1],NOW)
        self.assertEqual(r['skipped_records'],1)
        self.assertEqual(r['region_count'],16)

    def test_naive_source_time_is_explicit_and_html_sanitized(self):
        p=regions();p[0]['alert']=alert(start_date='2026-11-04T17:00:00',end_date='2026-11-05T03:00:00',alert_description='<script>secret()</script><b>Orientação oficial</b>')
        r=municipal(p)
        self.assertTrue(r['alerts'][0]['timezone_assumed'])
        n=civil_defense_notice(r,NOW)
        self.assertIn('sem fuso explícito',n['body'])
        self.assertNotIn('secret()',n['body']);self.assertNotIn('<b>',n['body'])

    def test_noRisk_and_unavailable_do_not_emit(self):
        p=regions();p[0]['alert']={'criticality':'noRisk'}
        self.assertEqual(parse_poa_alerts(p,NOW)['alerts'],[])
        self.assertIsNone(civil_defense_notice({'status':'unavailable'},NOW))

    def test_notice_prioritizes_severe_and_limits_payload(self):
        p=regions()
        for i in range(17):p[i]['alert']=alert(id=i,criticality='extreme_risk' if i==16 else 'attention_notice',alert_description='Descrição muito longa '*400)
        n=civil_defense_notice(municipal(p),NOW)
        self.assertIn('RISCO EXTREMO',n['title'])
        self.assertLess(n['body'].index('risco extremo'),n['body'].index('Aviso de atenção'))
        self.assertLess(len(n['body'].encode('utf-8')),4096)

    def test_failure_notice_transport_hourly_and_daily(self):
        for collection,f in [({'status':'error'},{}),({'status':'ok'},{'data_status':'unavailable','rain_12h':{'status':'unavailable'}}),({'status':'ok'},{'data_status':'unavailable','rain_12h':{'status':'ok'}})]:
            n=primary_failure_notice(collection,f,NOW)
            self.assertIn('FALHA',n['title'])
            self.assertIn('DADOS INDISPONÍVEIS NÃO SIGNIFICAM AUSÊNCIA DE RISCO',n['body'])
        self.assertIsNone(primary_failure_notice({'status':'ok'},{'data_status':'ok'},NOW))

    def test_delivery_failure_does_not_block_other_notice_or_leak_topic(self):
        calls=[]
        def send(title,body,level):
            calls.append(title)
            if len(calls)==1:raise requests.Timeout('https://ntfy.sh/PRIVATE_TOPIC')
            return True
        notices=[dict(title='Falha',body='teste',level='laranja'),dict(title='Municipal',body='teste',level='amarelo')]
        results=send_additional_notices(notices,send)
        self.assertEqual(len(calls),2);self.assertTrue(results[1]['accepted'])
        self.assertNotIn('PRIVATE_TOPIC',str(results))

    def test_main_failure_sends_failure_and_municipal_before_error(self):
        import robot
        with patch.object(robot,'collect_official_data',return_value={'poa_alerts':municipal()}),patch.object(robot,'Path'),patch.object(robot,'ensure_dirs'),patch.object(robot,'save_report'),patch.object(robot,'collect_open_meteo',return_value={'status':'error','json':{}}),patch.object(robot,'notify_ntfy',return_value=True) as notify,patch.dict('os.environ',{'RUN_MODE':'rain_alert'}):
            with self.assertRaisesRegex(RuntimeError,'indisponível'):robot.main(notification_state=robot.NotificationState())
            self.assertEqual(notify.call_count,2)
            titles=[c.args[0] for c in notify.call_args_list]
            self.assertIn('FALHA',titles[0]);self.assertIn('DEFESA CIVIL',titles[1])

    def test_main_malformed_json_still_sends_failure(self):
        import robot
        with patch.object(robot,'collect_official_data',return_value={}),patch.object(robot,'Path'),patch.object(robot,'ensure_dirs'),patch.object(robot,'save_report'),patch.object(robot,'collect_open_meteo',return_value={'status':'ok','json':[]}),patch.object(robot,'notify_ntfy',return_value=True) as notify,patch.dict('os.environ',{'RUN_MODE':'rain_alert'}):
            with self.assertRaisesRegex(RuntimeError,'indisponível'):robot.main(notification_state=robot.NotificationState())
            self.assertIn('FALHA',notify.call_args.args[0])

    def test_daily_schema_failure_does_not_cancel_valid_12h_alert(self):
        import robot
        variants=[]
        p=payload(20);p['daily']=[];variants.append(p)
        p=payload(20);p['daily']['precipitation_sum']=3;variants.append(p)
        p=payload(20);p['daily_units']=[];variants.append(p)
        p=payload(20);p['daily']['time']=[[],[],[]];variants.append(p)
        for p in variants:
            with patch.object(robot,'collect_official_data',return_value={}),patch.object(robot,'Path'),patch.object(robot,'ensure_dirs'),patch.object(robot,'save_report'),patch.object(robot,'now_brt',return_value=NOW),patch.object(robot,'collect_open_meteo',return_value={'status':'ok','json':p}),patch.object(robot,'notify_ntfy',return_value=True) as notify,patch.dict('os.environ',{'RUN_MODE':'rain_alert'}):
                robot.main(notification_state=robot.NotificationState())
                self.assertEqual(notify.call_count,2)
                self.assertIn('FALHA',notify.call_args_list[0].args[0])
                self.assertIn('12 horas permanece disponível',notify.call_args_list[0].args[1])
                self.assertIn('ALERTA chuva',notify.call_args_list[1].args[0])


if __name__=='__main__':unittest.main()
