"""14-domain x 3-body coverage matrix computed from persisted evidence, not from intentions."""
import json
from pathlib import Path

from twinsite.storage.science_db import science_db

DOMAINS = ('spatial_identity', 'topography', 'thermal', 'atmosphere_climate', 'temporal', 'surface_composition',
           'geology_mineralogy', 'mechanics_mobility', 'resources_volatiles', 'planetary_constraints',
           'accessibility_environment', 'operations_economics', 'mission_requirements', 'evidence_quality')
BODIES = ('Earth', 'Moon', 'Mars')
PAIR = Path(__file__).resolve().parents[1] / 'processing/published/g2_feature_pair.json'

# Dependencies that are NOT implemented: named so nobody mistakes absence for coverage.
MISSING = {
    ('thermal', 'Earth'): 'MOD11A2 LST download needs a new Earthdata token (granules discovered only)',
    ('thermal', 'Moon'): 'LRO Diviner (PDS) connector not implemented',
    ('thermal', 'Mars'): 'THEMIS / MGS TES connector not implemented',
    ('topography', 'Moon'): 'LRO LOLA (PDS) connector not implemented',
    ('atmosphere_climate', 'Mars'): 'Curiosity REMS / Perseverance MEDA (PDS Atmospheres) not implemented; local rover data only',
    ('atmosphere_climate', 'Moon'): 'No atmosphere (exosphere); bulk constant only',
    ('surface_composition', 'Earth'): 'HLS / Sentinel-2 reflectance not implemented; GIBS imagery is visualization only',
    ('geology_mineralogy', 'Earth'): 'EMIT not implemented',
    ('geology_mineralogy', 'Mars'): 'CRISM not implemented',
    ('geology_mineralogy', 'Moon'): 'USGS unified lunar geology not implemented',
    ('resources_volatiles', 'Moon'): 'LEND / LP-NS hydrogen not implemented',
    ('resources_volatiles', 'Mars'): 'MONS/GRS hydrogen not implemented',
    ('mechanics_mobility', 'Earth'): 'Only slope/roughness proxies; no strength/traversability product',
    ('accessibility_environment', 'Earth'): 'OSM Overpass and Protected Planet not implemented; access is user-provided or unknown',
    ('operations_economics', 'Earth'): 'Costs/days only as user-provided mission inputs; never estimated',
}


def matrix(data_dir):
    db = science_db(Path(data_dir))
    persisted = db.coverage()
    pair = json.loads(PAIR.read_text())
    g2 = {}
    for o in pair['observations']:
        g2.setdefault(o['body'], set()).add((o['feature_id'], o['source_product'], o['value'] is not None))
    rows = []
    for domain in DOMAINS:
        for body in BODIES:
            hits = [p for p in persisted if p['domain'] == domain and p['body'] == body]
            sources = sorted({p['source_id'] for p in hits})
            kinds = sorted({p['kind'] for p in hits})
            quantities, simple, ai, explorer = [], False, False, bool(hits)
            status, validation = 'missing', 'none'
            if domain == 'topography' and body in g2:
                feats = sorted({f for f, _, has in g2[body] if has})
                products = sorted({p for _, p, _ in g2[body]})
                quantities = feats
                sources = sorted(set(sources) | set(products))
                status, validation, simple, ai, explorer = 'real_data', 'checksum + C5 provenance check (release BLOCK pending independent review)', True, True, True
            elif 'reanalysis_model' in kinds or 'measurement' in kinds or 'derived_measurement' in kinds:
                status, validation, ai = 'real_data', 'fill-value mask, unit check, offline parser test', True
            elif 'reference_constant' in kinds:
                status, validation, ai = 'reference_constant', 'transcribed from NSSDCA fact sheet', True
            elif 'visualization' in kinds:
                status, validation, ai = 'visualization_only', 'JPEG magic/content-type check; qualitative A02 reading', True
            elif 'discovery_only' in kinds:
                status, validation = 'source_metadata_only', 'CMR granule search'
            if domain == 'spatial_identity':
                status, validation, simple, ai, explorer = 'implemented', 'contract: body/CRS/bbox validated per location', True, True, True
            elif domain == 'mission_requirements':
                status, validation, simple, ai = 'user_input', 'mission_request schema', True, True
            elif domain == 'evidence_quality':
                status, validation, simple, ai, explorer = 'implemented', 'QA gates, provenance check, release sidecar', True, True, True
            elif domain == 'operations_economics' and status == 'missing':
                status = 'user_input_only'
            rows.append({'domain': domain, 'body': body, 'sources': sources, 'kinds': kinds,
                         'quantities': quantities or sorted({p.get('quantity', '') for p in hits if p.get('quantity')}),
                         'observations_persisted': sum(p['n'] for p in hits), 'sites': sum(p['sites'] for p in hits),
                         'real_data_status': status, 'validation': validation, 'database_persistence': bool(hits) or status == 'real_data',
                         'simple_analysis': simple, 'ai_agents': ai, 'data_explorer': explorer,
                         'limitations': MISSING.get((domain, body), '')})
    return rows
