"""C5 G2 independent provenance verifier. Deliberately does NOT call
contracts.validation.measured_release_issues — it re-derives everything from
raw bytes and naming conventions so C0's gate and C5's check are independent.

  python tests/acceptance/provenance_check.py --evidence ev.json --artifact-root <dir> \
      [--result result.json] [--repo <tree>] [--refetch] [--json out.json]

What it can prove offline:   bytes on disk match recorded SHA-256/size; URLs are
NASA/PDS hosts without credentials; product/granule names follow the real
product's naming scheme and body; units/scale are consistent; no synthetic
fixture material leaked into a measured run; one feature recomputed
independently from raw SRTM .hgt bytes when present.
What it CANNOT prove offline: that the bytes really came from NASA. Only
--refetch (re-download from source_url and compare SHA-256) proves that; an
Earthdata-protected URL needs the user's own ~/.netrc and is reported as such.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import struct
import sys
from urllib.parse import urlparse, parse_qs
import zipfile

# host suffix -> organisation. Anything else is not accepted as a NASA source.
HOSTS = {
    'nasa.gov': 'NASA',
    'earthdata.nasa.gov': 'NASA Earthdata',
    'earthdatacloud.nasa.gov': 'NASA Earthdata Cloud',
    'e4ftl01.cr.usgs.gov': 'NASA LP DAAC (USGS EROS)',
    'lpdaac.usgs.gov': 'NASA LP DAAC (USGS EROS)',
    'pds-geosciences.wustl.edu': 'NASA PDS Geosciences Node',
    'pds.nasa.gov': 'NASA PDS',
    'imbrium.mit.edu': 'LRO LOLA PDS data node (MIT)',
    'planetarymaps.usgs.gov': 'USGS Astrogeology (NASA PDS partner)',
    'astrogeology.usgs.gov': 'USGS Astrogeology (NASA PDS partner)',
}
CRED_QUERY = re.compile(r'(?i)^(token|access_token|sig|signature|x-amz-.*|x-goog-.*|key|apikey|api_key|password|auth)$')

# product family: (regex over product_id/granule/url basename, body, nominal resolution m (min,max))
PRODUCTS = [
    ('SRTMGL1', re.compile(r'(?i)\b[NS]\d{2}[EW]\d{3}\.SRTMGL1(\.hgt(\.zip)?)?\b|SRTMGL1'), 'Earth', (20, 40)),
    ('SRTMGL3', re.compile(r'(?i)\b[NS]\d{2}[EW]\d{3}\.SRTMGL3(\.hgt(\.zip)?)?\b|SRTMGL3'), 'Earth', (60, 120)),
    ('NASADEM', re.compile(r'(?i)NASADEM(_HGT)?(_[ns]\d{2}[ew]\d{3})?'), 'Earth', (20, 40)),
    ('MOD11A2', re.compile(r'(?i)MOD11A2(\.A\d{7}\.h\d{2}v\d{2}\.\d{3}\.\d{13}\.hdf)?'), 'Earth', (900, 1100)),
    ('POWER', re.compile(r'(?i)NASA[ _-]?POWER|power\.larc\.nasa\.gov'), 'Earth', (40000, 120000)),
    ('MOLA_MEGDR', re.compile(r'(?i)\bmeg[acrt]\d{2}[ns]\d{3}[a-z]{2}\.(img|lbl)\b|MOLA|MEGDR'), 'Mars', (100, 60000)),
    ('HRSC_MOLA', re.compile(r'(?i)HRSC.?MOLA|Mars_HRSC_MOLA_Blend'), 'Mars', (150, 250)),
    ('LOLA_LDEM', re.compile(r'(?i)\bS?LDEM[_0-9A-Z]*|\bLOLA\b'), 'Moon', (5, 60000)),
    ('DIVINER', re.compile(r'(?i)DIVINER|DLRE'), 'Moon', (100, 60000)),
]
UNIT_BY_SUFFIX = {'_deg': {'degree', 'deg', 'degrees'}, '_m': {'m', 'meter', 'metre', 'meters'},
                  '_k': {'K', 'kelvin'}, '_fraction': {'1', 'fraction', 'unitless'}}


class Report:
    def __init__(self):
        self.items = []

    def add(self, level, code, detail):
        self.items.append({'level': level, 'code': code, 'detail': detail})

    def fail(self, code, detail=''):
        self.add('FAIL', code, detail)

    def warn(self, code, detail=''):
        self.add('WARN', code, detail)

    def ok(self, code, detail=''):
        self.add('PASS', code, detail)

    @property
    def failed(self):
        return [i for i in self.items if i['level'] == 'FAIL']


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def classify(*names):
    hits = []
    for family, pattern, body, res in PRODUCTS:
        if any(pattern.search(n or '') for n in names):
            hits.append((family, body, res))
    return hits


def host_org(url):
    host = (urlparse(url).hostname or '').lower()
    for suffix, org in HOSTS.items():
        if host == suffix or host.endswith('.' + suffix):
            return org
    return None


def check_url(rep, where, url):
    u = urlparse(url or '')
    if u.scheme != 'https':
        rep.fail('NON_HTTPS_SOURCE', f'{where}: {url}')
    if u.username or u.password:
        rep.fail('CREDENTIAL_IN_URL', where)
    bad = [k for k in parse_qs(u.query) if CRED_QUERY.match(k)]
    if bad:
        rep.fail('CAPABILITY_OR_SIGNED_QUERY', f'{where}: {bad}')
    org = host_org(url)
    if not org:
        rep.fail('NON_NASA_HOST', f'{where}: {u.hostname}')
    return org


# --------------------------------------------------------------- SRTM decode
def load_hgt(path):
    """Return (n, data_bytes) for raw .hgt or a .hgt inside a zip. Big-endian int16, -32768 void."""
    raw = Path(path).read_bytes()
    if raw[:2] == b'PK':
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            names = [n for n in z.namelist() if n.lower().endswith('.hgt')]
            if len(names) != 1:
                raise ValueError('zip does not contain exactly one .hgt')
            raw = z.read(names[0])
    n = int(math.isqrt(len(raw) // 2))
    if n * n * 2 != len(raw) or n not in (1201, 3601):
        raise ValueError(f'not an SRTM HGT grid ({len(raw)} bytes)')
    return n, raw


def tile_origin(name):
    m = re.search(r'(?i)([NS])(\d{2})([EW])(\d{3})', name)
    if not m:
        raise ValueError('cannot infer SRTM tile origin from ' + name)
    lat = int(m.group(2)) * (1 if m.group(1).upper() == 'N' else -1)
    lon = int(m.group(4)) * (1 if m.group(3).upper() == 'E' else -1)
    return lat, lon  # SW corner


def hgt_window(n, raw, lat0, lon0, bbox):
    """Pixel-centre selection inside bbox [minlon,minlat,maxlon,maxlat]. Row 0 = north edge (lat0+1)."""
    step = 1.0 / (n - 1)
    minlon, minlat, maxlon, maxlat = bbox
    rows = [r for r in range(n) if minlat <= lat0 + 1 - r * step <= maxlat]
    cols = [c for c in range(n) if minlon <= lon0 + c * step <= maxlon]
    grid = []
    for r in rows:
        row = []
        for c in cols:
            v = struct.unpack_from('>h', raw, 2 * (r * n + c))[0]
            row.append(None if v == -32768 else float(v))
        grid.append(row)
    lat_c = lat0 + 1 - ((rows[0] + rows[-1]) / 2) * step if rows else lat0
    return grid, step, lat_c


def independent_stats(grid, step_deg, lat_c):
    vals = [v for row in grid for v in row if v is not None]
    total = sum(len(r) for r in grid)
    out = {'valid_fraction': (len(vals) / total) if total else 0.0}
    if vals:
        out['elevation_mean_m'] = sum(vals) / len(vals)
        out['elevation_min_m'] = min(vals)
        out['elevation_max_m'] = max(vals)
        out['relief_m'] = max(vals) - min(vals)
    # Slope by central differences on a local metric grid (spherical Earth, R=6371008.8 m).
    R = 6371008.8
    dy = math.radians(step_deg) * R
    dx = dy * math.cos(math.radians(lat_c))
    slopes = []
    for i in range(1, len(grid) - 1):
        for j in range(1, len(grid[i]) - 1):
            a, b, c, d = grid[i][j - 1], grid[i][j + 1], grid[i - 1][j], grid[i + 1][j]
            if None in (a, b, c, d):
                continue
            gx, gy = (b - a) / (2 * dx), (c - d) / (2 * dy)
            slopes.append(math.degrees(math.atan(math.hypot(gx, gy))))
    if slopes:
        out['slope_mean_deg'] = sum(slopes) / len(slopes)
    return out


def match_stat(feature_id, stats):
    f = feature_id.lower()
    if 'slope' in f and 'slope_mean_deg' in stats:
        return 'slope_mean_deg', 1.0, 0.10      # abs deg, rel — method differences (Horn vs central diff)
    if ('relief' in f or 'range' in f) and 'relief_m' in stats:
        return 'relief_m', 2.0, 0.02
    if 'elev' in f and 'elevation_mean_m' in stats:
        return 'elevation_mean_m', 1.0, 0.005
    return None


# --------------------------------------------------------------- main check
def check(evidence, artifact_root, result=None, repo=None, refetch=False):
    rep = Report()
    root = Path(artifact_root).resolve() if artifact_root else None
    measured_claim = evidence.get('data_status') == 'measured'
    if not measured_claim:
        rep.fail('NOT_MEASURED', f'evidence data_status={evidence.get("data_status")!r}; nothing here is NASA evidence')
    if evidence.get('release_action') in ('RELEASE', 'QUALIFIED_RELEASE') and evidence.get('data_status') != 'measured':
        rep.fail('SYNTHETIC_RELEASED', 'non-measured evidence carries a release action')
    if re.search(r'(?i)synthetic|fixture|demo|mock|fake|sample', evidence.get('source_snapshot_id', '')):
        rep.fail('SNAPSHOT_LOOKS_SYNTHETIC', evidence.get('source_snapshot_id'))

    assets = evidence.get('assets', [])
    if not assets:
        rep.fail('NO_ASSETS', 'no raw source assets recorded')
    by_id = {}
    bodies = set()
    for a in assets:
        aid = a.get('asset_id')
        if aid in by_id:
            rep.fail('DUPLICATE_ASSET', aid)
        by_id[aid] = a
        org = check_url(rep, f'asset {aid}', a.get('source_url'))
        fams = classify(a.get('product_id'), Path(urlparse(a.get('source_url', '')).path).name, a.get('object_key'))
        if not fams:
            rep.fail('UNKNOWN_PRODUCT_NAMING', f'{aid}: product_id={a.get("product_id")!r}')
        elif all(body != a.get('body') for _, body, _ in fams):
            rep.fail('BODY_PRODUCT_MISMATCH', f'{aid}: {a.get("body")} vs {[f for f, _, _ in fams]}')
        else:
            rep.ok('PRODUCT_NAMING', f'{aid}: {fams[0][0]} on {a.get("body")} via {org}')
        bodies.add(a.get('body'))
        if not a.get('crs'):
            rep.fail('MISSING_CRS', aid)
        try:
            s, e = (datetime.fromisoformat(a[k].replace('Z', '+00:00')) for k in ('observation_start', 'observation_end'))
            r = datetime.fromisoformat(a['retrieved_at'].replace('Z', '+00:00'))
            if s > e:
                rep.fail('OBSERVATION_PERIOD_INVERTED', aid)
            if r > datetime.now(timezone.utc):
                rep.fail('RETRIEVED_IN_FUTURE', aid)
        except (KeyError, ValueError, TypeError) as err:
            rep.fail('BAD_TIMESTAMPS', f'{aid}: {err}')
        # Raw bytes: recompute independently.
        if root is None:
            rep.fail('NO_ARTIFACT_ROOT', aid)
            continue
        path = (root / a.get('object_key', '')).resolve()
        if not path.is_relative_to(root):
            rep.fail('OBJECT_KEY_ESCAPES_ROOT', aid)
            continue
        if not path.is_file():
            rep.fail('RAW_BYTES_MISSING', f'{aid}: {a.get("object_key")}')
            continue
        data = path.read_bytes()
        if sha256_bytes(data) != a.get('sha256'):
            rep.fail('RAW_SHA256_MISMATCH', aid)
        elif len(data) != a.get('byte_size'):
            rep.fail('RAW_SIZE_MISMATCH', aid)
        else:
            rep.ok('RAW_CHECKSUM', f'{aid}: sha256 {a["sha256"][:12]}… {len(data)} bytes')
        if refetch:
            refetch_asset(rep, a)
    if measured_claim and not ({'Earth'} & bodies and {'Moon', 'Mars'} & bodies):
        rep.fail('NO_EARTH_PLANETARY_PAIR', f'bodies with raw assets: {sorted(b for b in bodies if b)}')

    # Observations
    observations = evidence.get('observations', [])
    obs_by_id = {}
    scale_by_feature = {}
    for o in observations:
        eid = o.get('evidence_id')
        if eid in obs_by_id:
            rep.fail('DUPLICATE_EVIDENCE_ID', eid)
        obs_by_id[eid] = o
        if o.get('data_status') != 'measured' or o.get('evidence_kind') not in ('direct_measurement', 'derived_measurement'):
            if eid in evidence.get('required_evidence_ids', []):
                rep.fail('REQUIRED_NOT_MEASURED', f'{eid}: {o.get("evidence_kind")}/{o.get("data_status")}')
            continue
        v = o.get('value')
        if v is None or not isinstance(v, (int, float)) or not math.isfinite(v):
            rep.fail('MEASURED_VALUE_INVALID', f'{eid}: {v!r}')
        srcs = [by_id.get(x) for x in o.get('source_asset_ids', [])]
        if not srcs or None in srcs:
            rep.fail('ORPHAN_OBSERVATION', eid)
            continue
        if o.get('source_checksum') not in {s['sha256'] for s in srcs}:
            rep.fail('OBS_CHECKSUM_NOT_A_SOURCE', eid)
        if o.get('body') not in {s['body'] for s in srcs}:
            rep.fail('OBS_BODY_NOT_SOURCE_BODY', eid)
        gran = o.get('source_granule_id') or ''
        if not gran or not any(gran in (s.get('source_url', '') + ' ' + s.get('object_key', '') + ' ' + s.get('product_id', ''))
                               for s in srcs):
            rep.fail('GRANULE_ID_NOT_TRACEABLE', f'{eid}: {gran!r} not in any source URL/object key')
        check_url(rep, f'observation {eid}', o.get('source_url'))
        unit = o.get('unit')
        for suffix, units in UNIT_BY_SUFFIX.items():
            if o.get('feature_id', '').lower().endswith(suffix) and unit not in units:
                rep.fail('UNIT_FEATURE_MISMATCH', f'{eid}: {o.get("feature_id")} in {unit!r}')
        res, scale = o.get('spatial_resolution_m'), o.get('analysis_scale_m')
        if res is None or scale is None:
            rep.fail('MISSING_SPATIAL_SUPPORT', eid)
        else:
            if scale + 1e-9 < res:
                rep.fail('ANALYSIS_FINER_THAN_SOURCE', f'{eid}: scale {scale} m < resolution {res} m')
            fams = classify(*(s.get('product_id') for s in srcs))
            if fams:
                lo, hi = fams[0][2]
                if not (lo <= res <= hi):
                    rep.warn('RESOLUTION_ATYPICAL_FOR_PRODUCT', f'{eid}: {res} m for {fams[0][0]} (expected {lo}-{hi})')
            scale_by_feature.setdefault(o.get('feature_id'), {}).setdefault(o.get('body'), set()).add(round(scale, 3))
        g = o.get('geometry') or {}
        if not g.get('crs'):
            rep.fail('OBS_GEOMETRY_NO_CRS', eid)
        independent_recompute(rep, o, srcs, root)
    for feature, per_body in scale_by_feature.items():
        scales = set().union(*per_body.values())
        if len(per_body) > 1 and len(scales) > 1:
            rep.fail('NO_COMMON_ANALYSIS_SCALE', f'{feature}: {dict((b, sorted(s)) for b, s in per_body.items())}')
        elif len(per_body) > 1:
            rep.ok('COMMON_ANALYSIS_SCALE', f'{feature}: {sorted(scales)} m across {sorted(per_body)}')
    for rid in evidence.get('required_evidence_ids', []):
        if rid not in obs_by_id:
            rep.fail('REQUIRED_EVIDENCE_ABSENT', rid)

    # Result lineage (independent re-derivation)
    if result is not None:
        if result.get('data_status') != evidence.get('data_status'):
            rep.fail('RESULT_EVIDENCE_STATUS_DISAGREE', f'{result.get("data_status")} vs {evidence.get("data_status")}')
        for site in result.get('sites', []):
            for feat, c in (site.get('contributions') or {}).items():
                for key, vkey in (('source_id', 'value'), ('target_source_id', 'target_value')):
                    o = obs_by_id.get(c.get(key))
                    if o is None:
                        rep.fail('CONTRIBUTION_UNRESOLVED', f'{site.get("id")}/{feat}: {key}={c.get(key)!r}')
                    elif o.get('value') != c.get(vkey) or o.get('unit') != c.get('unit'):
                        rep.fail('CONTRIBUTION_VALUE_DRIFT', f'{site.get("id")}/{feat}: {c.get(vkey)} {c.get("unit")} vs '
                                                            f'evidence {o.get("value")} {o.get("unit")}')
    fixture_leakage(rep, evidence, result, repo)
    return rep


def independent_recompute(rep, o, srcs, root):
    if root is None:
        return
    hgt = [s for s in srcs if re.search(r'(?i)SRTMGL[13]|NASADEM', s.get('product_id', '')) and s.get('body') == 'Earth']
    if not hgt:
        rep.add('BLOCKED', 'INDEPENDENT_RECOMPUTE_UNSUPPORTED',
                f'{o["evidence_id"]}: no independent decoder for {[s.get("product_id") for s in srcs]} (awaiting C1 format notes)')
        return
    s = hgt[0]
    try:
        n, raw = load_hgt(root / s['object_key'])
        lat0, lon0 = tile_origin(Path(s['object_key']).name + ' ' + s.get('source_url', ''))
        bbox = o['geometry']['coordinates']
        grid, step, lat_c = hgt_window(n, raw, lat0, lon0, bbox)
        stats = independent_stats(grid, step, lat_c)
    except Exception as err:
        rep.fail('INDEPENDENT_DECODE_FAILED', f'{o["evidence_id"]}: {err}')
        return
    m = match_stat(o.get('feature_id', ''), stats)
    if not m:
        rep.add('BLOCKED', 'INDEPENDENT_RECOMPUTE_NO_MATCHING_STAT',
                f'{o["evidence_id"]} feature {o.get("feature_id")}; independent stats {json.dumps({k: round(v, 3) for k, v in stats.items()})}')
        return
    stat, abs_tol, rel_tol = m
    mine, theirs = stats[stat], o['value']
    note = f'{o["evidence_id"]}: C1={theirs} C5={mine:.3f} ({stat}, n-valid={stats["valid_fraction"]:.3f})'
    if abs(mine - theirs) <= max(abs_tol, rel_tol * abs(mine)):
        rep.ok('INDEPENDENT_RECOMPUTE_AGREES', note)
    else:
        rep.fail('INDEPENDENT_RECOMPUTE_DISAGREES', note + f' tol=max({abs_tol},{rel_tol:.0%})')


def fixture_leakage(rep, evidence, result, repo):
    if evidence.get('data_status') != 'measured':
        return
    texts = json.dumps([evidence, result])
    for token in ('synthetic-', 'run-fixture', 'synthetic_fixture', 'Synthetic terrain', 'synthetic-fixture-v1'):
        if token in texts:
            rep.fail('SYNTHETIC_TOKEN_IN_MEASURED_RUN', token)
    if not repo:
        return
    ex = Path(repo) / 'contracts/examples'
    fixture_sites = []
    for p in sorted(ex.glob('*synthetic*.json')):
        d = json.loads(p.read_text())
        for s in d.get('sites', []) + [t.get('location', {}) | {'observations': t.get('observations', {})} for t in d.get('target_profiles', [])]:
            obs = {f: v.get('value') for f, v in (s.get('observations') or {}).items() if isinstance(v, dict)}
            if obs:
                fixture_sites.append((p.name, s.get('id'), obs))
    measured = {}
    for o in evidence.get('observations', []):
        if o.get('value') is not None:
            measured.setdefault(o.get('site_id'), {})[o.get('feature_id')] = o.get('value')
    for site_id, vals in measured.items():
        for fname, fid, fobs in fixture_sites:
            same = [f for f in vals if f in fobs and fobs[f] == vals[f]]
            if len(same) >= 2:
                rep.fail('FIXTURE_VALUES_IN_MEASURED_RUN', f'site {site_id} matches {fname}:{fid} on {same}')


def refetch_asset(rep, a):
    from urllib.request import Request, urlopen
    from urllib.error import HTTPError, URLError
    url = a['source_url']
    try:
        with urlopen(Request(url, headers={'User-Agent': 'twinsite-qa-provenance/1.0'}), timeout=60) as resp:
            h = hashlib.sha256()
            final = resp.geturl()
            if 'urs.earthdata.nasa.gov' in final:
                rep.add('BLOCKED', 'REFETCH_NEEDS_EARTHDATA_AUTH', f'{a["asset_id"]}: redirected to Earthdata login')
                return
            for chunk in iter(lambda: resp.read(1 << 20), b''):
                h.update(chunk)
        if h.hexdigest() == a['sha256']:
            rep.ok('REFETCH_MATCHES_NASA', f'{a["asset_id"]}: re-downloaded bytes match recorded SHA-256')
        else:
            rep.fail('REFETCH_MISMATCH', f'{a["asset_id"]}: source now serves different bytes')
    except HTTPError as e:
        level = 'BLOCKED' if e.code in (401, 403) else 'FAIL'
        rep.add(level, 'REFETCH_HTTP_' + str(e.code), a['asset_id'])
    except (URLError, OSError) as e:
        rep.add('BLOCKED', 'REFETCH_NETWORK', f'{a["asset_id"]}: {e}')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--evidence', required=True)
    ap.add_argument('--artifact-root')
    ap.add_argument('--result')
    ap.add_argument('--repo', default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument('--refetch', action='store_true')
    ap.add_argument('--json')
    args = ap.parse_args()
    ev = json.loads(Path(args.evidence).read_text())
    res = json.loads(Path(args.result).read_text()) if args.result else None
    rep = check(ev, args.artifact_root, res, args.repo, args.refetch)
    for i in rep.items:
        print(f'{i["level"]:8} {i["code"]}' + (f' — {i["detail"]}' if i['detail'] else ''))
    verified = any(i['code'] == 'REFETCH_MATCHES_NASA' for i in rep.items)
    print(f'\nG2 provenance: {len(rep.failed)} FAIL; NASA-origin of bytes '
          f'{"VERIFIED by re-download" if verified else "NOT VERIFIED (run --refetch)"}')
    if args.json:
        Path(args.json).write_text(json.dumps({'items': rep.items, 'nasa_bytes_verified': verified}, indent=2) + '\n')
    return 1 if rep.failed else 0


if __name__ == '__main__':
    sys.exit(main())
