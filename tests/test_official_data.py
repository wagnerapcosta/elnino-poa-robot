import copy
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, Mock
import requests
import official_data as o
from rain_alert import TZ
from test_rain_alert import payload, NOW


def cptec(amount=2):
    base = NOW.astimezone(timezone.utc).replace(hour=0, minute=0)
    return {'datasets': [{'lat': -30.0331, 'lon': -51.23, 'data': [
        {'date': base.strftime('%Y-%m-%d %H:%M:%S'), 'fcst': i, 'prec': amount, 'sprec': 999}
        for i in range(72)]}]}


def poa():
    return dict(last_updated_forecast=NOW.astimezone(timezone.utc).isoformat(), previsions=[
        dict(prevision_date='2026-11-04', show_forecast=True, rain_quantity=20, climate='rain')])


def warning(**kw):
    row=dict(id=1, geocodes='123,4314902', encerrado=False, inicio='2026-11-04 18:00',
             fim='2026-11-05 00:00', descricao='Tempestade', severidade='Perigo')
    row.update(kw)
    return row


def parsed_cptec(amount=2):
    return dict(status='ok', source='CPTEC/INPE', url=o.CPTEC_URL, fetched_at=NOW.isoformat(),
                **o.parse_cptec(cptec(amount), NOW))


def primary(total=20):
    from rain_alert import rain_alert
    return rain_alert(payload(total),NOW)


