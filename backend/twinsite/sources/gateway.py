"""Scientific Data Gateway: public NASA services, retrieved end to end.

Implemented connectors (real retrieval -> decode -> QA -> persisted observations):
  * NASA POWER climatology (point; MERRA-2 / CERES reanalysis -> kind 'reanalysis_model')
  * NASA GIBS WMS (true-colour visualization -> kind 'visualization', never a measurement)
  * NASA CMR granule discovery (e.g. MOD11A2 LST) -> kind 'discovery_only' (no value; download
    needs a fresh Earthdata token because the previous one is treated as compromised)
  * NSSDCA Planetary Fact Sheet constants -> kind 'reference_constant'
Existing connectors (unchanged): LP DAAC SRTMGL1 and PDS MOLA via the published G2 pair.
"""
import hashlib
import json
import math
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from twinsite.storage.science_db import science_db

UA = 'TwinSite/1.0 (NASA Space Apps planetary-analog research)'
POWER_URL = 'https://power.larc.nasa.gov/api/temporal/climatology/point'
GIBS_WMS = 'https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi'
CMR_GRANULES = 'https://cmr.earthdata.nasa.gov/search/granules.json'
GIBS_LAYER, GIBS_DATE = 'MODIS_Terra_CorrectedReflectance_TrueColor', '2025-11-05'

# parameter -> (domain, quantity, unit expected from POWER, comparability note)
POWER_PARAMS = {
    'T2M': ('atmosphere_climate', 'air_temperature_2m', 'C',
            'Near-surface AIR temperature (reanalysis). Not land-surface temperature and not a planetary surface temperature.'),
    'T2M_RANGE': ('thermal', 'air_temperature_diurnal_range_2m', 'C', 'Daily max-min of 2 m air temperature (reanalysis).'),
    'WS10M': ('atmosphere_climate', 'wind_speed_10m', 'm/s', 'Reanalysis wind at 10 m.'),
    'PRECTOTCORR': ('atmosphere_climate', 'precipitation_rate', 'mm/day', 'Bias-corrected precipitation (MERRA-2).'),
    'RH2M': ('atmosphere_climate', 'relative_humidity_2m', '%', 'Reanalysis relative humidity.'),
    'PS': ('atmosphere_climate', 'surface_pressure', 'kPa', 'Reanalysis surface pressure; compare with Mars ~0.636 kPa only as a constraint, not as an analog match.'),
    'ALLSKY_SFC_SW_DWN': ('planetary_constraints', 'surface_shortwave_irradiance_all_sky', 'kWh/m^2/day',
                          'CERES/MERRA-2 derived insolation.'),
}
MONTHS = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')

# NASA NSSDCA Planetary Fact Sheet (https://nssdc.gsfc.nasa.gov/planetary/factsheet/), metric values.
CONSTANTS = {
    'Earth': {'surface_gravity': (9.80, 'm/s^2'), 'mean_radius': (6371.0, 'km'), 'surface_pressure': (101.4, 'kPa'),
              'length_of_day': (24.0, 'h')},
    'Moon': {'surface_gravity': (1.62, 'm/s^2'), 'mean_radius': (1737.5, 'km'), 'surface_pressure': (1e-13, 'kPa'),
             'length_of_day': (708.7, 'h')},
    'Mars': {'surface_gravity': (3.71, 'm/s^2'), 'mean_radius': (3389.5, 'km'), 'surface_pressure': (0.636, 'kPa'),
             'length_of_day': (24.7, 'h')},
}
FACT_SHEET = 'https://nssdc.gsfc.nasa.gov/planetary/factsheet/'

