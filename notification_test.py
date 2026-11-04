"""Explicit notification test; no weather requests or operational history writes."""
from datetime import datetime, timedelta
from rain_alert import TZ, rain_alert
from robot import notify_ntfy
from operational_notices import primary_failure_notice, civil_defense_notice, send_additional_notices
import argparse


def build_test(now=None):
    now = now or datetime.now(TZ)
    start = now.replace(minute=0, second=0, microsecond=0)
    payload = {
        'latitude': -29.9939, 'longitude': -51.1711,
        'timezone': 'America/Sao_Paulo',
        'hourly_units': {'precipitation': 'mm'},
        'hourly': {
            'time': [(start + timedelta(hours=i)).isoformat() for i in range(1, 13)],
            'precipitation': [2] * 10 + [0] * 2,
        },
    }
    alert = rain_alert(payload, now)
    if alert['status'] != 'ok' or alert['total_mm'] != 20 or alert['triggered'] is not True:
        raise RuntimeError('A simulação de 20 mm/12h não validou o gatilho inclusivo')
    title = 'TESTE - DADOS SIMULADOS - Radar POA 20 mm/12h'
    message = (
        'TESTE DE NOTIFICAÇÃO — DADOS SIMULADOS.\n'
        'Simulação: 20,0 mm acumulados em 12 horas. O limite inclusivo de 20 mm disparou.\n'
        f"Janela simulada: {start.strftime('%d/%m %H:%M')} a {(start + timedelta(hours=12)).strftime('%d/%m %H:%M')} BRT.\n"
        'Esta mensagem NÃO representa previsão real nem alerta meteorológico vigente. '
        'Nenhuma ação operacional é necessária por causa deste teste.\n'
        'Confirme no chat se a notificação chegou ao celular.'
    )
    return title, message


def build_operational_tests(now=None):
    now = now or datetime.now(TZ)
    failure = primary_failure_notice({'status': 'error'},
                                     {'data_status': 'unavailable', 'rain_12h': {'status': 'unavailable'}}, now)
    civil = civil_defense_notice({'status': 'ok', 'alerts': [{
        'criticality': 'high_risk', 'label': 'Alerta de risco alto', 'title_label': 'RISCO ALTO',
        'start': now.isoformat(), 'end': (now + timedelta(hours=2)).isoformat(),
        'active_now': True, 'timezone_assumed': False,
        'types': ['Chuva intensa — cenário fictício de teste'],
        'description': 'Texto fictício usado exclusivamente para testar a entrega da notificação no celular.',
        'regions': [{'order': 1, 'name': 'REGIÃO FICTÍCIA — TESTE'}],
    }]}, now)
    failure['title'] = 'TESTE - DADOS SIMULADOS - FALHA DA PREVISAO PRINCIPAL'
    failure['body'] = ('TESTE — DADOS SIMULADOS.\n'
                       'Simulação de falha da previsão principal. Não é uma indisponibilidade real detectada.\n'
                       'Nenhuma ação operacional é necessária por causa deste teste.\n\n'
                       + failure['body'] + '\n\nFIM DO TESTE. Confirme o recebimento no chat.')
    civil['title'] = 'TESTE - DADOS SIMULADOS - ALERTA DEFESA CIVIL POA'
    civil['body'] = civil['body'].replace('AVISOS/ALERTAS DA DEFESA CIVIL MUNICIPAL DE PORTO ALEGRE.',
                                        'SIMULAÇÃO DO FORMATO DE AVISO DA DEFESA CIVIL POA.')
    civil['body'] = civil['body'].replace('Origem: POA Clima.', 'Cenário fictício; nenhum alerta real foi consultado ou emitido pela Defesa Civil para este teste.')
    civil['body'] = civil['body'].replace('Descrição oficial:', 'Descrição simulada:').replace('Vigência:', 'Vigência simulada:')
    civil['body'] = ('TESTE — DADOS SIMULADOS.\n'
                     'Simulação de alerta municipal de risco alto, em região fictícia. NÃO é um alerta real da Defesa Civil.\n'
                     'Nenhuma ação operacional é necessária por causa deste teste.\n\n'
                     + civil['body'] + '\n\nFIM DO TESTE. Confirme o recebimento no chat.')
    return [failure, civil]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--operational', action='store_true', help='Enviar dois testes: falha principal e Defesa Civil POA')
    args = parser.parse_args()
    if args.operational:
        outcomes = send_additional_notices(build_operational_tests(), notify_ntfy)
        for row in outcomes:
            print(f"TESTE: {row['title']} — aceitação HTTP pelo ntfy: {row['accepted']}")
        if len(outcomes) != 2 or any(not row['accepted'] for row in outcomes):
            raise RuntimeError('Um ou mais testes não tiveram envio confirmado; não repetir os que já foram aceitos')
        print('DOIS TESTES aceitos pelo serviço. Recebimento no celular depende da confirmação do usuário.')
        return
    title, message = build_test()
    if notify_ntfy(title, message, 'laranja') is not True:
        raise RuntimeError('Teste não enviado: tópico de notificação não configurado')
    print('TESTE: serviço ntfy aceitou o envio HTTP. Recebimento no celular depende de confirmação do usuário.')


if __name__ == '__main__':
    main()
