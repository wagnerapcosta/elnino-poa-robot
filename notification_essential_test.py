"""Three explicitly authorized Essencial examples, with no weather collection."""
import copy
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from mobile_layout import forecast_body
from operational_notices import civil_defense_notice
from rain_alert import TZ, rain_alert
from robot import build_mobile_summary, notify_ntfy


def examples(now=None):
    now = now or datetime.now(TZ)
    start = now.replace(minute=0, second=0, microsecond=0)
    f = dict(dates=[now.date().isoformat()], p24_max_mm=50.9, p72_max_mm=55.9, gust_max_kmh=47.5,
             rain_12h=dict(status='ok', total_mm=10, triggered=False,
                           start=start.isoformat(), end=(start + timedelta(hours=12)).isoformat()))
    summary = build_mobile_summary('laranja', 'amarelo', f, {}, {},
                                  ['Realizar alinhamento preventivo com SMS, Operações, APOC e Manutenção.'],
                                  ['Previsão quantitativa: Chuva prevista em nível laranja: 24h=50.9 mm; 72h=55.9 mm.'])
    municipal = civil_defense_notice(dict(status='ok', airport_focus={'geometry_verified': True}, alerts=[dict(
        criticality='very_high_risk', label='Alerta de risco muito alto', title_label='RISCO MUITO ALTO',
        types=['Chuva intensa e vento forte'],
        description='Cenário fictício: chuva intensa, rajadas de 60,4 km/h e risco de alagamentos.',
        start=start.isoformat(), end=(start+timedelta(hours=3)).isoformat(), active_now=True,
        timezone_assumed=False, regions=[dict(order=1, name='Humaitá/Navegantes — REGIÃO SIMULADA')])]), now)
    source = dict(latitude=-29.9946, longitude=-51.1667, timezone='America/Sao_Paulo',
                  hourly_units={'precipitation': 'mm'}, hourly={
                      'time': [(start+timedelta(hours=i)).isoformat() for i in range(1, 13)],
                      'precipitation': [2]*10+[0]*2})
    exact = rain_alert(source, now)
    assert exact['triggered'] is True and exact['total_mm'] == 20
    rain_forecast = copy.deepcopy(f)
    rain_forecast['rain_12h'] = exact
    rows = [dict(title='SBPA | Radar El Nino POA', body=summary, level='laranja'),
            municipal,
            dict(title='SBPA | ALERTA chuva >=20 mm/12h',
                 body=forecast_body(rain_forecast, action='Acompanhar a previsão e as condições locais.'), level='laranja')]
    for row in rows:
        row['title'] = 'TESTE — DADOS SIMULADOS | ' + row['title']
        row['body'] = ('TESTE — DADOS SIMULADOS\nCenário fictício; nenhuma ação operacional é necessária.\n\n' + row['body'])
    return rows


def production_hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path('data').rglob('*')) if p.is_file()}


def run_test(notify=None):
    notify = notify or notify_ntfy
    before = production_hashes()
    result = dict(test=True, simulated=True, accepted=[], complete=False)
    try:
        for index, row in enumerate(examples()):
            if index:
                time.sleep(10)
            accepted = notify(row['title'], row['body'], row['level']) is True
            result['accepted'].append(dict(title=row['title'], accepted=accepted))
            print(json.dumps(result['accepted'][-1], ensure_ascii=False), flush=True)
            if not accepted:
                raise RuntimeError('Teste não confirmado; não repetir os já aceitos')
        result['complete'] = True
    finally:
        result['production_data_untouched'] = before == production_hashes()
        Path('reports').mkdir(exist_ok=True)
        Path('reports/notification_essential_test.json').write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        assert result['production_data_untouched']
    return result


if __name__ == '__main__':
    run_test()
