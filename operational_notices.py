"""Additional operational notices, independent from the 20 mm/12h trigger."""
from datetime import datetime
from rain_alert import TZ
from mobile_layout import MUNICIPAL_TITLES, rounded_measurements


def primary_failure_notice(collection, forecast, now):
    alert = forecast.get('rain_12h', {})
    if collection.get('status') == 'ok' and forecast.get('data_status') == 'ok':
        return None
    if collection.get('status') != 'ok' or alert.get('status') != 'ok':
        detail = 'Chuva 12h: indisponível. Não foi possível avaliar o gatilho.'
    else:
        detail = 'Dados diários indisponíveis; a avaliação de 12h permanece disponível.'
    body = (detail + '\nDADOS INDISPONÍVEIS NÃO SIGNIFICAM AUSÊNCIA DE RISCO.\n'
            f"Verificação: {now.astimezone(TZ).strftime('%d/%m %H:%M')} BRT\nFonte: Open-Meteo")
    return dict(title='SBPA | Previsao | FALHA na coleta', body=body, level='laranja')


def _utf8_excerpt(text, max_bytes):
    suffix = '… [trecho; consulte a íntegra no portal]'
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes - len(suffix.encode('utf-8'))].decode('utf-8', errors='ignore') + suffix


def civil_defense_notice(product, now):
    """Render one bounded page and identify only the regions present in its body."""
    alerts = product.get('alerts', [])
    if product.get('status') not in ('ok', 'partial') or not alerts:
        return None
    ranks = {'attention_notice': 1, 'high_risk': 2, 'very_high_risk': 3, 'extreme_risk': 4}
    included, included_alerts = [], []
    lines = []
    if product.get('airport_focus') and not product['airport_focus'].get('geometry_verified'):
        lines.append('ABRANGÊNCIA A CONFIRMAR: consultar mapa oficial.')
    if product.get('status') == 'partial':
        lines.append('CONSULTA PARCIAL: cobertura incompleta não significa ausência de risco.')
    footer = ['\nAviso regional; não confirma ocorrência na pista.', 'Fonte: Defesa Civil POA · POA Clima']
    continuation = '\nContinua em outra notificação.'
    # Reserve the footer and continuation note, measuring bytes rather than characters.
    budget = 3900 - len(('\n'.join([continuation] + footer) + '\n').encode('utf-8'))
    for a in sorted(alerts, key=lambda a: ranks[a['criticality']], reverse=True):
        start = datetime.fromisoformat(a['start']).astimezone(TZ).strftime('%d/%m %H:%M')
        end = datetime.fromisoformat(a['end']).astimezone(TZ).strftime('%d/%m %H:%M')
        conditions = rounded_measurements(', '.join(a['types'])) or a['label']
        detail = '\n' + _utf8_excerpt(rounded_measurements(a['description']), 280)
        detail += f"\nValidade: {start} → {end} BRT"
        if not a['active_now']:
            detail += ' (início futuro).'
        if a.get('timezone_assumed'):
            detail += '\nFonte sem fuso explícito: horários interpretados em BRT.'
        page_regions = []
        text = None
        for region in a['regions']:
            names = ', '.join(r['name'] for r in page_regions + [region])
            heading = _utf8_excerpt(conditions, 400)
            if len(alerts) > 1:
                heading = a['label'] + ' · ' + heading
            candidate = heading + detail + '\nÁrea: ' + names
            if len('\n'.join(lines + [candidate]).encode('utf-8')) > budget:
                break
            page_regions.append(region)
            text = candidate
        if page_regions:
            lines.append(text)
            included.extend(r['order'] for r in page_regions)
            included_alerts.append(a)
        if len(page_regions) != len(a['regions']):
            break
    if not included:
        # Normalized source records fit individually; never send/record an empty page.
        raise ValueError('Uma região municipal excede o limite da notificação')
    if len(included) < sum(len(a['regions']) for a in alerts):
        lines.append(continuation)
    lines += footer
    maximum = max(included_alerts, key=lambda a: ranks[a['criticality']])
    level = 'vermelho' if ranks[maximum['criticality']] >= 3 else ('laranja' if ranks[maximum['criticality']] == 2 else 'amarelo')
    return dict(title='SBPA | Defesa Civil | ' + MUNICIPAL_TITLES[maximum['criticality']],
                body='\n'.join(lines), level=level, region_orders=included)


def send_additional_notices(notices, notify):
    """Attempt each channel even when another delivery fails; never log topic URLs."""
    outcomes = []
    for notice in notices:
        if notice is None:
            continue
        try:
            accepted = notify(notice['title'], notice['body'], notice['level'])
            outcomes.append(dict(title=notice['title'], accepted=accepted is True,
                                 error=None if accepted is True else 'Serviço não confirmou o envio'))
        except Exception as exc:
            outcomes.append(dict(title=notice['title'], accepted=False,
                                 error=type(exc).__name__ + ': envio não confirmado'))
    return outcomes
