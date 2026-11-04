import copy
import csv
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from notification_state import NotificationState
from test_rain_alert import NOW, payload
from test_operational_notices import municipal, regions, alert


def healthy():return {'status':'ok'},{'data_status':'ok','rain_12h':{'status':'ok','triggered':False}}
def outage(kind='transport'):
    return {'status':'error' if kind=='transport' else 'ok'}, {'data_status':'unavailable','rain_12h':{'status':'ok' if kind=='daily' else 'unavailable'}}
def forecast(total=20):
    import robot
    return robot.classify_forecast(payload(total),NOW)
def notice():return dict(title='Radar POA - ALERTA chuva >=20 mm/12h',body='conteúdo de teste',level='laranja')


class StateTests(unittest.TestCase):
    def test_initial_healthy_does_not_claim_recovery(self):
        s=NotificationState();n=Mock(return_value=True)
        self.assertEqual(s.collection(*healthy(),NOW,n),[]);n.assert_not_called()

    def test_outage_once_recovery_once_and_new_episode(self):
        s=NotificationState();n=Mock(return_value=True)
        for i in range(3):s.collection(*outage(),NOW+timedelta(hours=i),n)
        self.assertEqual(n.call_count,1)
        s.collection(*healthy(),NOW+timedelta(hours=3),n)
        self.assertIn('NORMALIZADA',n.call_args.args[0])
        self.assertIn('NÃO significa ausência de risco',n.call_args.args[1])
        s.collection(*healthy(),NOW+timedelta(hours=4),n)
        self.assertEqual(n.call_count,2)
        s.collection(*outage(),NOW+timedelta(hours=5),n)
        self.assertEqual(n.call_count,3)

    def test_changed_outage_scope_is_an_update_not_poll_time(self):
        s=NotificationState();n=Mock(return_value=True)
        s.collection(*outage(),NOW,n);s.collection(*outage('hourly'),NOW,n)
        self.assertEqual(n.call_count,2);self.assertIn('ATUALIZACAO',n.call_args.args[0])
        s.collection(*outage('hourly'),NOW+timedelta(hours=1),n);self.assertEqual(n.call_count,2)

    def test_failed_send_retries_and_failed_recovery_keeps_episode(self):
        s=NotificationState();n=Mock(side_effect=[False,True,False,True])
        self.assertEqual(s.collection(*outage(),NOW,n)[0]['status'],'failed')
        s.collection(*outage(),NOW,n)
        s.collection(*healthy(),NOW,n)
        self.assertTrue(s.data['collection']['failed'])
        s.collection(*healthy(),NOW,n)
        self.assertFalse(s.data['collection']['failed']);self.assertEqual(n.call_count,4)

    def test_restart_preserves_failure_and_sent_baselines(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';n=Mock(return_value=True)
            s=NotificationState(path);s.collection(*outage(),NOW,n)
            s=NotificationState(path);s.collection(*outage(),NOW+timedelta(hours=1),n)
            self.assertEqual(n.call_count,1)
            s.collection(*healthy(),NOW+timedelta(hours=2),n)
            s=NotificationState(path);s.collection(*healthy(),NOW+timedelta(hours=3),n)
            self.assertEqual(n.call_count,2)

    def test_corrupt_store_is_not_silently_reset(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';path.write_text('{bad',encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'inválida'):NotificationState(path)

    def test_municipal_ignores_poll_clock_regenerated_id_and_format_only(self):
        s=NotificationState();n=Mock(return_value=True);p=municipal()
        s.municipal(p,NOW,n)
        p['fetched_at']=(NOW+timedelta(hours=1)).isoformat()
        p['alerts'][0]['source_id']='new-provider-id'
        p['alerts'][0]['description']='   ALERTA OFICIAL DE TESTE DE UNIDADE.   '
        s.municipal(p,NOW+timedelta(hours=1),n)
        self.assertEqual(n.call_count,1)
        entry=s.data['events']['municipal:1']['signature']
        self.assertIn('description_sha256',entry);self.assertNotIn('description',entry)

    def test_municipal_level_period_type_description_region_changes_notify(self):
        for field,value in [('criticality','very_high_risk'),('end',(NOW+timedelta(hours=5)).isoformat()),
                            ('description','Nova orientação importante'),('types',['Granizo'])]:
            s=NotificationState();n=Mock(return_value=True);p=municipal();s.municipal(p,NOW,n)
            p['alerts'][0][field]=value
            if field=='criticality':p['alerts'][0].update(title_label='RISCO MUITO ALTO',label='Alerta de risco muito alto')
            s.municipal(p,NOW,n);self.assertEqual(n.call_count,2)
            self.assertIn('ATUALIZACAO',n.call_args.args[0])

    def test_only_changed_regions_are_forwarded(self):
        rows=regions();rows[0]['alert']=alert();rows[1]['alert']=alert()
        p=municipal(rows);s=NotificationState();n=Mock(return_value=True);s.municipal(p,NOW,n)
        # Region 1 changes; region 2 keeps its previous alert.
        rows[0]['alert']=alert(criticality='extreme_risk');p=municipal(rows)
        s.municipal(p,NOW,n)
        self.assertIn('Região 1',n.call_args.args[1]);self.assertNotIn('Região 2',n.call_args.args[1])
        self.assertEqual(n.call_count,2)

    def test_missing_or_partial_source_does_not_clear_event(self):
        s=NotificationState();n=Mock(return_value=True);p=municipal();s.municipal(p,NOW,n)
        s.municipal({'status':'unavailable'},NOW,n)
        s.municipal({'status':'partial','alerts':[]},NOW,n)
        s.municipal(p,NOW,n);self.assertEqual(n.call_count,1)
        s.municipal(municipal(regions()),NOW,n)
        s.municipal(p,NOW,n);self.assertEqual(n.call_count,2)

    def test_expiration_of_other_region_does_not_repeat_remaining_alert(self):
        rows=regions();rows[0]['alert']=alert();rows[1]['alert']=alert()
        s=NotificationState();n=Mock(return_value=True);s.municipal(municipal(rows),NOW,n)
        del rows[0]['alert'];s.municipal(municipal(rows),NOW,n)
        self.assertEqual(n.call_count,1);self.assertFalse(s.data['events']['municipal:1']['active'])

    def test_municipal_failed_send_is_not_suppressed_next_poll(self):
        s=NotificationState();n=Mock(side_effect=[False,True]);p=municipal()
        s.municipal(p,NOW,n);s.municipal(p,NOW,n);self.assertEqual(n.call_count,2)

    def test_rain_rolling_clock_and_small_changes_do_not_repeat(self):
        s=NotificationState();n=Mock(return_value=True);f=forecast(20)
        s.rain(f,{}, {},notice(),NOW,n)
        f['rain_12h']['start']=(NOW+timedelta(hours=1)).isoformat()
        s.rain(f,{}, {},notice(),NOW+timedelta(hours=1),n)
        s.rain(forecast(24),{}, {},notice(),NOW,n)
        self.assertEqual(n.call_count,1)
        s.rain(forecast(25),{}, {},notice(),NOW,n)
        self.assertEqual(n.call_count,2)
        s.rain(forecast(30),{}, {},notice(),NOW,n);self.assertEqual(n.call_count,2)
        s.rain(forecast(32),{}, {},notice(),NOW,n);self.assertEqual(n.call_count,3)

    def test_rain_unavailability_does_not_reset_but_valid_below_threshold_rearms(self):
        s=NotificationState();n=Mock(return_value=True)
        s.rain(forecast(20),{},{},notice(),NOW,n)
        s.rain({'rain_12h':{'status':'unavailable','triggered':None}},{},{},notice(),NOW,n)
        s.rain(forecast(20),{},{},notice(),NOW,n);self.assertEqual(n.call_count,1)
        s.rain(forecast(19),{},{},notice(),NOW,n)
        s.rain(forecast(20),{},{},notice(),NOW,n);self.assertEqual(n.call_count,2)

    def test_general_level_or_material_metrics_only_and_history_seed(self):
        s=NotificationState();n=Mock(return_value=True)
        f=forecast(0);f.update(general_level='laranja',p24_max_mm=100,p72_max_mm=100,gust_max_kmh=50)
        s.general(f,notice(),NOW,n)
        f['p24_max_mm']=110;s.general(f,notice(),NOW,n);self.assertEqual(n.call_count,1)
        f['p24_max_mm']=125;s.general(f,notice(),NOW,n);self.assertEqual(n.call_count,2)
        f['gust_max_kmh']=60;s.general(f,notice(),NOW,n);self.assertEqual(n.call_count,3)
        f['general_level']='vermelho';s.general(f,notice(),NOW,n);self.assertEqual(n.call_count,4)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'history.csv'
            with path.open('w',newline='',encoding='utf-8') as stream:
                w=csv.DictWriter(stream,fieldnames=['tactical_level','p24_max_mm','p72_max_mm','gust_max_kmh','timestamp']);w.writeheader();w.writerow(dict(tactical_level='vermelho',p24_max_mm=125,p72_max_mm=100,gust_max_kmh=60,timestamp=NOW.isoformat()))
            s=NotificationState(history_path=path);n.reset_mock();s.general(f,notice(),NOW,n);n.assert_not_called()

    def test_same_rain_event_shared_by_hourly_daily_and_weekly(self):
        import robot
        s=NotificationState()
        with patch('builtins.print'),patch.object(robot,'collect_official_data',return_value={}),patch.object(robot,'Path'),patch.object(robot,'ensure_dirs'),patch.object(robot,'now_brt',return_value=NOW),patch.object(robot,'save_report'),patch.object(robot,'save_history'),patch.object(robot,'create_forecast_chart',return_value='test.png'),patch.object(robot,'collect_aviation_weather',return_value={'status':'ok','metar':[{}],'taf':[{}]}),patch.object(robot,'SOURCES',[]),patch.object(robot,'collect_open_meteo',return_value={'status':'ok','json':payload(20)}),patch.object(robot,'notify_ntfy',return_value=True) as n:
            for mode in ['rain_alert','daily','weekly']:
                with patch.dict('os.environ',{'RUN_MODE':mode}):robot.main(notification_state=s)
            self.assertEqual(n.call_count,1)


if __name__=='__main__':unittest.main()
