"""Self-tests for the C5 G2 provenance checker.

The positive control below is a CONSTRUCTED, NON-NASA raster written to a temp
dir. It proves the checker's arithmetic and consistency logic only; it must
never be copied into an artifact root, and the checker must still report
NASA origin as NOT verified for it (no --refetch).
"""
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import provenance_check as pc  # noqa: E402


def constructed_hgt(path, n=1201, base=1000.0, dzdx_per_px=2.0):
    """Plane z = base + dzdx * col (metres). NOT NASA DATA."""
    rows = []
    for _ in range(n):
        rows.append(struct.pack('>' + 'h' * n, *[int(base + dzdx_per_px * c) for c in range(n)]))
    path.write_bytes(b''.join(rows))
    return path.read_bytes()


def constructed_evidence(root):
    (root / 'raw').mkdir()
    data = constructed_hgt(root / 'raw' / 'N33W117.SRTMGL3.hgt')
    sha = hashlib.sha256(data).hexdigest()
    asset_e = {
        'schema_version': '1.0', 'asset_id': 'a-earth', 'source_id': 'srtm', 'product_id': 'SRTMGL3',
        'product_version': '003', 'body': 'Earth',
        'source_url': 'https://e4ftl01.cr.usgs.gov/MEASURES/SRTMGL3.003/2000.02.11/N33W117.SRTMGL3.hgt.zip',
        'object_key': 'raw/N33W117.SRTMGL3.hgt', 'sha256': sha, 'retrieved_at': '2026-11-15T01:00:00Z',
        'observation_start': '2000-02-11T00:00:00Z', 'observation_end': '2000-02-22T00:00:00Z', 'format': 'HGT',
        'crs': 'EPSG:4326', 'coordinate_conventions': 'pixel-is-point', 'license_url': 'https://lpdaac.usgs.gov/',
        'byte_size': len(data), 'adapter_version': 'test', 'parent_asset_ids': []}
    mars = b'CONSTRUCTED NOT NASA'
    (root / 'raw' / 'megt44n000hb.img').write_bytes(mars)
    asset_m = dict(asset_e, asset_id='a-mars', source_id='mola', product_id='MOLA_MEGDR megt44n000hb', body='Mars',
                   source_url='https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt44n000hb.img',
                   object_key='raw/megt44n000hb.img', sha256=hashlib.sha256(mars).hexdigest(), byte_size=len(mars),
                   crs='Mars2000 planetocentric', format='PDS3 IMG')
    # Window 33.2-33.3N, 116.8-116.7W; 3 arc-second pixels ~ 92.6 m E-W at equator.
    obs = {
        'schema_version': '1.0', 'evidence_id': 'e-earth-slope', 'feature_id': 'slope_deg', 'site_id': 'A', 'body': 'Earth',
        'geometry': {'type': 'bbox', 'coordinates': [-116.8, 33.2, -116.7, 33.3], 'crs': 'EPSG:4326'},
        'value': None, 'unit': 'degree', 'source_product': 'SRTMGL3', 'source_granule_id': 'N33W117.SRTMGL3',
        'source_url': asset_e['source_url'], 'source_checksum': sha, 'source_asset_ids': ['a-earth'],
        'observation_period': {'start': '2000-02-11T00:00:00Z', 'end': '2000-02-22T00:00:00Z'},
        'spatial_resolution_m': 90, 'analysis_scale_m': 500, 'quality_flags': [], 'valid_coverage_fraction': 1.0,
        'uncertainty': {'kind': 'unknown', 'low': None, 'high': None, 'standard_deviation': None, 'basis': 'test'},
        'processing_version': 'test', 'provenance_id': 'p1', 'evidence_kind': 'derived_measurement',
        'data_status': 'measured', 'missing_reason': None, 'qa_status': 'ACCEPT'}
    n, raw = pc.load_hgt(root / 'raw/N33W117.SRTMGL3.hgt')
    grid, step, lat_c = pc.hgt_window(n, raw, 33, -117, obs['geometry']['coordinates'])
    obs['value'] = round(pc.independent_stats(grid, step, lat_c)['slope_mean_deg'], 4)
    obs_m = dict(obs, evidence_id='e-mars-slope', site_id='target', body='Mars', source_product='MOLA_MEGDR',
                 source_granule_id='megt44n000hb', source_url=asset_m['source_url'], source_checksum=asset_m['sha256'],
                 source_asset_ids=['a-mars'], spatial_resolution_m=463, analysis_scale_m=500, value=1.0,
                 geometry={'type': 'bbox', 'coordinates': [137.3, -4.7, 137.5, -4.5], 'crs': 'Mars2000'})
    return {
        'schema_version': '1.0', 'run_id': 'r', 'input_sha256': '0' * 64, 'source_snapshot_id': 'snap-2026-11-15',
        'source_snapshot_sha256': '0' * 64, 'qa_gate_id': 'g', 'qa_gate_version': '1', 'data_status': 'measured',
        'strict_gate_status': 'PASS', 'release_action': 'QUALIFIED_RELEASE', 'weights_version': 'w',
        'evidence_coverage': 1.0, 'required_evidence_ids': ['e-earth-slope', 'e-mars-slope'],
        'assets': [asset_e, asset_m], 'observations': [obs, obs_m], 'rejected_candidates': [], 'assumptions': [],
        'unknowns': [], 'blocking_issues': [], 'review_ids': ['rv']}


