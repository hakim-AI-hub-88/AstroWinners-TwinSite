import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import Request

from twinsite.api.server import App, Handler, ApiError
from twinsite.api import data
from twinsite.jobs.measured import resolve_request, evidence_for, load_pair, DATASET, source_root
from twinsite.jobs.worker import Worker
from twinsite.jobs.contract import digest, validate
from twinsite.science import ENGINE_VERSION
from twinsite.sources.credentials import earthdata_token
from twinsite.sources.fetch import _SafeRedirect
from twinsite.storage import load_settings

ROOT = Path(__file__).resolve().parents[3]
SELECTION = {'schema_version': '1.0', 'dataset_id': DATASET}

NEEDS_SOURCE_CACHE = unittest.skipUnless(
    (source_root() / "raw").is_dir() and (source_root() / "cleaned").is_dir(),
    "NASA source cache not provisioned (python ops/provision_source_cache.py, or set TWINSITE_SOURCE_DATA_DIR)")


class IntegrationTests(unittest.TestCase):
    @NEEDS_SOURCE_CACHE
    def test_measured_handler_worker_persistence_and_release_block(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = load_settings(directory)
            app = App(settings)
            h = Handler.__new__(Handler)
            h.app = app
            h.headers = {'Idempotency-Key': 'measured-integration'}
            h._read_json_body = lambda: json.dumps(SELECTION).encode()
            responses = []
            h.send_json = lambda *args: responses.append(args)
            h.route_submit_measured({})
            self.assertEqual(responses[-1][0], 202)
            run_id = responses[-1][1]['run_id']
            worker = Worker(settings)
            self.assertTrue(worker.run_once())
            run = app.store.get(run_id)
            self.assertEqual(run['status'], 'completed_with_limits', run['error'])
            committed = app.store.committed(run_id)
            result, evidence = map(json.loads, (committed['result'], committed['evidence']))
            self.assertEqual(result['algorithm_version'], ENGINE_VERSION)
            self.assertEqual(result['data_status'], 'measured')
            self.assertEqual(evidence['release_action'], 'BLOCK')
            self.assertIn('C5_INDEPENDENT_REVIEW_REQUIRED', evidence['blocking_issues'])
            self.assertEqual(result['input_sha256'], digest(resolve_request(SELECTION)))
            validate('mission_result', result)
            validate('release_evidence', evidence)
            self.assertEqual(len(evidence['observations']), 6)
            self.assertEqual(len(evidence['assets']), 5)
            self.assertTrue(result['sites'][0]['contributions'])
            self.assertIn('dry_fraction', ' '.join(result['sites'][0]['missing']))
            self.assertEqual(sorted({e['phase'] for e in app.store.events(run_id)}), ['P00','P10','P20','P30','P40','P50','P60','P70','P80','P90'])
            self.assertIn('Scientific release BLOCKED', committed['report'])
            self.assertEqual(App(settings).store.committed(run_id), committed)
            h.route_submit_measured({})
            self.assertEqual(responses[-1][1]['run_id'], run_id)
            out = ROOT / '.runtime/c0'
            out.mkdir(parents=True, exist_ok=True)
            (out / 'measured-result.json').write_text(committed['result'])
            (out / 'measured-evidence.json').write_text(committed['evidence'])
            (out / 'measured-request.json').write_text(json.dumps(resolve_request(SELECTION)))

    def test_measured_client_values_rejected(self):
        payload = resolve_request(SELECTION)
        payload['sites'][0]['observations']['slope_deg']['value'] += 1
        with self.assertRaises(ValueError): evidence_for(payload)
        with self.assertRaises(ValueError): resolve_request({**SELECTION, 'observations': {}})

    def test_synthetic_cannot_be_relabelled(self):
        payload = json.loads((ROOT / 'contracts/examples/mission.synthetic.json').read_text())
        payload['data_status'] = 'measured'
        with self.assertRaises(ValueError): evidence_for(payload)

    def test_source_bytes_required(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'TWINSITE_SOURCE_DATA_DIR': directory}):
            with self.assertRaisesRegex(ValueError, 'Source bytes'): evidence_for(resolve_request(SELECTION))

    def test_lineage_mutation_rejected(self):
        pair = load_pair()
        pair['observations'][0]['source_checksum'] = '0' * 64
        with patch('twinsite.jobs.measured.PAIR') as path:
            path.read_text.return_value = json.dumps(pair)
            with self.assertRaisesRegex(ValueError, 'lineage'): load_pair()

    def test_explorer_real_data_and_comparison(self):
        ids = [d['dataset_id'] for d in data.catalog()['items']]
        self.assertIn('moon-taurus-littrow', ids)   # Moon pair (LOLA + Diviner) is published too
        ids = ['earth-zagora-draa', 'mars-gale-aeolis']
        self.assertTrue(set(ids) <= set(d['dataset_id'] for d in data.catalog()['items']))
        left, right = [data.records(i, 'cleaned') for i in ids]
        request = {'schema_version':'1.0', 'left_dataset_id':ids[0], 'right_dataset_id':ids[1],
                   'left_record_ids':[r['record_id'] for r in left['rows']], 'right_record_ids':[r['record_id'] for r in right['rows']],
                   'columns':['feature_id','value','unit'], 'stage':'cleaned'}
        compared = data.compare(request)
        self.assertEqual(len(compared['rows']), 3)
        self.assertTrue(all(r['left']['unit'] == r['right']['unit'] for r in compared['rows']))
        request['columns'] = ['DROP TABLE']
        with self.assertRaises(ValueError): data.compare(request)

    def test_catalog_limit_is_validated_and_applied(self):
        h = Handler.__new__(Handler)
        responses = []
        h.send_json = lambda *args: responses.append(args)
        for invalid in ('0', '101', '-5', 'x'):
            with self.assertRaises(ApiError) as error:
                h.route_data_catalog({'limit': [invalid]})
            self.assertEqual(error.exception.status, 422)
        h.route_data_catalog({'limit': ['1']})
        self.assertEqual(len(responses[-1][1]['items']), 1)

    def test_secret_file_permissions_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / 'secret.env'
            path.write_text('EARTHDATA_TOKEN=test-only-placeholder\n')
            path.chmod(0o600)
            os.environ['TWINSITE_SECRET_ENV_FILE'] = str(path)
            self.assertEqual(earthdata_token(), 'test-only-placeholder')
            os.environ['EARTHDATA_TOKEN'] = 'environment-placeholder'
            self.assertEqual(earthdata_token(), 'environment-placeholder')
            del os.environ['EARTHDATA_TOKEN']
            path.chmod(0o644)
            with self.assertRaises(ValueError): earthdata_token()

    def test_redirect_removes_auth_and_refuses_downgrade(self):
        req = Request('https://data.lpdaac.earthdatacloud.nasa.gov/a', headers={'Authorization':'Bearer test-only-placeholder'})
        redirect = _SafeRedirect()
        new = redirect.redirect_request(req, None, 302, '', {}, 'https://other.example/a')
        self.assertIsNone(new.get_header('Authorization'))
        with self.assertRaises(Exception): redirect.redirect_request(req, None, 302, '', {}, 'http://other.example/a')

    def test_openapi_is_current(self):
        from twinsite.api.openapi import build_openapi
        self.assertEqual(json.loads((ROOT / 'backend/twinsite/api/openapi.json').read_text()), build_openapi())

    def test_aoi_extent_mismatch_blocks_release(self):
        from twinsite.jobs.measured import extent_mismatches
        pair = load_pair()
        issues = extent_mismatches(pair)
        self.assertEqual(len(issues), 1)
        self.assertTrue(issues[0].startswith('AOI_EXTENT_MISMATCH:3.33x'), issues)
        matched = copy.deepcopy(pair)
        for site in matched['sites']:
            site['provenance']['feature_details']['local_relief_m']['stats']['n'] = 100
        self.assertEqual(extent_mismatches(matched), [])
        del matched['sites'][1]['provenance']['feature_details']['local_relief_m']
        self.assertEqual(extent_mismatches(matched), ['AOI_EXTENT_UNVERIFIED'])

    @NEEDS_SOURCE_CACHE
    def test_grid_view_is_checksum_verified_and_labelled_display_only(self):
        mars = data.grid('mars-gale-aeolis')
        self.assertEqual((mars['display']['factor'], mars['display']['nrows'], mars['display']['ncols']), (1, 38, 38))
        self.assertIn('not the 1852.3 m analysis grid', mars['method'])
        self.assertTrue(any('datum' in c for c in mars['caveats']))
        site = next(s for s in load_pair()['sites'] if s['site_id'] == 'mars-gale-aeolis')
        key = site['provenance']['cleaned_object_key']
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'TWINSITE_SOURCE_DATA_DIR': tmp}):
                with self.assertRaises(KeyError):
                    data.grid('mars-gale-aeolis')
                target = Path(tmp) / key
                target.parent.mkdir(parents=True)
                target.write_bytes(b'{"tampered": true}')
                with self.assertRaises(data.SourceIntegrityError):
                    data.grid('mars-gale-aeolis')
        with self.assertRaises(KeyError):
            data.grid('unknown-site')

    def test_metadata_reports_metric_extent_and_distributions(self):
        earth, mars = data.metadata('earth-zagora-draa'), data.metadata('mars-gale-aeolis')
        self.assertAlmostEqual(earth['extent']['east_west_km'], 28.8, delta=0.2)
        self.assertAlmostEqual(mars['extent']['north_south_km'], 17.8, delta=0.2)
        self.assertEqual(mars['distributions']['slope_deg']['n'], 49)
        self.assertEqual(earth['distributions']['roughness_m']['mean'], 17.9224)

if __name__ == '__main__': unittest.main()