SOURCES = [
    dict(source_id='lpdaac-srtmgl1', name='NASA SRTMGL1 v003 (LP DAAC)', provider='NASA LP DAAC', bodies=['Earth'],
         domains=['topography'], access='Earthdata-authenticated download', auth='earthdata_token',
         documentation_url='https://lpdaac.usgs.gov/products/srtmgl1v003/', status='integrated_cached',
         notes='Verified cached tile; previous Earthdata token treated as compromised, not reused.'),
    dict(source_id='pds-mola-megdr', name='MGS MOLA MEGDR (PDS Geosciences)', provider='NASA PDS', bodies=['Mars'],
         domains=['topography'], access='public', auth='none',
         documentation_url='https://pds-geosciences.wustl.edu/missions/mgs/megdr.html', status='integrated_cached', notes=''),
    dict(source_id='nasa-power', name='NASA POWER climatology (MERRA-2/CERES)', provider='NASA LaRC', bodies=['Earth'],
         domains=['atmosphere_climate', 'thermal', 'temporal', 'planetary_constraints'], access='public REST', auth='none',
         documentation_url='https://power.larc.nasa.gov/docs/services/api/', status='integrated_live',
         notes='Reanalysis/model product at ~0.5x0.625 deg; not station measurements.'),
    dict(source_id='nasa-gibs', name='NASA GIBS WMS (MODIS Terra true colour)', provider='NASA ESDIS', bodies=['Earth'],
         domains=['surface_composition'], access='public WMS', auth='none',
         documentation_url='https://nasa-gibs.github.io/gibs-api-docs/', status='integrated_live',
         notes='Visualization only; colours are not calibrated reflectance. Used by A02 for qualitative reading.'),
    dict(source_id='cmr-mod11a2', name='MODIS MOD11A2 v061 LST (CMR discovery)', provider='NASA LP DAAC', bodies=['Earth'],
         domains=['thermal'], access='public discovery; Earthdata download', auth='earthdata_token',
         documentation_url='https://lpdaac.usgs.gov/products/mod11a2v061/', status='discovery_only',
         notes='Granules discovered; HDF4 download requires a NEW Earthdata token (old one compromised).'),
    dict(source_id='nssdca-factsheet', name='NSSDCA Planetary Fact Sheet', provider='NASA GSFC', bodies=['Earth', 'Moon', 'Mars'],
         domains=['planetary_constraints'], access='public reference', auth='none', documentation_url=FACT_SHEET,
         status='reference_constants', notes='Bulk constants; not site observations.'),
]


def _get(url, timeout=60, limit=30_000_000):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read(limit), resp.headers.get('Content-Type', '')


def _store_asset(data_dir, source_id, data, ext):
    sha = hashlib.sha256(data).hexdigest()
    key = f'sources/{source_id}/{sha}.{ext}'
    path = data_dir / key
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_bytes(data)
        tmp.replace(path)
    return sha, key


def _register_sources(db):
    for s in SOURCES:
        db.upsert_source(**s)


def site_id_for(lon, lat):
    coords = f'{lat:+.3f}{lon:+.3f}'.replace('+', 'p').replace('-', 'm').replace('.', '_')
    return 'earth-' + coords