class OfficialTests(unittest.TestCase):
    def test_cptec_utc_12h_and_no_cumulative_double_count(self):
        r=o.parse_cptec(cptec(),NOW)
        self.assertEqual(r['alignment_start_mm'],24)
        self.assertEqual(r['alignment_end_mm'],24)
        self.assertTrue(r['signal_12h'])
        self.assertEqual(r['start'], '2026-11-04T18:00:00-03:00')
        self.assertEqual(r['end'], '2026-11-05T06:00:00-03:00')
        self.assertGreater(r['airport_distance_km'],7)

    def test_cptec_inclusive_20(self):
        p=cptec(0)
        for i in (21,22):p['datasets'][0]['data'][i]['prec']=20
        # timestamp 21UTC = 18BRT; sensitivity windows both include 22UTC
        r=o.parse_cptec(p,NOW)
        self.assertEqual(r['alignment_start_mm'],40)
        self.assertEqual(r['alignment_end_mm'],20)
        self.assertTrue(r['signal_12h'])

    def test_cptec_alignment_sensitive_is_inconclusive(self):
        p=cptec(0);p['datasets'][0]['data'][21]['prec']=20
        r=o.parse_cptec(p,NOW)
        self.assertIsNone(r['signal_12h'])
        c=o.compare_sources(primary(),{'cptec':dict(status='ok',**r)})
        self.assertIn('inconclusiva',c['state'])
        self.assertFalse(c['cptec_attention'])

    def test_cptec_bad_data(self):
        cases=[]
        p=cptec();p['datasets'][0]['lat']=0;cases.append(p)
        p=cptec();p['datasets'][0]['data'][3]['prec']=None;cases.append(p)
        p=cptec();p['datasets'][0]['data'][3]['fcst']=4;cases.append(p)
        p=cptec();p['datasets'][0]['data'][3]['date']='2026-11-03 00:00:00';cases.append(p)
        for p in cases:
            with self.assertRaises((ValueError,KeyError)):o.parse_cptec(p,NOW)
        with self.assertRaises(ValueError):o.parse_cptec(cptec(),NOW+timedelta(days=3))
        with self.assertRaises(ValueError):o.parse_cptec(cptec(),NOW-timedelta(days=1))

    def test_poa_daily_20_never_becomes_12h(self):
        p=o.parse_poa(poa(),NOW)
        self.assertEqual(p['daily'][0]['rain_mm'],20)
        c=o.compare_sources(primary(0),{'poa':dict(status='ok',**p)},payload())
        self.assertFalse(c['cptec_attention'])
        self.assertEqual(c['daily_pairs'][0]['poa_mm'],20)
        self.assertIn('inconclusiva',c['state'])

    def test_poa_invalid_stale_missing_and_zero(self):
        p=poa();p['previsions'][0]['rain_quantity']=0
        self.assertEqual(o.parse_poa(p,NOW)['daily'][0]['rain_mm'],0)
        p['previsions'][0]['rain_quantity']=None
        with self.assertRaises(ValueError):o.parse_poa(p,NOW)
        with self.assertRaises(ValueError):o.parse_poa(poa(),NOW+timedelta(days=3))
        p=poa();p['previsions'][0]['show_forecast']=False
        with self.assertRaises(ValueError):o.parse_poa(p,NOW)
        p=poa();p['previsions'].append(p['previsions'][0].copy())
        with self.assertRaises(ValueError):o.parse_poa(p,NOW)

    def test_inmet_forecast_locality_and_no_mm_inference(self):
        p={'4314902': {'04/11/2026': {'tarde': dict(uf='RS',entidade='Porto Alegre',resumo='Chuva intensa')}}}
        r=o.parse_inmet_forecast(p,NOW)
        self.assertEqual(r['forecasts'][0]['summary'],'Chuva intensa')
        self.assertIsNone(r['issued_at'])
        p['4314902']['04/11/2026']['tarde']['entidade']='Curitiba'
        with self.assertRaises(ValueError):o.parse_inmet_forecast(p,NOW)

    def test_inmet_warnings_geocode_validity_dedup(self):
        p={'hoje':[warning(),warning(),warning(id=2,geocodes='14314902'),warning(id=3,encerrado=True),
                   warning(id=4,fim='2026-11-04 18:00')], 'futuro':[warning(id=5,inicio='2026-11-05 07:00',fim='2026-11-05 10:00')]}
        r=o.parse_inmet_warnings(p,NOW)
        self.assertEqual(len(r['warnings']),1)
        self.assertTrue(r['warnings'][0]['active_now'])
        self.assertEqual(r['warnings'][0]['start'],'2026-11-04T18:00:00-03:00')

    def test_inmet_malformed_warning_is_partial_not_no_alert(self):
        r=o.parse_inmet_warnings({'hoje':[warning(inicio='bad')],'futuro':[]},NOW)
        self.assertEqual(r['skipped_records'],1)
        with self.assertRaises(ValueError):o.parse_inmet_warnings({},NOW)

    def test_comparison_preserves_primary(self):
        p=primary(20);original=copy.deepcopy(p)
        c=o.compare_sources(p,{'cptec':parsed_cptec(0)})
        self.assertIn('divergência',c['state'])
        self.assertEqual(p,original)
        self.assertTrue(p['triggered'])
        c=o.compare_sources(primary(0),{'cptec':parsed_cptec(2)})
        self.assertTrue(c['cptec_attention'])
        c=o.compare_sources(primary(20),{'cptec':parsed_cptec(2)})
        self.assertIn('acima',c['state'])

    def test_mismatched_windows_not_compared(self):
        c=parsed_cptec();c['start']='2026-11-04T19:00:00-03:00'
        r=o.compare_sources(primary(0),{'cptec':c})
        self.assertIn('inconclusiva',r['state']);self.assertFalse(r['cptec_attention'])

    def test_unavailable_primary_can_have_cptec_attention(self):
        r=o.compare_sources({'status':'unavailable','triggered':None},{'cptec':parsed_cptec()})
        self.assertTrue(r['cptec_attention'])
        self.assertIn('inconclusiva',r['state'])

    def test_transport_failure_and_malformed_json_are_not_zero(self):
        for side_effect in [requests.Timeout('tempo esgotado'), ValueError('JSON inválido')]:
            with patch.object(o.requests,'get',side_effect=side_effect):
                r=o.collect_official_data(NOW)
            self.assertEqual(len(r),5)
            self.assertTrue(all(p['status']=='unavailable' and p['error'] for p in r.values()))

    def test_rain_mode_does_not_cancel_primary_or_hide_cptec(self):
        import robot
        for total,cp,expected_title in [(20,0,'ALERTA'),(0,2,'ATENCAO'),(0,0,None)]:
            f=robot.classify_forecast(payload(total),NOW)
            with patch.object(robot,'collect_official_data',return_value={'cptec':parsed_cptec(cp)}), patch.object(robot,'Path'), patch.object(robot,'ensure_dirs'), patch.object(robot,'save_report'), patch.object(robot,'classify_forecast',return_value=f), patch.object(robot,'collect_open_meteo',return_value={'status':'ok','json':payload(total)}), patch.object(robot,'notify_ntfy',return_value=True) as notify, patch.dict('os.environ',{'RUN_MODE':'rain_alert'}):
                robot.main(notification_state=robot.NotificationState())
                if expected_title:self.assertIn(expected_title,notify.call_args.args[0])
                else:notify.assert_not_called()


if __name__=='__main__':unittest.main()
