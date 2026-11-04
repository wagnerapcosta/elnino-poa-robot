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


def civil_defense_notice(product, now):
    alerts = product.get('alerts', [])
    if product.get('status') not in ('ok', 'partial') or not alerts:
        return None
    ranks = {'attention_notice': 1, 'high_risk': 2, 'very_high_risk': 3, 'extreme_risk': 4}
    maximum = max(alerts, key=lambda a: ranks[a['criticality']])
    lines = ['AVISOS/ALERTAS DA DEFESA CIVIL MUNICIPAL DE PORTO ALEGRE.',
             f"Consulta: {now.astimezone(TZ).strftime('%d/%m/%Y %H:%M')} BRT.",
             'Origem: POA Clima. A abrangência é por região; conferir a aplicabilidade a SBPA.']
    if product.get('status') == 'partial':
        lines.append('CONSULTA PARCIAL: alguns registros/regiões não puderam ser avaliados.')
    for a in sorted(alerts, key=lambda a: ranks[a['criticality']], reverse=True):
        start = datetime.fromisoformat(a['start']).astimezone(TZ).strftime('%d/%m %H:%M')
        end = datetime.fromisoformat(a['end']).astimezone(TZ).strftime('%d/%m %H:%M')
        region = ', '.join(r['name'] for r in a['regions'])
        text = f"\n{a['label']} — regiões: {region}.\nVigência: {start} a {end} BRT"
        text += ' (vigente agora).' if a['active_now'] else ' (início futuro).'
        if a['types']:
            text += '\nTipo: ' + ', '.join(a['types']) + '.'
        excerpt = a['description'][:500]
        if len(a['description']) > 500:
            excerpt += '… [trecho; consulte a íntegra no portal]'
        text += '\nDescrição oficial: ' + excerpt
        if a.get('timezone_assumed'):
            text += '\nFonte sem fuso explícito: horários interpretados em BRT.'
        # ntfy has a finite payload. Reserve room for source and truncation note.
        if len(('\n'.join(lines) + text).encode('utf-8')) > 3300:
            lines.append('\nHá conteúdo adicional no portal/relatório; consulte a fonte para os detalhes completos.')
            break
        lines.append(text)
    lines += ['\nEstes avisos não equivalem ao gatilho quantitativo de 20 mm/12h.',
              'Fonte oficial e orientações completas: https://prefeitura.poa.br/poaclima/']
    level = 'vermelho' if ranks[maximum['criticality']] >= 3 else ('laranja' if ranks[maximum['criticality']] == 2 else 'amarelo')
    return dict(title='Radar POA - DEFESA CIVIL POA - ' + maximum['title_label'],
                body='\n'.join(lines), level=level)


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
