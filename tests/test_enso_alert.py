import unittest
from datetime import date, datetime
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock

import enso_alert as enso
from notification_state import NotificationState
from rain_alert import TZ


def bulletin(day='8 October 2026', status='El Niño Advisory'):
    return f'<p>CLIMATE PREDICTION CENTER/NCEP/NWS<br>{day}</p>' \
           f'<p>ENSO Alert System Status: <a>{status}</a></p><p>Synopsis: Details</p>'


def outlook(edition='October 2026', season='NDJ Nov Dec Jan', values=(0, 0, 0, 0, 0, 0, 0, 4, 96)):
    headings = ['Season'] + ['other'] * 7 + ['1.5°C ≤ Index < 2.0°C', 'Index ≥ 2.0°C']
    header = ''.join(f'<th>{heading}</th>' for heading in headings)
    row = ''.join(f'<td>{value}</td>' for value in (season, *values))
    return f'<h2>Issued {edition}</h2><table id="probabilities-table"><tr>{header}</tr><tr>{row}</tr></table>'


class EnsoAlertTests(unittest.TestCase):
    def test_bulletin_uses_official_dated_status(self):
        parsed = enso.parse_bulletin(bulletin(status='El Niño Advisory / La Niña Watch'), date(2026, 11, 11))
        self.assertEqual(parsed, {'issued': '2026-10-08', 'status': 'El Niño ativo / Vigilância para La Niña'})
        for raw in (bulletin(status='Unexpected'), bulletin('12 November 2026'), bulletin('8 September 2026'), 'El Niño'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                enso.parse_bulletin(raw, date(2026, 11, 11))

    def test_outlook_keeps_the_official_edition_and_trimestre(self):
        issued = date(2026, 10, 8)
        parsed = enso.parse_outlook(outlook(), issued)
        self.assertEqual(parsed, {'season': 'NDJ', 'season_start_year': 2026, 'strong_pct': 100})
        report = enso.notice({'issued': issued.isoformat(), 'status': 'El Niño ativo', 'outlook': parsed})
        self.assertIn('nov/2026 a jan/2027 · ≈100% (RONI)', report['body'])
        self.assertEqual(report['level'], 'verde')
        for raw in (outlook(edition='September 2026'), outlook(values=(0,) * 9), outlook(season='')):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                enso.parse_outlook(raw, issued)
        rollover = enso.parse_outlook(outlook(edition='December 2026', season='JFM Jan Feb Mar'), date(2026, 12, 10))
        self.assertEqual(rollover['season_start_year'], 2027)

    def test_memory_retries_unaccepted_and_suppresses_duplicate_and_older_bulletins(self):
        now = datetime(2026, 11, 11, 12, tzinfo=TZ)
        issue = {'issued': '2026-10-08', 'status': 'El Niño ativo'}
        older = dict(issue, issued='2026-09-10')
        revised = dict(issue, status='Último aviso de El Niño')
        sender = Mock(side_effect=[False, True, True])
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'enso.json'
            self.assertEqual(enso.publish(issue, NotificationState(path), now, sender)['status'], 'failed')
            self.assertEqual(enso.publish(issue, NotificationState(path), now, sender)['status'], 'sent')
            self.assertEqual(enso.publish(issue, NotificationState(path), now, sender)['status'], 'suppressed')
            self.assertEqual(enso.publish(older, NotificationState(path), now, sender)['status'], 'suppressed')
            self.assertEqual(enso.publish(revised, NotificationState(path), now, sender)['status'], 'sent')
        self.assertEqual(sender.call_count, 3)
        self.assertEqual(sender.call_args.kwargs['source_url'], enso.NOAA_BULLETIN)