def codes(rep, level='FAIL'):
    return {i['code'] for i in rep.items if i['level'] == level}


class ProvenanceSelfTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='c5-prov-')
        self.root = Path(self.tmp.name)
        self.ev = constructed_evidence(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_every_synthetic_example_is_rejected(self):
        ex = REPO / 'contracts/examples/release_evidence.synthetic.json'
        rep = pc.check(json.loads(ex.read_text()), self.root, repo=REPO)
        self.assertIn('NOT_MEASURED', codes(rep))
        self.assertIn('NO_ASSETS', codes(rep))
        self.assertIn('SNAPSHOT_LOOKS_SYNTHETIC', codes(rep))

    def test_relabelled_synthetic_is_rejected(self):
        ev = json.loads((REPO / 'contracts/examples/release_evidence.synthetic.json').read_text())
        ev['data_status'] = 'measured'
        ev['release_action'] = 'RELEASE'
        self.assertTrue(pc.check(ev, self.root, repo=REPO).failed)

    def test_constructed_control_consistent_but_not_nasa_verified(self):
        rep = pc.check(self.ev, self.root, repo=REPO)
        self.assertEqual(rep.failed, [], rep.failed)
        self.assertIn('INDEPENDENT_RECOMPUTE_AGREES', codes(rep, 'PASS'))
        self.assertNotIn('REFETCH_MATCHES_NASA', codes(rep, 'PASS'))

    def test_independent_slope_is_physically_right(self):
        # Plane rising 2 m per 3" column: dx ~ 92.66 m * cos(33.25 deg) ~ 77.5 m -> atan(2/77.5) ~ 1.48 deg.
        v = self.ev['observations'][0]['value']
        self.assertAlmostEqual(v, 1.478, delta=0.03)

    def test_mutated_bytes(self):
        p = self.root / 'raw/N33W117.SRTMGL3.hgt'
        b = bytearray(p.read_bytes()); b[100] ^= 1; p.write_bytes(bytes(b))
        self.assertIn('RAW_SHA256_MISMATCH', codes(pc.check(self.ev, self.root, repo=REPO)))

    def test_wrong_value_disagrees(self):
        ev = copy.deepcopy(self.ev); ev['observations'][0]['value'] += 5
        self.assertIn('INDEPENDENT_RECOMPUTE_DISAGREES', codes(pc.check(ev, self.root, repo=REPO)))

    def test_non_nasa_host_and_signed_url(self):
        ev = copy.deepcopy(self.ev)
        ev['assets'][1]['source_url'] = 'https://example.com/megt44n000hb.img?X-Amz-Signature=abc'
        c = codes(pc.check(ev, self.root, repo=REPO))
        self.assertIn('NON_NASA_HOST', c)
        self.assertIn('CAPABILITY_OR_SIGNED_QUERY', c)

    def test_body_product_mismatch(self):
        ev = copy.deepcopy(self.ev); ev['assets'][1]['body'] = 'Moon'
        self.assertIn('BODY_PRODUCT_MISMATCH', codes(pc.check(ev, self.root, repo=REPO)))

    def test_no_common_scale(self):
        ev = copy.deepcopy(self.ev); ev['observations'][1]['analysis_scale_m'] = 1000
        self.assertIn('NO_COMMON_ANALYSIS_SCALE', codes(pc.check(ev, self.root, repo=REPO)))

    def test_unit_mismatch(self):
        ev = copy.deepcopy(self.ev); ev['observations'][0]['unit'] = 'percent'
        self.assertIn('UNIT_FEATURE_MISMATCH', codes(pc.check(ev, self.root, repo=REPO)))

    def test_granule_not_traceable(self):
        ev = copy.deepcopy(self.ev); ev['observations'][0]['source_granule_id'] = 'N01E001.SRTMGL3'
        self.assertIn('GRANULE_ID_NOT_TRACEABLE', codes(pc.check(ev, self.root, repo=REPO)))

    def test_fixture_tokens_and_values_leak(self):
        ev = copy.deepcopy(self.ev)
        ev['observations'][0]['provenance_id'] = 'synthetic-A-slope_deg'
        self.assertIn('SYNTHETIC_TOKEN_IN_MEASURED_RUN', codes(pc.check(ev, self.root, repo=REPO)))
        ev = copy.deepcopy(self.ev)
        extra = copy.deepcopy(ev['observations'][0]); extra.update(evidence_id='x2', feature_id='roughness_m', unit='m', value=7)
        ev['observations'][0]['value'] = 12; ev['observations'].append(extra)
        self.assertIn('FIXTURE_VALUES_IN_MEASURED_RUN', codes(pc.check(ev, self.root, repo=REPO)))

    def test_earth_only_is_not_a_pair(self):
        ev = copy.deepcopy(self.ev); ev['assets'] = ev['assets'][:1]; ev['observations'] = ev['observations'][:1]
        ev['required_evidence_ids'] = ['e-earth-slope']
        self.assertIn('NO_EARTH_PLANETARY_PAIR', codes(pc.check(ev, self.root, repo=REPO)))

    def test_object_key_escape(self):
        ev = copy.deepcopy(self.ev); ev['assets'][1]['object_key'] = '../../etc/passwd'
        self.assertIn('OBJECT_KEY_ESCAPES_ROOT', codes(pc.check(ev, self.root, repo=REPO)))


if __name__ == '__main__':
    unittest.main()
