"""Controlled resend of only the two simulated messages reported missing."""
import json
import os
import time
from pathlib import Path
import requests
from notification_patch_test import production_hashes


def main():
    topic = os.environ.get('NTFY_TOPIC')
    if not topic:
        raise RuntimeError('Tópico indisponível')
    url = f'https://ntfy.sh/{topic}'
    before = production_hashes()
    report = dict(test=True, sent=[], production_data_untouched=False)
    source_ids = [('Di9BFhRDAIme', 'TATICO AMARELO', 3),
                  ('YBP1XFahkhNp', 'MUNICIPAL PARTE 1/2', 4)]
    try:
        try:
            cached = requests.get(url + '/json', params=dict(poll=1, since='30m'), timeout=30)
            cached.raise_for_status()
            records = [json.loads(line) for line in cached.text.splitlines() if line.strip()]
        except (requests.RequestException, ValueError):
            raise RuntimeError('Consulta ao histórico falhou; nenhum reenvio realizado') from None
        planned = []
        for source_id, label, priority in source_ids:
            matches = [r for r in records if r.get('id') == source_id]
            assert len(matches) == 1, 'Mensagem original não encontrada; abortando reenvio'
            original = matches[0]
            assert original['title'] == 'TESTE - DADOS SIMULADOS - ' + label
            body = 'TESTE — DADOS SIMULADOS. REENVIO CONTROLADO da mensagem não recebida.\n' + original['message']
            assert len(body.encode('utf-8')) <= 4096
            planned.append((source_id, label, priority, body))
        for index, (source_id, label, priority, body) in enumerate(planned):
            if index:
                time.sleep(10)
            title = 'TESTE - DADOS SIMULADOS - REENVIO ' + label
            try:
                response = requests.post(url, data=body.encode('utf-8'),
                                         headers={'Title': title, 'Priority': str(priority), 'Tags': 'test_tube'},
                                         timeout=30)
                response.raise_for_status()
                receipt = response.json()
                assert receipt.get('id') and receipt.get('message') == body
            except (requests.RequestException, ValueError, AssertionError):
                raise RuntimeError('Reenvio não confirmado; não repetir automaticamente os já aceitos') from None
            row = dict(title=title, source_id=source_id, id=receipt['id'], time=receipt['time'],
                       accepted=True, bytes=len(body.encode('utf-8')), priority=priority)
            report['sent'].append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        report['production_data_untouched'] = before == production_hashes()
        Path('reports').mkdir(exist_ok=True)
        Path('reports/notification_missing_test.json').write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        assert report['production_data_untouched']


if __name__ == '__main__':
    main()
