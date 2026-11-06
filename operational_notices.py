"""Additional operational notices, independent from the 20 mm/12h trigger."""
from datetime import datetime
from rain_alert import TZ


def primary_failure_notice(collection, forecast, now):
    alert = forecast.get('rain_12h', {})
    if collection.get('status') == 'ok' and forecast.get('data_status') == 'ok':
        return None
    if collection.get('status') != 'ok':
        detail = 'A consulta ao Open-Meteo falhou; a previsão principal não está disponível.'
    elif alert.get('status') != 'ok':
        detail = 'A série horária está ausente, inválida ou sem cobertura. Não foi possível avaliar o gatilho de 20 mm em 12 horas.'
    else:
        detail = 'Os dados diários da previsão principal estão incompletos ou inválidos. A avaliação de 12 horas permanece disponível separadamente.'
    body = ('FALHA NA COLETA DA PREVISÃO PRINCIPAL — Open-Meteo.\n'
            + detail + '\nDADOS INDISPONÍVEIS NÃO SIGNIFICAM AUSÊNCIA DE RISCO.\n'
            'Não interprete esta falha como previsão de tempo seguro ou ausência de chuva. '
            'Consulte CPTEC/INPE, INMET e POA Clima antes de concluir sobre o risco.\n'
            f"Verificação: {now.astimezone(TZ).strftime('%d/%m/%Y %H:%M')} BRT.\n"
            'Fontes: https://www.cptec.inpe.br/ · https://mapas.inmet.gov.br/ · https://prefeitura.poa.br/poaclima/')
    return dict(title='Radar POA - FALHA na previsao principal', body=body, level='laranja')


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
    lines = ['AVISOS/ALERTAS DA DEFESA CIVIL MUNICIPAL DE PORTO ALEGRE.',
             f"Consulta: {now.astimezone(TZ).strftime('%d/%m/%Y %H:%M')} BRT.",
             'Origem: POA Clima. A abrangência é por região; conferir a aplicabilidade a SBPA.']
    if product.get('airport_focus'):
        lines[0] = 'DEFESA CIVIL POA — FOCO SBPA E ENTORNO DE 4 KM.'
        lines[2] = 'Origem: POA Clima. Região sobreposta ao entorno; não confirma ocorrência na pista.'
        if not product['airport_focus'].get('geometry_verified'):
            lines[0] = 'DEFESA CIVIL POA — ABRANGÊNCIA A CONFIRMAR.'
            lines[2] = 'Geografia não confirmada para todos os registros; consultar o mapa oficial.'
    if product.get('status') == 'partial':
        lines.append('CONSULTA PARCIAL: alguns registros/regiões não puderam ser avaliados.')
    footer = ['\nEstes avisos não equivalem ao gatilho quantitativo de 20 mm/12h.',
              'Fonte oficial e orientações completas: https://prefeitura.poa.br/poaclima/']
    continuation = '\nHá conteúdo adicional em outra notificação e no portal/relatório.'
    # Reserve the footer and continuation note, measuring bytes rather than characters.
    budget = 3900 - len(('\n'.join([continuation] + footer) + '\n').encode('utf-8'))
    for a in sorted(alerts, key=lambda a: ranks[a['criticality']], reverse=True):
        start = datetime.fromisoformat(a['start']).astimezone(TZ).strftime('%d/%m %H:%M')
        end = datetime.fromisoformat(a['end']).astimezone(TZ).strftime('%d/%m %H:%M')
        detail = f"\nVigência: {start} a {end} BRT"
        detail += ' (vigente agora).' if a['active_now'] else ' (início futuro).'
        if a['types']:
            detail += '\nTipo: ' + _utf8_excerpt(', '.join(a['types']), 400) + '.'
        detail += '\nDescrição oficial: ' + _utf8_excerpt(a['description'], 1000)
        if a.get('timezone_assumed'):
            detail += '\nFonte sem fuso explícito: horários interpretados em BRT.'
        page_regions = []
        text = None
        for region in a['regions']:
            names = ', '.join(r['name'] for r in page_regions + [region])
            candidate = f"\n{a['label']} — regiões: {names}." + detail
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
    return dict(title='Radar POA - DEFESA CIVIL POA - ' + maximum['title_label'],
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
