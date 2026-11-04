"""Explicit notification test; no weather requests or operational history writes."""
from datetime import datetime, timedelta
from rain_alert import TZ, rain_alert
from robot import notify_ntfy


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


def main():
    title, message = build_test()
    if notify_ntfy(title, message, 'laranja') is not True:
        raise RuntimeError('Teste não enviado: tópico de notificação não configurado')
    print('TESTE: serviço ntfy aceitou o envio HTTP. Recebimento no celular depende de confirmação do usuário.')


if __name__ == '__main__':
    main()
