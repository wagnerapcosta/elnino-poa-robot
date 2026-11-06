"""Airport-first geographic scope, independent of notification rendering."""
import json
import math
import re
import unicodedata
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parent / 'config' / 'airport_focus.json'


def load_focus():
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    assert config['icao'] == 'SBPA' and config['radius_km'] > 0
    return config


def name_key(value):
    text = unicodedata.normalize('NFKD', value.casefold())
    return ''.join(c for c in text if c.isalnum() and not unicodedata.combining(c))


def distance_km(lat, lon, center=None):
    center = center or load_focus()['center']
    a, b = math.radians(lat - center['lat']), math.radians(lon - center['lon'])
    x = math.sin(a / 2)**2 + math.cos(math.radians(lat)) * math.cos(math.radians(center['lat'])) * math.sin(b / 2)**2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1, max(0, x))))


def focus_municipal(product, config=None):
    """Keep intersecting/border regions, retain unknown geography conservatively.

    All original alerts and exclusion reasons remain available for audit. A
    municipality-wide warning is never reclassified as airport-point weather.
    """
    if product.get('status') not in ('ok', 'partial'):
        return product
    config = config or load_focus()
    regions = {r['order']: r for r in config['regions']}
    selected, excluded, unknown = [], [], False
    for alert in product.get('alerts', []):
        if re.match(r'^\s*(?:teste\b|simulad[oa]\b|dados\s+simulados\b)', alert['description'], re.I):
            excluded.append(dict(reason='source_test', alert=alert))
            continue
        keep = []
        for region in alert['regions']:
            mapped = regions.get(region['order'])
            if not mapped or name_key(mapped['name']) != name_key(region['name']):
                unknown = True
                keep.append(dict(region, airport_relation='unverified'))
            elif mapped['distance_km'] <= config['radius_km'] + config['boundary_margin_km']:
                relation = 'intersects' if mapped['distance_km'] <= config['radius_km'] else 'border'
                keep.append(dict(region, airport_relation=relation,
                                 region_edge_distance_km=mapped['distance_km']))
            else:
                excluded.append(dict(reason='outside_airport_focus', region=region, alert=alert))
        if keep:
            selected.append(dict(alert, regions=keep))
    return dict(product, alerts=selected, regional_alerts=product.get('alerts', []),
                excluded_alerts=excluded, status='partial' if unknown else product['status'],
                airport_focus=dict(icao=config['icao'], center=config['center'], radius_km=config['radius_km'],
                                   boundary_margin_km=config['boundary_margin_km'],
                                   geometry_verified=not unknown,
                                   source=config['geometry_source'], verified_on=config['verified_on']),
                scope='Regiões municipais que interceptam SBPA + raio de referência de 4 km; margem conservadora de 100 m. Não prova impacto pontual.')