def acquire_power(data_dir, site_id, lon, lat, refresh=False, timeout=60):
    db = science_db(data_dir)
    _register_sources(db)
    query = urllib.parse.urlencode({'parameters': ','.join(POWER_PARAMS), 'community': 'RE', 'longitude': f'{lon:.4f}',
                                    'latitude': f'{lat:.4f}', 'format': 'JSON'})
    url = f'{POWER_URL}?{query}'
    cache = data_dir / 'sources' / 'nasa-power' / f'{hashlib.sha256(url.encode()).hexdigest()[:24]}.url'
    if cache.exists() and not refresh:
        raw = (data_dir / cache.read_text()).read_bytes()
    else:
        raw, _ = _get(url, timeout=timeout)
    sha, key = _store_asset(data_dir, 'nasa-power', raw, 'json')
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(key)
    doc = json.loads(raw)
    header = doc.get('header') or {}
    fill = header.get('fill_value', -999.0)
    params = (doc.get('properties') or {}).get('parameter') or {}
    units = {k: (v or {}).get('units') for k, v in (doc.get('parameters') or {}).items()}
    period = header.get('range') or f"{header.get('start', '?')}-{header.get('end', '?')}"
    asset_id = f'power-{sha[:16]}'
    db.upsert_asset(asset_id=asset_id, source_id='nasa-power', product_id='POWER climatology ' + period,
                    granule_id=f'point {lat:.4f},{lon:.4f}', source_url=url, sha256=sha, byte_size=len(raw),
                    media_type='application/json', object_key=key)
    geometry = doc.get('geometry', {}).get('coordinates')
    out = []
    for param, (domain, quantity, unit, note) in POWER_PARAMS.items():
        series = params.get(param) or {}
        monthly = [series.get(m) for m in MONTHS]
        valid = [v for v in monthly if isinstance(v, (int, float)) and v != fill and math.isfinite(v)]
        ann = series.get('ANN')
        got_unit = units.get(param) or unit
        norm = lambda u: u.replace(' ', '').replace('-hr', 'h').replace('kWh', 'kwh').lower()  # noqa: E731
        flags = [] if norm(got_unit) == norm(unit) else ['UNIT_MISMATCH:' + got_unit]
        missing = None
        if not isinstance(ann, (int, float)) or ann == fill:
            ann, missing = None, 'POWER fill value'
        ev = f'power-{site_id}-{param.lower()}-{sha[:8]}'
        row = dict(evidence_id=ev, site_id=site_id, body='Earth', domain=domain, quantity=quantity, value=ann, unit=unit,
                   kind='reanalysis_model', statistic=f'climatological annual mean {period}',
                   temporal_support=f'monthly climatology {period}', spatial_support='POWER grid cell ~0.5 x 0.625 deg',
                   crs='EPSG:4326', vertical_datum=None, qa_status='ACCEPT' if ann is not None and len(valid) == 12 else 'LIMITED',
                   quality_flags=flags + (['INCOMPLETE_MONTHLY_SERIES'] if len(valid) != 12 else []),
                   uncertainty={'kind': 'monthly_range', 'low': min(valid) if valid else None,
                                'high': max(valid) if valid else None,
                                'basis': 'min/max of monthly climatology (seasonal variability, not instrument error)'},
                   missing_reason=missing, source_id='nasa-power', product_id='POWER climatology', asset_id=asset_id,
                   processing='twinsite-gateway/1.0 (fill-value mask, unit check)', comparability=note)
        db.upsert_observation(**row)
        out.append(row)
        if param == 'T2M' and len(valid) == 12:
            amp = round(max(valid) - min(valid), 3)
            row2 = dict(row, evidence_id=f'power-{site_id}-t2m_seasonal_amplitude-{sha[:8]}', domain='temporal',
                        quantity='air_temperature_seasonal_amplitude', value=amp, unit='C',
                        kind='reanalysis_model',
                        statistic='max - min of monthly climatological means', uncertainty=None,
                        comparability='Seasonal behaviour of Earth air temperature; Mars/Moon equivalents need a thermal source.')
            db.upsert_observation(**row2)
            out.append(row2)
    db.upsert_site(keep_name=True, site_id=site_id, name=site_id, body='Earth', crs='EPSG:4326', lon=lon, lat=lat,
                   bbox=[lon - 0.15, lat - 0.15, lon + 0.15, lat + 0.15])
    return {'asset_id': asset_id, 'sha256': sha, 'grid_point': geometry, 'observations': out}


