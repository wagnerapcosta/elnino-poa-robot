"""Durable event memory. Tests use memory-only instances; production shares JSON in Git.

Only HTTP-accepted notifications advance the sent baseline. Source failures never
clear weather/municipal events. Test notifications intentionally bypass this store.
"""
import csv
import hashlib
import json
import math
import os
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from operational_notices import primary_failure_notice, civil_defense_notice
from rain_alert import TZ


def normalized(value):
    return re.sub(r'\s+', ' ', str(value)).strip().casefold()


def instant(value):
    return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()


def materially_changed(old, new):
    if old.get('level') != new.get('level') or old.get('kind') != new.get('kind'):
        return True
    if new.get('level') == 'verde':
        return False
    for name, value in new.get('metrics', {}).items():
        previous = old.get('metrics', {}).get(name)
        if previous is None:
            return True
        minimum, fraction = (10, .20) if name == 'gust' else (5, .25)
        if abs(value - previous) + 1e-9 >= max(minimum, abs(previous) * fraction):
            return True
    return False


class NotificationState:
    def __init__(self, path=None, history_path=None):
        self.path = Path(path) if path is not None else None
        self.data = {'schema': 1, 'events': {}, 'collection': {'failed': False}}
        if self.path and self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                if loaded.get('schema') != 1 or not isinstance(loaded.get('events'), dict) or type(loaded.get('collection', {}).get('failed')) is not bool:
                    raise ValueError('Formato de estado inválido')
                if any(not isinstance(v, dict) or type(v.get('active')) is not bool or not isinstance(v.get('signature'), dict)
                       for v in loaded['events'].values()):
                    raise ValueError('Evento de estado inválido')
                if loaded['collection']['failed']:
                    datetime.fromisoformat(loaded['collection']['since'])
                self.data = loaded
            except (ValueError, TypeError, AttributeError, KeyError) as exc:
                raise RuntimeError('Memória de notificações inválida; não será reiniciada silenciosamente') from exc
        elif history_path is not None:
            self._seed_general(history_path)
        self.save()

    def _seed_general(self, history_path):
        """The last history row was written after its mobile summary was sent."""
        try:
            with Path(history_path).open(encoding='utf-8-sig', newline='') as stream:
                rows = list(csv.DictReader(stream))
            if not rows:
                return
            row = rows[-1]
            level = row['tactical_level']
            metrics = dict(p24=float(row['p24_max_mm']), p72=float(row['p72_max_mm']), gust=float(row['gust_max_kmh']))
            if level not in ('verde', 'amarelo', 'laranja', 'vermelho') or any(not math.isfinite(v) or v < 0 for v in metrics.values()):
                return
            self.data['events']['general'] = dict(active=True, signature=dict(level=level, metrics=metrics),
                                                  last_sent=row['timestamp'], seeded_from_history=True)
        except (OSError, KeyError, ValueError, TypeError):
            pass

    def save(self):
        if self.path is None:
            return
        content = json.dumps(self.data, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.read_text(encoding='utf-8') == content:
            return
        temporary = self.path.with_suffix('.json.tmp')
        temporary.write_text(content, encoding='utf-8')
        os.replace(temporary, self.path)

    def clear(self, key):
        entry = self.data['events'].get(key)
        if entry and entry['active']:
            entry['active'] = False
            self.save()

    def changed(self, key, signature, relevance=None):
        entry = self.data['events'].get(key)
        if not entry or not entry['active']:
            return True
        return relevance(entry['signature'], signature) if relevance else entry['signature'] != signature

    def send(self, key, signature, notice, now, notify, relevance=None):
        if not self.changed(key, signature, relevance):
            return dict(title=notice['title'], status='suppressed', accepted=None, error=None)
        entry = self.data['events'].get(key)
        title = ('ATUALIZACAO - ' if entry and entry['active'] else '') + notice['title']
        try:
            accepted = notify(title, notice['body'], notice['level']) is True
            error = None if accepted else 'Serviço não confirmou envio'
        except Exception as exc:
            accepted, error = False, type(exc).__name__ + ': envio não confirmado'
        if accepted:
            self.data['events'][key] = dict(active=True, signature=deepcopy(signature), last_sent=now.isoformat())
            self.save()
        return dict(title=title, status='sent' if accepted else 'failed', accepted=accepted, error=error)

    def collection(self, collection, forecast, now, notify):
        failure = primary_failure_notice(collection, forecast, now)
        marker = self.data['collection']
        if failure:
            if not marker['failed']:
                marker.update(failed=True, since=now.isoformat())
                self.clear('collection_recovery')
                self.save()
            kind = 'transport' if collection.get('status') != 'ok' else ('hourly' if forecast.get('rain_12h', {}).get('status') != 'ok' else 'daily')
            return [self.send('collection_failure', {'kind': kind}, failure, now, notify)]
        if not marker['failed']:
            return []
        notice = dict(title='Radar POA - COLETA DA PREVISAO NORMALIZADA', level='verde',
                      body=('COLETA DA PREVISÃO PRINCIPAL NORMALIZADA — Open-Meteo.\n'
                            'Os dados horários e diários voltaram a passar nas verificações de formato, valores e cobertura.\n'
                            f"Verificação: {now.astimezone(TZ).strftime('%d/%m/%Y %H:%M')} BRT.\n"
                            'A normalização da coleta NÃO significa ausência de risco meteorológico. Consulte os alertas atuais.'))
        outcome = self.send('collection_recovery', {'episode': marker['since']}, notice, now, notify)
        if outcome['status'] in ('sent', 'suppressed'):
            marker['failed'] = False
            self.clear('collection_failure')
            self.save()
        return [outcome]

    def municipal(self, product, now, notify):
        if product.get('status') not in ('ok', 'partial'):
            return []
        changed_alerts, signatures, present = [], {}, set()
        for alert in product.get('alerts', []):
            # IDs regenerated by the provider and poll timestamps are excluded.
            common = dict(level=alert['criticality'], start=instant(alert['start']), end=instant(alert['end']),
                          types=sorted({normalized(t) for t in alert['types']}),
                          description_sha256=hashlib.sha256(normalized(alert['description']).encode('utf-8')).hexdigest())
            groups = []
            for region in alert['regions']:
                key = 'municipal:' + str(region['order'])
                present.add(key)
                signature = dict(common, region=normalized(region['name']))
                signatures[key] = signature
                if self.changed(key, signature):
                    groups.append(region)
            if groups:
                changed_alerts.append(dict(alert, regions=groups))
        if product.get('status') == 'ok':
            for key in list(self.data['events']):
                if key.startswith('municipal:') and key not in present:
                    self.clear(key)
        if not changed_alerts:
            return []
        outcomes = []
        pending = changed_alerts
        while pending:
            notice = civil_defense_notice(dict(product, alerts=pending), now)
            included = set(notice['region_orders'])
            keys = ['municipal:' + str(order) for order in notice['region_orders']]
            if any(self.data['events'].get(key, {}).get('active') for key in keys):
                notice['title'] = 'ATUALIZACAO - ' + notice['title']
            # Each page has its own acceptance boundary. Never advance omitted or failed regions.
            try:
                accepted = notify(notice['title'], notice['body'], notice['level']) is True
                error = None if accepted else 'Serviço não confirmou envio'
            except Exception as exc:
                accepted, error = False, type(exc).__name__ + ': envio não confirmado'
            if accepted:
                for key in keys:
                    self.data['events'][key] = dict(active=True, signature=deepcopy(signatures[key]), last_sent=now.isoformat())
                self.save()
            outcomes.append(dict(title=notice['title'], status='sent' if accepted else 'failed',
                                 accepted=accepted, error=error, region_orders=notice['region_orders']))
            # Try the other pages even after a failure; retry failed regions only on the next poll.
            pending = [dict(a, regions=[r for r in a['regions'] if r['order'] not in included])
                       for a in pending if any(r['order'] not in included for r in a['regions'])]
        return outcomes

    def rain(self, forecast, official, comparison, notice, now, notify):
        alert = forecast['rain_12h']
        if alert.get('triggered') is True:
            signature = dict(kind='primary', level='laranja', metrics={'rain': alert['total_mm']})
        elif comparison.get('cptec_attention'):
            cptec = official['cptec']
            signature = dict(kind='cptec', level='amarelo', metrics={'rain': min(cptec['alignment_start_mm'], cptec['alignment_end_mm'])})
        else:
            previous_kind = self.data['events'].get('rain', {}).get('signature', {}).get('kind')
            cptec = official.get('cptec', {})
            if alert.get('status') == 'ok' and (previous_kind != 'cptec' or cptec.get('status') == 'ok' and cptec.get('signal_12h') is False):
                self.clear('rain')
            return []
        return [self.send('rain', signature, notice, now, notify, materially_changed)]

    def general(self, forecast, notice, now, notify):
        if forecast.get('data_status') != 'ok':
            return []
        # The reference must match the actual summary, including non-forecast tactical changes.
        signature = dict(level=notice['level'], rain_only=notice.get('rain_only') is True,
                         metrics=dict(p24=forecast['p24_max_mm'], p72=forecast['p72_max_mm'], gust=forecast['gust_max_kmh']))
        if signature['level'] == 'verde' and 'general' not in self.data['events']:
            self.data['events']['general'] = dict(active=True, signature=signature, baseline=True)
            self.save()
            return []
        # A low-level general message caused solely by the same 12h episode is
        # already conveyed by the specific alert; do not send it twice.
        previous = self.data['events'].get('general', {})
        previous_level = previous.get('signature', {}).get('level')
        rain_signature = dict(kind='primary', level='laranja', metrics={'rain': forecast['rain_12h'].get('total_mm')})
        if (notice.get('rain_only') is True and forecast['rain_12h'].get('triggered') is True
                and signature['level'] in ('verde', 'amarelo') and previous_level not in ('laranja', 'vermelho')
                and not self.changed('rain', rain_signature, materially_changed)):
            if previous.get('last_sent') and not previous.get('covered_by_rain'):
                # Keep the last accepted summary metrics; rain-only polls must
                # not erase that baseline or cause an unchanged summary to repeat.
                return []
            self.data['events']['general'] = dict(active=True, signature=signature, covered_by_rain=True)
            self.save()
            return []
        # A rain-covered baseline is not an independently delivered general summary.
        # Its first independent notice must be attempted even at the same yellow level.
        def relevant(old, new):
            return (previous.get('covered_by_rain', False)
                    or old.get('rain_only', False) and not new['rain_only']
                    or materially_changed(old, new))
        return [self.send('general', signature, notice, now, notify, relevant)]
