"""Public products linked by CPTEC, INMET and the official POA Clima portal.

Cross-checks are indicative: different locations, temporal resolutions and models.
No averaging, majority voting or cancellation of the Open-Meteo alert.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import isfinite, radians, sin, cos, asin, sqrt
import unicodedata
import requests
from rain_alert import TZ

CPTEC_URL = 'https://s1.cptec.inpe.br/grafico/Modelos/Multimodel/pag_web/horario/1276.json'
INMET_URL = 'https://apiprevmet3.inmet.gov.br/previsao/4314902'
INMET_WARNINGS_URL = 'https://apiprevmet3.inmet.gov.br/avisos/ativos'
POA_URL = 'https://api.helpertecnologia.com.br/defesa-civil/bff/climate/previsions/poadc'
IBGE = '4314902'


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
    a, b = radians(lat + 29.9939), radians(lon + 51.1711)
    x = sin(a / 2)**2 + cos(radians(lat)) * cos(radians(-29.9939)) * sin(b / 2)**2
    return round(6371 * 2 * asin(sqrt(x)), 1)


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


PRODUCTS = {
    'cptec': ('CPTEC/INPE Multimodelo', CPTEC_URL, parse_cptec),
    'inmet_forecast': ('INMET previsão Porto Alegre', INMET_URL, parse_inmet_forecast),
    'inmet_warnings': ('INMET avisos', INMET_WARNINGS_URL, parse_inmet_warnings),
    'poa': ('POA Clima / Prefeitura', POA_URL, parse_poa),
}


def collect_official_data(now=None):
    now = now or datetime.now(TZ)
    def fetch(key):
        name, url, parser = PRODUCTS[key]
        result = dict(source=name, url=url, fetched_at=now.isoformat(), status='unavailable', error=None)
        try:
            response = requests.get(url, timeout=25, headers={'User-Agent': 'POA-Radar/1.4'})
            response.raise_for_status()
            result.update(parser(response.json(), now))
            result['status'] = 'partial' if result.get('skipped_records') else 'ok'
        except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, AttributeError, OverflowError) as exc:
            result['error'] = str(exc)
        return key, result
    with ThreadPoolExecutor(max_workers=4) as pool:
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
    attention = c_ok and c_signal is True and (not p_ok or same_window and primary.get('triggered') is False)
    daily_pairs = []
    daily = (open_meteo_json or {}).get('daily') or {}
    units = (open_meteo_json or {}).get('daily_units') or {}
    dates, amounts = daily.get('time') or [], daily.get('precipitation_sum') or []
    if units.get('precipitation_sum') == 'mm' and len(dates) == len(amounts):
        om_daily = dict(zip(dates, amounts))
        if official.get('poa', {}).get('status') == 'ok':
            for row in official['poa']['daily']:
                try:
                    om = number(om_daily.get(row['date']))
                    daily_pairs.append(dict(date=row['date'], open_meteo_mm=float(om), poa_mm=row['rain_mm'],
                                            difference_mm=float(number(row['rain_mm']) - om)))
                except ValueError:
                    pass
    return dict(state=state, cptec_attention=bool(attention), daily_pairs=daily_pairs,
                limitation='Checagem cruzada de previsões, sem validação estatística; modelos podem compartilhar insumos. INMET e POA diário não confirmam o total de 12h.')


def official_summary(official, comparison):
    lines = ['Checagem oficial: ' + comparison['state'] + '.']
    if comparison.get('cptec_attention'):
        lines.append('ATENÇÃO COMPLEMENTAR: CPTEC sugere ultrapassagem nas duas hipóteses horárias; conferir divergência ou indisponibilidade da fonte principal.')
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
    if comparison.get('daily_pairs'):
        r = comparison['daily_pairs'][0]
        lines.append(f"Dia {r['date']}: POA Clima {r['poa_mm']:.1f} mm; Open-Meteo {r['open_meteo_mm']:.1f} mm. Totais diários, não 12h.")
    else:
        lines.append('POA Clima: comparação quantitativa diária indisponível.')
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
    return '\n'.join(lines) + '\n'