def acquire_gibs(data_dir, site_id, bbox, date=GIBS_DATE, timeout=60):
    db = science_db(data_dir)
    _register_sources(db)
    # Cache: reuse a previously retrieved image for this site/date (bytes verified against the stored hash).
    _, rows = db.observations([site_id], kind='visualization', limit=20)
    for row in rows:
        asset = db.asset(row['asset_id']) if row.get('asset_id') else None
        if asset and asset['granule_id'] == date and (data_dir / asset['object_key']).is_file():
            data = (data_dir / asset['object_key']).read_bytes()
            if hashlib.sha256(data).hexdigest() == asset['sha256']:
                return {'evidence_id': row['evidence_id'], 'asset_id': asset['asset_id'], 'bytes': data,
                        'mime': 'image/jpeg', 'label': f'NASA GIBS {GIBS_LAYER} {date} over bbox {bbox}'}
    w, s, e, n = bbox
    query = urllib.parse.urlencode({'SERVICE': 'WMS', 'REQUEST': 'GetMap', 'VERSION': '1.3.0', 'LAYERS': GIBS_LAYER,
                                    'CRS': 'EPSG:4326', 'BBOX': f'{s},{w},{n},{e}', 'WIDTH': 512, 'HEIGHT': 512,
                                    'FORMAT': 'image/jpeg', 'TIME': date})
    url = f'{GIBS_WMS}?{query}'
    data, ctype = _get(url, timeout=timeout, limit=5_000_000)
    if not ctype.startswith('image/') or data[:2] != b'\xff\xd8':
        raise ValueError('GIBS did not return a JPEG (service exception)')
    sha, key = _store_asset(data_dir, 'nasa-gibs', data, 'jpg')
    asset_id = f'gibs-{sha[:16]}'
    db.upsert_asset(asset_id=asset_id, source_id='nasa-gibs', product_id=GIBS_LAYER, granule_id=date, source_url=url,
                    sha256=sha, byte_size=len(data), media_type='image/jpeg', object_key=key)
    ev = f'gibs-{site_id}-truecolor-{sha[:8]}'
    db.upsert_observation(evidence_id=ev, site_id=site_id, body='Earth', domain='surface_composition',
                          quantity='true_colour_visualization', value=None, unit=None, kind='visualization',
                          statistic=None, temporal_support=date, spatial_support='512x512 px over AOI (~250 m MODIS)',
                          crs='EPSG:4326', qa_status='VISUAL_ONLY', quality_flags=['NOT_CALIBRATED_REFLECTANCE'],
                          missing_reason=None, source_id='nasa-gibs', product_id=GIBS_LAYER, asset_id=asset_id,
                          processing='WMS GetMap', comparability='Qualitative only.')
    return {'evidence_id': ev, 'asset_id': asset_id, 'bytes': data, 'mime': 'image/jpeg',
            'label': f'NASA GIBS {GIBS_LAYER} {date} over bbox {bbox}'}


def discover_cmr(data_dir, site_id, bbox, short_name='MOD11A2', version='061', temporal='2024-06-01T00:00:00Z,2024-06-30T23:59:59Z'):
    db = science_db(data_dir)
    _register_sources(db)
    query = urllib.parse.urlencode({'short_name': short_name, 'version': version, 'bounding_box': ','.join(map(str, bbox)),
                                    'temporal': temporal, 'page_size': 10})
    raw, _ = _get(f'{CMR_GRANULES}?{query}')
    entries = json.loads(raw).get('feed', {}).get('entry', [])
    ev = f'cmr-{site_id}-{short_name.lower()}-{version}'
    db.upsert_observation(evidence_id=ev, site_id=site_id, body='Earth', domain='thermal', quantity='land_surface_temperature',
                          value=None, unit='K', kind='discovery_only', statistic=None, temporal_support=temporal,
                          spatial_support='1 km (8-day composite)', crs='MODIS sinusoidal', qa_status='NOT_RETRIEVED',
                          quality_flags=['DOWNLOAD_REQUIRES_NEW_EARTHDATA_TOKEN'],
                          missing_reason=f'{len(entries)} granules discovered; not downloaded (no valid Earthdata token)',
                          source_id='cmr-mod11a2', product_id=f'{short_name}.{version}',
                          asset_id=None, processing='CMR granule search',
                          comparability='LST (skin) differs from 2 m air temperature.')
    return [e.get('producer_granule_id') or e.get('title') for e in entries]


