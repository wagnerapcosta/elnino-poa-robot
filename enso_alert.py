"""Dated ENSO updates from NOAA CPC for the climate notification channel."""

import argparse
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from notification_state import NotificationState
from rain_alert import TZ
from robot import notify_ntfy


NOAA_BULLETIN = 'https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso_advisory/ensodisc.shtml'
NOAA_ARCHIVE = 'https://www.cpc.ncep.noaa.gov/products/analysis_monitoring/enso/roni/archives/'
CPTEC_BRAZIL = 'https://clima2.cptec.inpe.br/boletins/pt'
MONTHS = 'January February March April May June July August September October November December'.split()
SEASONS = 'JFM FMA MAM AMJ MJJ JJA JAS ASO SON OND NDJ DJF'.split()
STATUS_LABELS = {
    'el nino advisory': 'El Niño ativo',
    'el nino watch': 'Vigilância para El Niño',
    'la nina advisory': 'La Niña ativa',
    'la nina watch': 'Vigilância para La Niña',
    'final advisory': 'Último aviso da fase anterior',
    'final el nino advisory': 'Último aviso de El Niño',
    'final la nina advisory': 'Último aviso de La Niña',
    'not active': 'Sem aviso ENOS ativo',
}


def parse_bulletin(raw, today):
    text = ' '.join(BeautifulSoup(raw, 'lxml').get_text(' ', strip=True).split())
    header = re.search(
        r'CLIMATE PREDICTION CENTER\s*/\s*NCEP\s*/\s*NWS\s+(\d{1,2}) ([A-Za-z]+) (\d{4})'
        r'\s+ENSO Alert System Status\s*:\s*(.*?)\s+Synopsis\s*:',
        text, flags=re.IGNORECASE,
    )
    if not header:
        raise ValueError('Data ou estado oficial ausente no boletim CPC')
    day, month, year, status = header.groups()
    issued = date(int(year), MONTHS.index(month.title()) + 1, int(day))
    if not 0 <= (today - issued).days <= 45:
        raise ValueError('Data do boletim CPC fora da janela de atualização')
    status = unicodedata.normalize('NFKD', status.casefold()).encode('ascii', 'ignore').decode()
    phases = [part.strip() for part in status.split('/')]
    if not all(phase in STATUS_LABELS for phase in phases):
        raise ValueError('Estado oficial CPC não reconhecido')
    return {'issued': issued.isoformat(), 'status': ' / '.join(STATUS_LABELS[phase] for phase in phases)}


def parse_outlook(raw, issued):
    soup = BeautifulSoup(raw, 'lxml', from_encoding='utf-8')
    expected_edition = f'Issued {MONTHS[issued.month - 1]} {issued.year}'
    if not any(h.get_text(' ', strip=True) == expected_edition for h in soup.find_all('h2')):
        raise ValueError('Probabilidades de edição diferente do boletim')
    table = soup.find('table', id='probabilities-table')
    if table is None:
        raise ValueError('Tabela de probabilidades ausente')
    rows = [[cell.get_text(' ', strip=True) for cell in row.find_all(['th', 'td'], recursive=False)]
            for row in table.find_all('tr')]
    if not rows or len(rows[0]) != 10 or rows[0][-2:] != ['1.5°C ≤ Index < 2.0°C', 'Index ≥ 2.0°C']:
        raise ValueError('Categorias de intensidade do CPC não reconhecidas')
    # The selected three-month season begins in the month following issuance.
    season = SEASONS[issued.month % 12]
    season_year = issued.year + (issued.month == 12)
    row = next((cells for cells in rows[1:] if cells and cells[0].split()[:1] == [season]), None)
    if row is None or len(row) != 10 or any(not value.isdecimal() for value in row[1:]):
        raise ValueError('Trimestre de interesse ausente ou incompleto')
    probabilities = list(map(int, row[1:]))
    strong = sum(probabilities[-2:])
    if any(value > 100 for value in probabilities) or not 98 <= sum(probabilities) <= 102 or strong > 100:
        raise ValueError('Probabilidades do CPC fora dos limites esperados')
    return {'season': season, 'season_start_year': season_year, 'strong_pct': strong}


def fetch(url):
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.content


def collect(now):
    bulletin = parse_bulletin(fetch(NOAA_BULLETIN), now.date())
    issued = date.fromisoformat(bulletin['issued'])
    outlook_url = f'{NOAA_ARCHIVE}?month={issued.month:02}&type=strengths&year={issued.year}'
    bulletin['outlook_url'] = outlook_url
    try:
        bulletin['outlook'] = parse_outlook(fetch(outlook_url), issued)
    except (requests.RequestException, ValueError):
        bulletin['outlook'] = None
    return bulletin


def notice(bulletin):
    issued = date.fromisoformat(bulletin['issued'])
    lines = [bulletin['status'], f'Boletim NOAA/CPC de {issued:%d/%m/%Y}']
    outlook = bulletin.get('outlook')
    if outlook is not None:
        first = SEASONS.index(outlook['season'])
        months = 'jan fev mar abr mai jun jul ago set out nov dez'.split()
        end_year = outlook['season_start_year'] + (first >= 10)
        period = f"{months[first]}/{outlook['season_start_year']} a {months[(first + 2) % 12]}/{end_year}"
        lines.append(f"El Niño forte ou muito forte em {period} · ≈{outlook['strong_pct']}% (RONI)")
    lines.extend(['Contexto climático sazonal. Consulte o alerta de chuva para a previsão local de 12 h.',
                  f'Boletins para o Brasil · {CPTEC_BRAZIL}'])
    return {'title': 'SBPA | ENOS | Boletim climático', 'body': '\n'.join(lines), 'level': 'verde'}


def publish(bulletin, state, now, notify=notify_ntfy):
    signature = {key: bulletin[key] for key in ('issued', 'status')}
    return state.send('enso', signature, notice(bulletin), now,
                      lambda title, body, level: notify(title, body, level, source_url=NOAA_BULLETIN),
                      relevance=lambda old, new: new['issued'] >= old['issued'] and new != old)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', action='store_true')
    args = parser.parse_args()
    now = datetime.now(TZ)
    try:
        bulletin = collect(now)
    except (requests.RequestException, ValueError) as exc:
        raise SystemExit(f'Boletim ENOS indisponível: {exc}') from None
    outcome = {'status': 'preview', 'accepted': None} if args.preview else publish(
        bulletin, NotificationState(Path('data/enso_notification_state.json')), now)
    report = Path('reports/enso')
    report.mkdir(parents=True, exist_ok=True)
    (report / 'boletim.json').write_text(json.dumps({'collected_at': now.isoformat(), 'bulletin': bulletin,
        'notice': notice(bulletin), 'delivery': outcome}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"Boletim ENOS de {bulletin['issued']}, {bulletin['status']}. Envio: {outcome['status']}.")
    if outcome['status'] == 'failed':
        raise SystemExit('Envio do boletim ENOS não confirmado')


if __name__ == '__main__':
    main()
