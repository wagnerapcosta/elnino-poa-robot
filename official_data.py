"""Public products linked by CPTEC, INMET and the official POA Clima portal.

Cross-checks are indicative: different locations, temporal resolutions and models.
No averaging, majority voting or cancellation of the Open-Meteo alert.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import isfinite, radians, sin, cos, asin, sqrt
import unicodedata
import hashlib
import json
import requests
from bs4 import BeautifulSoup
from rain_alert import TZ
from airport_focus import focus_municipal, distance_km, load_focus

CPTEC_URL = 'https://s1.cptec.inpe.br/grafico/Modelos/Multimodel/pag_web/horario/1276.json'
INMET_URL = 'https://apiprevmet3.inmet.gov.br/previsao/4314902'
INMET_WARNINGS_URL = 'https://apiprevmet3.inmet.gov.br/avisos/ativos'
POA_URL = 'https://api.helpertecnologia.com.br/defesa-civil/bff/climate/previsions/poadc'
POA_ALERTS_URL = 'https://api.helpertecnologia.com.br/defesa-civil/bff/climate/alert/public/poadc/grouped-by-region'
POA_STATIONS_URL = 'https://api.helpertecnologia.com.br/defesa-civil/bff/public/dashboard/weather-monitor/poadc?station_type=METEOROLOGICAL'
IBGE = '4314902'
POA_LEVELS = {
    'attention_notice': ('Aviso de atenção', 'AVISO DE ATENCAO'),
    'high_risk': ('Alerta de risco alto', 'RISCO ALTO'),
    'very_high_risk': ('Alerta de risco muito alto', 'RISCO MUITO ALTO'),
    'extreme_risk': ('Alerta de risco extremo', 'RISCO EXTREMO'),
}


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
        raise ValueError('Valor quantitativo ausente ou inválido')
    return Decimal(str(value))


def stamp(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp sem fuso')
    return dt


def distance(lat, lon):
    return round(distance_km(lat, lon), 1)


def parse_poa_stations(data, now):
    if not isinstance(data, list) or not data:
        raise ValueError('Lista de estações meteorológicas ausente')
    stations, skipped = [], 0
    for row in data:
        try:
            if row.get('station_type') != 'METEOROLOGICAL':
                continue
            lat, lon = float(row['latitude']), float(row['longitude'])
            if not isfinite(lat) or not isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
                raise ValueError('Coordenadas inválidas')
            km = distance_km(lat, lon)
            if km > 50:
                continue
            sensors = [dict(sensor_type=s['sensor_type'], value=float(number(s['value'])),
                            unit=s.get('unit'), source_time=s.get('created_at'))
                       for s in row.get('sensor_readings', [])
                       if s.get('sensor_type') in ('accumulated_rain', 'wind_speed') and s.get('value') is not None]
            stations.append(dict(id=str(row['id']), name=str(row['name']), lat=lat, lon=lon,
                                 distance_km=round(km, 3), within_focus=km <= load_focus()['radius_km'],
                                 readings=sensors, last_read_at=row.get('last_read_at')))
        except (KeyError, ValueError, TypeError):
            skipped += 1
    if not stations:
        raise ValueError('Nenhuma estação com localização válida próxima de SBPA')
    stations.sort(key=lambda s: s['distance_km'])
    inside = [s for s in stations if s['within_focus']]
    return dict(stations=(inside or stations[:1])[:3], skipped_records=skipped, optional=True,
                scope='Estações municipais próximas; observação complementar, não previsão em SBPA.',
                limitation='Janela do acumulado e idade efetiva da medição não documentadas nesta rota; não usar para validar 20 mm/12h.')


def parse_cptec(data, now):
    d = data['datasets'][0]
    lat, lon = d['lat'], d['lon']
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in (lat, lon)):
        raise ValueError('Coordenadas CPTEC inválidas')
    if abs(lat + 30.0331) > .02 or abs(lon + 51.23) > .02:
        raise ValueError('Ponto CPTEC diferente de Porto Alegre 1276')
    rows = d['data']
    if len(rows) < 24:
        raise ValueError('Série CPTEC insuficiente')
    base, series = None, {}
    for index, row in enumerate(rows):
        issued = datetime.strptime(row['date'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
        if base is None:
            base = issued
        if base != issued or type(row['fcst']) is not int or row['fcst'] != index:
            raise ValueError('Rodadas misturadas, horários duplicados ou lacunas CPTEC')
        series[base + timedelta(hours=index)] = number(row['prec'])
    if not timedelta(hours=-1) <= now - base <= timedelta(hours=36):
        raise ValueError('Rodada CPTEC futura ou com mais de 36h')
    start = now.astimezone(TZ).replace(minute=0, second=0, microsecond=0)
    # The official frontend labels prec as mm/h, but does not specify which
    # edge of the interval its timestamp represents. Keep both alignments.
    totals = []
    for offset in (0, 1):
        times = [start + timedelta(hours=i) for i in range(offset, offset + 12)]
        if any(t not in series for t in times):
            raise ValueError('CPTEC não cobre a janela de 12h')
        totals.append(sum(series[t] for t in times))
    flags = [v >= Decimal('20') for v in totals]
    signal = flags[0] if flags[0] == flags[1] else None
    return dict(issued_at=base.isoformat(), point={'lat': lat, 'lon': lon, 'id': 1276},
                airport_distance_km=distance(lat, lon), start=start.isoformat(),
                end=(start + timedelta(hours=12)).isoformat(),
                alignment_start_mm=float(totals[0]), alignment_end_mm=float(totals[1]),
                signal_12h=signal, interval_convention='não confirmada; sensibilidade a deslocamento de 1h',
                scope='ponto municipal, não medição em SBPA', unit='mm/h integrado em passos horários')


def parse_poa(data, now):
    issued = stamp(data['last_updated_forecast'])
    if not timedelta(hours=-1) <= now - issued <= timedelta(hours=48):
        raise ValueError('Previsão POA Clima futura ou com mais de 48h')
    today = now.astimezone(TZ).date()
    daily, seen = [], set()
    for row in data['previsions']:
        if row.get('show_forecast') is not True:
            continue
        day = datetime.strptime(row['prevision_date'], '%Y-%m-%d').date()
        if day < today or day > today + timedelta(days=6):
            continue
        if day in seen:
            raise ValueError('Data duplicada no POA Clima')
        seen.add(day)
        daily.append(dict(date=day.isoformat(), rain_mm=float(number(row['rain_quantity'])),
                          condition=str(row.get('climate', ''))))
    if today not in seen:
        raise ValueError('POA Clima sem previsão válida para hoje')
    return dict(issued_at=issued.isoformat(), daily=sorted(daily, key=lambda r: r['date']),
                scope='previsão municipal por dia civil; não repartida em 12h', unit='mm/dia')


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.lower()) if not unicodedata.combining(c))


def parse_inmet_forecast(data, now):
    days = data[IBGE]
    today = now.astimezone(TZ).date()
    forecasts = []
    for day_offset in (0, 1):
        day = today + timedelta(days=day_offset)
        item = days.get(day.strftime('%d/%m/%Y'), {})
        for turn in ('manha', 'tarde', 'noite', 'diaria'):
            r = item if turn == 'diaria' else item.get(turn, {})
            if not r.get('resumo'):
                continue
            if normalized(str(r.get('entidade', ''))) != 'porto alegre' or r.get('uf') != 'RS':
                raise ValueError('Localidade INMET incompatível')
            forecasts.append(dict(date=day.isoformat(), turn=turn, summary=str(r['resumo'])[:500]))
    if not any(r['date'] == today.isoformat() for r in forecasts):
        raise ValueError('INMET sem previsão qualitativa para hoje')
    return dict(issued_at=None, forecasts=forecasts, scope='município IBGE 4314902; previsão qualitativa, sem acumulado de 12h',
                freshness='Data de validade disponível; emissão não informada por este produto')


def parse_inmet_warnings(data, now):
    if not isinstance(data, dict) or not isinstance(data.get('hoje'), list) or not isinstance(data.get('futuro'), list):
        raise ValueError('Formato de avisos INMET inválido')
    end = now + timedelta(hours=12)
    warnings, skipped, seen = [], 0, set()
    for row in data['hoje'] + data['futuro']:
        codes = row.get('geocodes')
        if not isinstance(codes, str):
            skipped += 1
            continue
        if IBGE not in {v.strip() for v in codes.split(',')}:
            continue
        if row.get('encerrado') is True:
            continue
        try:
            if row.get('encerrado') is not False:
                raise ValueError('Estado de encerramento ausente')
            # INMET exposes local validity strings in inicio/fim; retain that
            # convention explicitly rather than reading date-only UTC fields.
            begin = datetime.strptime(row['inicio'], '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
            finish = datetime.strptime(row['fim'], '%Y-%m-%d %H:%M').replace(tzinfo=TZ)
            if finish <= begin:
                raise ValueError('Vigência inválida')
            key = str(row['id'])
            if not key.isdigit():
                raise ValueError('Identificador inválido')
            if finish <= now or begin >= end or key in seen:
                continue
            seen.add(key)
            warnings.append(dict(id=key, description=str(row['descricao'])[:200], severity=str(row.get('severidade', ''))[:100],
                                 start=begin.isoformat(), end=finish.isoformat(), active_now=begin <= now < finish,
                                 url='https://avisos.inmet.gov.br/' + key))
        except (ValueError, TypeError, KeyError):
            skipped += 1
    return dict(warnings=warnings, skipped_records=skipped, issued_at=None,
                timezone_assumption='inicio/fim tratados como horário de Brasília',
                scope='município IBGE 4314902 e sobreposição às próximas 12h; não prova 20 mm/12h em SBPA')


def parse_poa_alerts(data, now):
    if not isinstance(data, list) or not data:
        raise ValueError('POA Clima sem lista de regiões válida')
    seen, grouped, skipped = set(), {}, 0
    for region in data:
        order = region.get('order')
        if type(order) is not int or order not in range(1, 18) or order in seen:
            raise ValueError('Regiões POA Clima duplicadas ou com identificador inválido')
        name = region.get('name')
        if not isinstance(name, str) or not name.strip():
            raise ValueError('Região POA Clima sem nome')
        seen.add(order)
        alert = region.get('alert')
        # This is the public frontend's explicit no-alert representation.
        if alert is None:
            continue
        try:
            if not isinstance(alert, dict):
                raise ValueError('Alerta municipal inválido')
            criticality = alert.get('criticality')
            if criticality == 'noRisk':
                continue
            if criticality not in POA_LEVELS:
                raise ValueError('Nível municipal desconhecido')
            assumed = False
            dates = []
            for field in ('start_date', 'end_date'):
                dt = datetime.fromisoformat(alert[field].replace('Z', '+00:00'))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=TZ)
                    assumed = True
                dates.append(dt)
            begin, end = dates
            if end <= begin:
                raise ValueError('Vigência municipal inválida')
            if end <= now:
                continue
            types = alert.get('alert_types') or []
            if not isinstance(types, list) or any(not isinstance(t, dict) or not isinstance(t.get('name'), str) for t in types):
                raise ValueError('Tipos de alerta municipal inválidos')
            description = alert.get('alert_description') or 'Descrição não informada pela fonte.'
            if not isinstance(description, str):
                raise ValueError('Descrição municipal inválida')
            soup = BeautifulSoup(description, 'lxml')
            for tag in soup(['script', 'style']):
                tag.decompose()
            text = ' '.join(soup.get_text(' ').split())[:8000]
            label, title_label = POA_LEVELS[criticality]
            item = dict(criticality=criticality, label=label, title_label=title_label,
                        start=begin.isoformat(), end=end.isoformat(), active_now=begin <= now < end,
                        timezone_assumed=assumed, types=sorted({t['name'].strip()[:120] for t in types}),
                        description=text, source_id=str(alert.get('id', 'não informado')))
            fingerprint = hashlib.sha256(json.dumps(item, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
            if fingerprint not in grouped:
                grouped[fingerprint] = dict(item, regions=[])
            grouped[fingerprint]['regions'].append(dict(order=order, name=name.strip()[:100]))
        except (ValueError, TypeError, KeyError, AttributeError):
            skipped += 1
    skipped += len(set(range(1, 18)) - seen)
    return dict(alerts=list(grouped.values()), region_count=len(seen), skipped_records=skipped,
                issued_at=None, scope='Avisos/alertas municipais por região; não confirma impacto em SBPA nem acumulado de 12h')


PRODUCTS = {
    'cptec': ('CPTEC/INPE Multimodelo', CPTEC_URL, parse_cptec),
    'inmet_forecast': ('INMET previsão Porto Alegre', INMET_URL, parse_inmet_forecast),
    'inmet_warnings': ('INMET avisos', INMET_WARNINGS_URL, parse_inmet_warnings),
    'poa': ('POA Clima / Prefeitura', POA_URL, parse_poa),
    'poa_alerts': ('Defesa Civil POA / POA Clima', POA_ALERTS_URL, parse_poa_alerts),
    'poa_stations': ('Estações POA Clima próximas de SBPA', POA_STATIONS_URL, parse_poa_stations),
}


def collect_official_data(now=None):
    now = now or datetime.now(TZ)
    def fetch(key):
        name, url, parser = PRODUCTS[key]
        result = dict(source=name, url=url, fetched_at=now.isoformat(), status='unavailable', error=None,
                      optional=key == 'poa_stations')
        try:
            response = requests.get(url, timeout=25, headers={'User-Agent': 'POA-Radar/1.7', 'x-timezone': 'America/Sao_Paulo'})
            response.raise_for_status()
            result.update(parser(response.json(), now))
            result['status'] = 'partial' if result.get('skipped_records') else 'ok'
            if key == 'poa_alerts':
                result = focus_municipal(result)
        except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            result['error'] = str(exc)
        return key, result
    with ThreadPoolExecutor(max_workers=6) as pool:
        return dict(pool.map(fetch, PRODUCTS))


def compare_sources(primary, official, open_meteo_json=None):
    cptec = official.get('cptec', {})
    p_ok = primary.get('status') == 'ok'
    c_ok = cptec.get('status') == 'ok'
    c_signal = cptec.get('signal_12h') if c_ok else None
    same_window = (cptec.get('start') == primary.get('start') and cptec.get('end') == primary.get('end'))
    if not p_ok or not c_ok or not same_window or c_signal is None:
        state = 'comparação 12h inconclusiva'
    elif primary['triggered'] == c_signal:
        state = 'concordância indicativa acima do limiar' if c_signal else 'concordância indicativa abaixo do limiar'
    else:
        state = 'divergência no sinal de 20 mm/12h'
    regional_attention = c_ok and c_signal is True and (not p_ok or same_window and primary.get('triggered') is False)
    config = load_focus()
    km = cptec.get('airport_distance_km')
    local_point = isinstance(km, (float, int)) and not isinstance(km, bool) and 0 <= km <= config['radius_km'] + config['boundary_margin_km']
    attention = regional_attention and local_point
    daily_pairs = []
    forecast_payload = open_meteo_json if isinstance(open_meteo_json, dict) else {}
    daily = forecast_payload.get('daily') or {}
    daily = daily if isinstance(daily, dict) else {}
    units = forecast_payload.get('daily_units') or {}
    units = units if isinstance(units, dict) else {}
    dates, amounts = daily.get('time'), daily.get('precipitation_sum')
    dates = dates if isinstance(dates, list) else []
    amounts = amounts if isinstance(amounts, list) else []
    if units.get('precipitation_sum') == 'mm' and len(dates) == len(amounts) and all(isinstance(d, str) for d in dates):
        om_daily = dict(zip(dates, amounts))
        if official.get('poa', {}).get('status') == 'ok':
            for row in official['poa']['daily']:
                try:
                    om = number(om_daily.get(row['date']))
                    daily_pairs.append(dict(date=row['date'], open_meteo_mm=float(om), poa_mm=row['rain_mm'],
                                            difference_mm=float(number(row['rain_mm']) - om)))
                except ValueError:
                    pass
    return dict(state=state, cptec_attention=bool(attention), cptec_regional_attention=bool(regional_attention),
                cptec_point_within_focus=bool(local_point), daily_pairs=daily_pairs,
                limitation='Checagem cruzada de previsões, sem validação estatística; modelos podem compartilhar insumos. INMET e POA diário não confirmam o total de 12h.')


def official_summary(official, comparison):
    lines = ['Checagem oficial: ' + comparison['state'] + '.']
    if comparison.get('cptec_attention'):
        lines.append('ATENÇÃO COMPLEMENTAR: CPTEC sugere ultrapassagem nas duas hipóteses horárias; conferir divergência ou indisponibilidade da fonte principal.')
    elif comparison.get('cptec_regional_attention'):
        lines.append('CPTEC: sinal regional acima do limiar em ponto externo ao foco; contexto complementar, sem acionar alerta local.')
    cptec = official.get('cptec', {})
    if cptec.get('status') == 'ok':
        a, b = cptec['alignment_start_mm'], cptec['alignment_end_mm']
        lines.append(f"CPTEC/INPE: {min(a,b):.2f}–{max(a,b):.2f} mm nas duas hipóteses horárias; ponto a {cptec['airport_distance_km']:.1f} km de SBPA. Convenção do intervalo não confirmada.")
    else:
        lines.append('CPTEC/INPE: indisponível; sem checagem numérica complementar de 12h.')
    warnings = official.get('inmet_warnings', {})
    if warnings.get('status') in ('ok', 'partial'):
        lines.append(f"INMET: {len(warnings['warnings'])} aviso(s) para o município com vigência sobreposta às próximas 12h; não equivalem a 20 mm/12h.")
        if warnings.get('skipped_records'):
            lines.append(f"Consulta de avisos parcial: {warnings['skipped_records']} registro(s) não puderam ser avaliados.")
    else:
        lines.append('INMET avisos: indisponíveis; não interpretar como ausência de aviso.')
    if official.get('inmet_forecast', {}).get('status') != 'ok':
        lines.append('INMET previsão por turnos: indisponível.')
    municipal = official.get('poa_alerts', {})
    if municipal.get('status') in ('ok', 'partial'):
        area = ' no foco SBPA/4 km' if municipal.get('airport_focus') else ' municipais'
        lines.append(f"Defesa Civil POA: {len(municipal['alerts'])} aviso(s)/alerta(s){area}, consulta de {municipal['region_count']}/17 regiões.")
        if municipal.get('status') == 'partial':
            lines.append('Consulta municipal parcial; registros/regiões não avaliados não significam ausência de alerta.')
    else:
        lines.append('Defesa Civil POA: alertas indisponíveis; não interpretar como ausência de alerta.')
    if comparison.get('daily_pairs'):
        r = comparison['daily_pairs'][0]
        lines.append(f"Dia {r['date']}: POA Clima {r['poa_mm']:.1f} mm; Open-Meteo {r['open_meteo_mm']:.1f} mm. Totais diários, não 12h.")
    else:
        lines.append('POA Clima: comparação quantitativa diária indisponível.')
    stations = official.get('poa_stations', {})
    if stations.get('status') in ('ok', 'partial'):
        lines.append('Estações próximas (observação complementar): ' + '; '.join(
            f"{s['name']} ({s['distance_km']:.1f} km)" for s in stations['stations']) + '.')
    return '\n'.join(lines)


def official_report(official, comparison):
    lines = ['## Checagem cruzada com fontes oficiais', '', official_summary(official, comparison), '',
             comparison['limitation'], '',
             'CPTEC: faixa de sensibilidade horária, não intervalo de confiança. INMET: inicio/fim interpretados em horário de Brasília; emissão não informada pelo produto.',
             '', '| Produto | Estado | Coleta | Emissão | Escopo/erro |', '|---|---|---|---|---|']
    def cell(value):
        return str(value).replace('|', '/').replace('\n', ' ')
    for key, product in official.items():
        lines.append(f"| [{cell(product['source'])}]({product['url']}) | {product['status']} | {product['fetched_at']} | {product.get('issued_at') or 'não informada'} | {cell(product.get('error') or product.get('scope', ''))} |")
    for row in official.get('inmet_forecast', {}).get('forecasts', []):
        lines.append(f"- INMET {row['date']} / {row['turn']}: {cell(row['summary'])}.")
    for row in official.get('inmet_warnings', {}).get('warnings', []):
        lines.append(f"- Aviso INMET [{cell(row['description'])} — {cell(row['severity'])}]({row['url']}): {row['start']} a {row['end']}; ativo agora: {row['active_now']}.")
    for row in comparison.get('daily_pairs', []):
        lines.append(f"- Dia {row['date']}: POA Clima {row['poa_mm']:.1f} mm / Open-Meteo {row['open_meteo_mm']:.1f} mm; diferença {row['difference_mm']:+.1f} mm.")
    for row in official.get('poa_alerts', {}).get('alerts', []):
        regions = ', '.join(r['name'] for r in row['regions'])
        lines.append(f"- Defesa Civil POA — {row['label']}; regiões: {cell(regions)}; vigência {row['start']} a {row['end']}; ativo agora: {row['active_now']}. Tipos: {cell(', '.join(row['types']))}. Descrição: {cell(row['description'])}")
        if row.get('timezone_assumed'):
            lines.append('  Fonte municipal sem fuso explícito; horários interpretados em BRT.')
    for entry in official.get('poa_alerts', {}).get('excluded_alerts', []):
        alert = entry['alert']
        lines.append(f"- Municipal mantido somente no relatório ({entry['reason']}): {cell(alert['description'])}; regiões originais: {cell(', '.join(r['name'] for r in alert['regions']))}.")
    station_product = official.get('poa_stations', {})
    for station in station_product.get('stations', []):
        lines.append(f"- Estação {cell(station['name'])}: {station['distance_km']:.3f} km de SBPA; dentro do raio: {station['within_focus']}; leituras publicadas: {cell(json.dumps(station['readings'], ensure_ascii=False))}.")
    if station_product.get('stations'):
        lines.append(station_product['limitation'])
    return '\n'.join(lines) + '\n'