def store_constants(data_dir, bodies):
    db = science_db(data_dir)
    _register_sources(db)
    out = []
    for body in bodies:
        for quantity, (value, unit) in CONSTANTS[body].items():
            row = dict(evidence_id=f'ctx-const-{body.lower()}-{quantity}', site_id=f'body-{body.lower()}', body=body,
                       domain='planetary_constraints', quantity=quantity, value=value, unit=unit, kind='reference_constant',
                       statistic='bulk planetary value', temporal_support=None, spatial_support='whole body', crs=None,
                       qa_status='ACCEPT', quality_flags=[], missing_reason=None, source_id='nssdca-factsheet',
                       product_id='Planetary Fact Sheet', asset_id=None, processing='transcribed constant',
                       comparability='Body-level constant, not a site measurement.')
            db.upsert_observation(**row)
            out.append(row)
        db.upsert_site(site_id=f'body-{body.lower()}', name=f'{body} (whole body)', body=body, crs=None, lon=None, lat=None,
                       bbox=None)
    return out


def packet_item(row):
    unc = row.get('uncertainty')
    if isinstance(unc, str):
        unc = json.loads(unc)
    return {'evidence_id': row['evidence_id'], 'site': row['site_id'], 'body': row['body'], 'feature': row['quantity'],
            'domain': row['domain'], 'value': row['value'], 'unit': row['unit'], 'status': row['kind'],
            'product': row['product_id'], 'interval_p10_p90': [unc.get('low'), unc.get('high')] if unc else None,
            'note': row.get('comparability')}


def mission_context(payload, observations, data_dir, fetch_image=True):
    """Real gateway evidence for a measured mission's Earth sites (+ body constants). Synthetic
    missions get none, so synthetic inputs are never mixed with real context."""
    if not observations:
        return [], None
    data_dir = Path(data_dir)
    bodies = sorted({s.get('body', 'Earth') for s in payload['sites']} | {p['body'] for p in payload['target_profiles']})
    context = [packet_item(r) for r in store_constants(data_dir, [b for b in bodies if b in CONSTANTS])]
    image = None
    for site in payload['sites']:
        if site.get('body', 'Earth') != 'Earth' or site.get('longitude') is None:
            continue
        lon, lat = site['longitude'], site['latitude']
        try:
            power = acquire_power(data_dir, site['id'], lon, lat, timeout=15)
            context += [packet_item(r) for r in power['observations'] if r['value'] is not None]
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError):
            pass
        # Persisted accessibility evidence (OSM) for this site, if retrieved earlier; never fetched inside a mission.
        _, osm = science_db(data_dir).observations([site['id']], domain='accessibility_environment', limit=10)
        context += [packet_item(r) for r in osm if r['value'] is not None]
        if fetch_image and image is None:
            try:
                image = acquire_gibs(data_dir, site['id'], [lon - 0.5, lat - 0.5, lon + 0.5, lat + 0.5], timeout=15)
            except (urllib.error.URLError, TimeoutError, ValueError):
                image = None
    return context, image


GEOCODER = 'https://geocoding-api.open-meteo.com/v1/search'
_PLACE_CACHE = {}


def search_places(data_dir, q, count=10):
    """Search named places worldwide (Open-Meteo Geocoding API, GeoNames-based, free, no key). Cached in memory."""
    key = q.lower()
    if key in _PLACE_CACHE:
        return _PLACE_CACHE[key]
    url = f"{GEOCODER}?{urllib.parse.urlencode({'name': q, 'count': count, 'language': 'en', 'format': 'json'})}"
    try:
        raw, _ = _get(url, timeout=8, limit=2_000_000)
        results = json.loads(raw).get('results') or []
    except (urllib.error.URLError, TimeoutError, ValueError):
        # Fallback: OpenStreetMap Nominatim (ODbL); low volume, identified User-Agent, cached.
        nurl = 'https://nominatim.openstreetmap.org/search?' + urllib.parse.urlencode({'q': q, 'format': 'jsonv2', 'limit': count})
        raw, _ = _get(nurl, timeout=8, limit=2_000_000)
        results = [{'name': r.get('name') or r.get('display_name', '').split(',')[0], 'country': r.get('display_name', '').split(',')[-1].strip(),
                    'feature_code': r.get('type'), 'latitude': float(r['lat']), 'longitude': float(r['lon']), 'id': r.get('osm_id')}
                   for r in json.loads(raw)]
    out = []
    for r in results:
        if not isinstance(r.get('latitude'), (int, float)) or not isinstance(r.get('longitude'), (int, float)):
            continue
        out.append({'name': r.get('name'), 'admin1': r.get('admin1'), 'country': r.get('country'),
                    'country_code': r.get('country_code'), 'feature_code': r.get('feature_code'),
                    'latitude': round(r['latitude'], 5), 'longitude': round(r['longitude'], 5),
                    'elevation_m': r.get('elevation'), 'geonames_id': r.get('id')})
    if len(_PLACE_CACHE) > 500:
        _PLACE_CACHE.clear()
    _PLACE_CACHE[key] = out
    return out


