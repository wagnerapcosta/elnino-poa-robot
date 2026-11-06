"""Explicit mobile regression test; fictitious inputs and temporary event memory."""
import argparse
import hashlib
import json
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

from notification_state import NotificationState
from operational_notices import civil_defense_notice
from rain_alert import TZ
from robot import notify_ntfy


def production_hashes():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(Path('data').rglob('*')) if p.is_file()}


def municipal_fixture(now):
    alerts = []
    for group in range(4):
        orders = range(group * 4 + 1, (group + 1) * 4 + 1 if group < 3 else 18)
        alerts.append(dict(
            criticality='high_risk', label='RISCO ALTO SIMULADO', title_label='RISCO ALTO',
            start=now.isoformat(), end=(now + timedelta(hours=2)).isoformat(),
            active_now=True, timezone_assumed=False,
            types=[f'Cenário fictício {group + 1}: ' + 'amostra ' * 12 for _ in range(4)],
            description=('Texto fictício para verificar a divisão de mensagens longas. ' * 25),
            regions=[dict(order=i, name=f'REGIÃO FICTÍCIA {i:02} ' + 'x' * 65) for i in orders]))
    return dict(status='ok', alerts=alerts)


def run_test(notify, dry_run=False):
    now = datetime.now(TZ)
    before = production_hashes()
    report = dict(test=True, dry_run=dry_run, started_at=now.isoformat(),
                  accepted=[], phases=[], simulated_rejections=[], complete=False)
    prefix = 'TESTE — DADOS SIMULADOS. Cenário fictício; sem alerta real ou ação necessária.\n'

    def deliver(label, body, level):
        title = 'TESTE - DADOS SIMULADOS - ' + label
        body = prefix + body
        assert len(body.encode('utf-8')) <= 4096, 'Mensagem de teste excede limite'
        # Diagnostic precaution after a partial burst delivery; not a delivery guarantee.
        if report['accepted'] and not dry_run:
            time.sleep(10)
        accepted = notify(title, body, level) is True
        report['accepted'].append(dict(title=title, accepted=accepted, bytes=len(body.encode('utf-8'))))
        print(f'{title}: aceitação HTTP={accepted}', flush=True)
        if not accepted:
            raise RuntimeError('Envio real não confirmado. Não repetir automaticamente mensagens já aceitas.')
        return True

    try:
        with tempfile.TemporaryDirectory(prefix='radar-patch-test-') as folder:
            general_path = Path(folder) / 'general.json'
            municipal_path = Path(folder) / 'municipal.json'
            forecast = dict(data_status='ok', general_level='verde', level='verde',
                            p24_max_mm=0, p72_max_mm=0, gust_max_kmh=0,
                            rain_12h=dict(status='ok', triggered=False, total_mm=0))
            def general_send(title, body, level):
                return deliver('TATICO ' + level.upper(), body, level)

            for level, expected in [('verde', None), ('amarelo', 'sent'),
                                    ('amarelo', 'suppressed'), ('laranja', 'sent'),
                                    ('laranja', 'suppressed')]:
                notice = dict(title='Resumo fictício', level=level, rain_only=False,
                              body=f'Nível tático simulado: {level.upper()}.\n'
                                   'Previsão quantitativa mantida igual. A mudança de nível deve notificar; '
                                   'a repetição idêntica deve ser bloqueada.')
                outcomes = NotificationState(general_path).general(forecast, notice, now, general_send)
                status = outcomes[0]['status'] if outcomes else None
                assert status == expected, (level, status, expected)
                report['phases'].append(dict(kind='tactical', level=level, status=status))

            product = municipal_fixture(now)
            # Prove this fixture needs exactly two pages before any municipal delivery.
            first = civil_defense_notice(product, now)
            remaining = [dict(a, regions=[r for r in a['regions'] if r['order'] not in first['region_orders']])
                         for a in product['alerts']]
            remaining = [a for a in remaining if a['regions']]
            second = civil_defense_notice(dict(product, alerts=remaining), now)
            assert set(first['region_orders']) | set(second['region_orders']) == set(range(1, 18))
            assert set(first['region_orders']).isdisjoint(second['region_orders'])
            municipal_attempts, municipal_accepted = 0, 0

            def municipal_send(title, body, level):
                nonlocal municipal_attempts, municipal_accepted
                municipal_attempts += 1
                if municipal_attempts == 2:
                    # No HTTP request here: exercise a rejected page without noisy real failure.
                    report['simulated_rejections'].append('municipal page 2; no HTTP attempted')
                    print('TESTE: segunda página recusada SIMULADAMENTE, sem chamada HTTP.', flush=True)
                    return False
                body = body.replace('AVISOS/ALERTAS DA DEFESA CIVIL MUNICIPAL DE PORTO ALEGRE.',
                                    'FORMATO MUNICIPAL SIMULADO — NÃO EMITIDO PELA DEFESA CIVIL.')
                body = body.replace('Origem: POA Clima.', 'Origem: dados fictícios.').replace(
                    'Descrição oficial:', 'Descrição fictícia:').replace('Vigência:', 'Vigência simulada:')
                deliver(f'MUNICIPAL PARTE {municipal_accepted + 1}/2', body, level)
                municipal_accepted += 1
                return True

            first_result = NotificationState(municipal_path).municipal(product, now, municipal_send)
            assert [r['status'] for r in first_result] == ['sent', 'failed']
            state = NotificationState(municipal_path)
            accepted_orders = {int(key.split(':')[1]) for key in state.data['events']}
            assert accepted_orders == set(first['region_orders'])
            retry = state.municipal(product, now, municipal_send)
            assert len(retry) == 1 and retry[0]['status'] == 'sent'
            assert set(retry[0]['region_orders']) == set(second['region_orders'])
            assert len(NotificationState(municipal_path).data['events']) == 17
            assert NotificationState(municipal_path).municipal(product, now, municipal_send) == []
            report['phases'].append(dict(kind='municipal', initial=first_result, retry=retry,
                                         repeat=[], recorded_regions=17, accepted_pages=municipal_accepted))
            assert municipal_accepted == 2 and len(report['accepted']) == 4
            report['complete'] = True
    finally:
        after = production_hashes()
        report['production_data_untouched'] = before == after
        report['production_hashes_before'] = before
        report['production_hashes_after'] = after
        Path('reports').mkdir(exist_ok=True)
        Path('reports/notification_patch_test.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        assert before == after, 'Dados de produção alterados indevidamente'
    print('TESTE CONCLUÍDO: 2 avisos táticos e 2 páginas municipais; repetições bloqueadas; '
          'somente a página recusada foi retomada. Confirmação no celular pendente.', flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    run_test((lambda *_: True) if args.dry_run else notify_ntfy, args.dry_run)
