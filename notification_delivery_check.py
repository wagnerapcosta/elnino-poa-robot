"""Read-only diagnostic of the four explicitly requested simulated messages."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import requests


def main():
    topic = os.environ.get('NTFY_TOPIC')
    if not topic:
        raise RuntimeError('Tópico não disponível para diagnóstico')
    since = int(datetime(2026, 11, 5, 14, 56, 5, tzinfo=timezone.utc).timestamp())
    expected = ['TESTE - DADOS SIMULADOS - ' + label for label in (
        'TATICO AMARELO', 'TATICO LARANJA', 'MUNICIPAL PARTE 1/2', 'MUNICIPAL PARTE 2/2')]
    try:
        response = requests.get(f'https://ntfy.sh/{topic}/json',
                                params=dict(poll=1, since=since), timeout=30)
        response.raise_for_status()
        messages = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    except (requests.RequestException, ValueError):
        raise RuntimeError('Não foi possível consultar o histórico do serviço; tópico preservado') from None
    records = []
    for item in messages:
        if item.get('event') != 'message' or item.get('title') not in expected:
            continue
        if not since <= item.get('time', 0) <= since + 120:
            continue
        body = item.get('message', '')
        records.append(dict(title=item['title'], id=item['id'], time=item['time'],
                            priority=item.get('priority', 3), bytes=len(body.encode('utf-8')),
                            test_label_present='TESTE — DADOS SIMULADOS' in body,
                            fictional_regions=[i for i in range(1, 18) if f'REGIÃO FICTÍCIA {i:02}' in body]))
    report = dict(read_only=True, sent_count=0, records=records,
                  missing_titles=[title for title in expected if title not in {r['title'] for r in records}],
                  unique_ids=len({r['id'] for r in records}))
    Path('reports').mkdir(exist_ok=True)
    Path('reports/notification_delivery_check.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