OVERPASS = 'https://overpass-api.de/api/interpreter'
OVERPASS_MIRRORS = (OVERPASS, 'https://overpass.kumi.systems/api/interpreter', 'https://overpass.private.coffee/api/interpreter')


def acquire_osm_access(data_dir, site_id, bbox, timeout=40):
    """OpenStreetMap (ODbL) mapped access within the AOI: counts of highway ways by class via Overpass.
    Context evidence for the accessibility domain; OSM completeness varies by region (flagged)."""
    w, s, e, n = bbox
    q = (f'[out:json][timeout:{timeout}];('
         f'way["highway"~"^(motorway|trunk|primary|secondary|tertiary)$"]({s},{w},{n},{e});'
         f')->.major;(way["highway"~"^(unclassified|residential|service|track|path)$"]({s},{w},{n},{e}););'
         '.major out count;out count;')
    raw, last, used = None, None, None
    for endpoint in OVERPASS_MIRRORS:
        try:
            req = urllib.request.Request(endpoint, data=urllib.parse.urlencode({'data': q}).encode(), headers={'User-Agent': UA})
            with urllib.request.urlopen(req, timeout=timeout + 15) as resp:
                raw, used = resp.read(2_000_000), endpoint
            break
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error
    if raw is None:
        raise last
    doc = json.loads(raw)
    counts = [int(el.get('tags', {}).get('ways', 0)) for el in doc.get('elements', []) if el.get('type') == 'count']
    if len(counts) != 2:
        raise ValueError('unexpected Overpass response')
    db = science_db(data_dir)
    db.upsert_source(source_id='osm-overpass', name='OpenStreetMap via Overpass API', provider='OpenStreetMap contributors (ODbL)',
                     bodies=['Earth'], domains=['accessibility_environment'], access='public API', auth='none',
                     documentation_url='https://wiki.openstreetmap.org/wiki/Overpass_API', status='integrated_live',
                     notes='Mapped roads/tracks counts within the AOI; completeness varies by region.')
    sha, key = _store_asset(data_dir, 'osm-overpass', raw, 'json')
    asset_id = f'osm-{sha[:16]}'
    db.upsert_asset(asset_id=asset_id, source_id='osm-overpass', product_id='OSM highway ways (Overpass count)',
                    granule_id=f'bbox {bbox}', source_url=used, sha256=sha, byte_size=len(raw),
                    media_type='application/json', object_key=key)
    out = []
    for q_name, value in (('mapped_major_roads_ways', counts[0]), ('mapped_minor_roads_tracks_ways', counts[1])):
        row = dict(evidence_id=f'osm-{site_id}-{q_name}-{sha[:8]}', site_id=site_id, body='Earth',
                   domain='accessibility_environment', quantity=q_name, value=float(value), unit='count',
                   kind='derived_measurement', statistic='count of OSM ways intersecting the AOI',
                   temporal_support='OSM snapshot at retrieval', spatial_support='~33 km AOI', crs='EPSG:4326',
                   qa_status='ACCEPT', quality_flags=['OSM_COMPLETENESS_VARIES_BY_REGION'], missing_reason=None,
                   source_id='osm-overpass', product_id='OSM highway ways', asset_id=asset_id,
                   processing='Overpass count query', comparability='Earth-only operational context; not used in scoring.')
        db.upsert_observation(**row)
        out.append(row)
    return out
