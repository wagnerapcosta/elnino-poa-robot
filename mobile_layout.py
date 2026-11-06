"""Essencial: presentation-only rounding; classification uses unrounded data."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re


def integer(value, threshold=None):
    if value is None or isinstance(value, bool):
        return 'indisponível'
    try:
        exact = Decimal(str(value))
        if not exact.is_finite() or exact < 0:
            return 'indisponível'
        shown = exact.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
        # 19.99 must not look like an inclusive 20 mm trigger after rounding.
        if threshold is not None and exact < Decimal(str(threshold)) <= shown:
            return '<' + str(threshold)
        return str(shown)
    except (InvalidOperation, ValueError):
        return 'indisponível'


def rounded_measurements(text):
    return re.sub(r'(?<![\d.,])(\d+[.,]\d+)(?=\s*(?:mm(?:/h)?|km/h)\b)',
                  lambda m: integer(m[1].replace(',', '.')), text, flags=re.I)


def short_reason(text):
    text = text.removeprefix('Previsão quantitativa: ').strip()
    if text.startswith('Chuva 12h:'):
        return 'Chuva prevista atingiu o gatilho de 12h.' if 'ALERTA' in text else 'Avaliação de chuva em 12h indisponível.'
    text = re.split(r':\s*(?:24h=|72h=|\d)', text, maxsplit=1)[0]
    return rounded_measurements(text).rstrip('.') + '.'


def forecast_lines(forecast):
    alert = forecast['rain_12h']
    rain = integer(alert.get('total_mm'), threshold=20) if alert.get('status') == 'ok' else 'indisponível'
    daily_ok = bool(forecast.get('dates'))
    return [f'Chuva 12h: {rain}' + (' mm' if rain != 'indisponível' else ''),
            'Chuva dia (máx.): ' + (integer(forecast.get('p24_max_mm')) + ' mm' if daily_ok else 'indisponível'),
            'Chuva 3 dias (máx.): ' + (integer(forecast.get('p72_max_mm')) + ' mm' if daily_ok else 'indisponível'),
            'Rajada máx.: ' + (integer(forecast.get('gust_max_kmh')) + ' km/h' if daily_ok else 'indisponível')]


def forecast_body(forecast, risk=None, reason=None, action=None):
    lines = ['Risco: ' + risk.upper(), ''] if risk else []
    lines += forecast_lines(forecast)
    if reason:
        lines += ['', 'Motivo: ' + short_reason(reason)]
    if action:
        lines.append('Ação: ' + rounded_measurements(action))
    alert = forecast['rain_12h']
    if alert.get('start') and alert.get('end'):
        start = datetime.fromisoformat(alert['start']).strftime('%d/%m %H:%M')
        end = datetime.fromisoformat(alert['end']).strftime('%d/%m %H:%M')
        lines += ['', f'Janela 12h: {start} → {end} BRT']
    lines.append('Fonte: Open-Meteo · SBPA')
    return '\n'.join(lines)


MUNICIPAL_TITLES = {
    'attention_notice': 'Aviso Amarelo',
    'high_risk': 'Alerta Laranja',
    'very_high_risk': 'Alerta Vermelho',
    'extreme_risk': 'Alerta Roxo (risco extremo)',
}
