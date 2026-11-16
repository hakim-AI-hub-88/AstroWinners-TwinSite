import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation'))
from contracts.validation import digest, measured_release_issues, require_finite, validate
from ares.engine import analyze
from ares.store import Store
from ares.__main__ import work_once
from ares.report import render_report


class CompatibilityTests(unittest.TestCase):
    def test_legacy_schemas_unchanged(self):
        for name in ('mission_request','mission_result','production'):
            self.assertEqual((ROOT/f'contracts/legacy/{name}.schema.json').read_bytes(),(ROOT/f'contracts/v1/{name}.schema.json').read_bytes())

    def test_reference_snapshots_pinned(self):
        for item in json.loads((ROOT/'references/SNAPSHOT.json').read_text())['packages']:
            self.assertEqual(hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest(),item['sha256'])

    def test_all_four_reference_results_reproduce(self):
        for name in ('mission','moon_mission','three_body_mission','zone_mission'):
            request=json.loads((ROOT/f'contracts/examples/{name}.synthetic.json').read_text())
            result=json.loads((ROOT/f'contracts/examples/{name}.result.synthetic.json').read_text())
            with self.subTest(name=name):
                self.assertEqual(analyze(request),result)
                self.assertEqual(result['data_status'],'synthetic')

    def test_required_missing_feature_cannot_stay_eligible(self):
        request=json.loads((ROOT/'contracts/examples/mission.synthetic.json').read_text())
        feature=next(iter(request['mission']['features']))
        request['mission']['features'][feature]['required']=True
        for site in request['sites']:
            site['observations'][feature]['value']=None
            site['observations'][feature]['missing_reason']='Negative-control removed measurement'
        result=analyze(request)
        self.assertFalse(any(s['eligible'] for s in result['sites']))
        self.assertEqual(result['portfolios'],[])

    def test_non_finite_numbers_rejected(self):
        for value in (float('nan'),float('inf'),float('-inf')):
            with self.assertRaises(ValueError): require_finite({'nested':[value]})

    def test_persisted_worker_result_and_report_offline(self):
        with tempfile.TemporaryDirectory(prefix='twinsite-worker-test-') as folder:
            store=Store(Path(folder)/'jobs.sqlite')
            request=json.loads((ROOT/'contracts/examples/mission.synthetic.json').read_text())
            run_id=store.submit(request,'test-idempotency')
            self.assertEqual(store.get(run_id)['state'],'queued')
            self.assertTrue(work_once(store))
            job=store.get(run_id)
            self.assertEqual(job['state'],'succeeded')
            self.assertEqual(job['result'],json.loads((ROOT/'contracts/examples/mission.result.synthetic.json').read_text()))
            self.assertIn('synthetic',render_report(job['result']).lower())
            events=store.events(run_id)
            self.assertEqual(store.events(run_id,events[-1]['sequence']),[])
            self.assertFalse(work_once(store))

    def test_types_not_stale(self):
        subprocess.run([sys.executable,'scripts/integration/generate_types.py','--check'],cwd=ROOT,check=True,capture_output=True)


class ReleaseGateTests(unittest.TestCase):
    """Fabricated unit-test bytes exercise logic; they are NOT NASA evidence."""
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='twinsite-gate-test-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.request=json.loads((ROOT/'contracts/examples/mission.synthetic.json').read_text())
        # Explicitly constructed unit fixture for the measured-branch guard.
        self.request['data_status']='measured'
        self.observations=[]
        self.assets=[]
        for body in ('Earth','Mars'):
            raw=('UNIT TEST ONLY '+body).encode();(self.root/body).write_bytes(raw)
            self.assets.append({'asset_id':body,'sha256':hashlib.sha256(raw).hexdigest(),'object_key':body,'byte_size':len(raw),'source_url':'https://example.invalid/'+body,'product_id':'UNIT_TEST_ONLY','body':body})
        for site in self.request['sites']:
            self.add_observations(site['id'],site['body'],site['observations'])
        for profile in self.request['target_profiles']:
            self.add_observations(profile['location']['id'],profile['body'],profile['observations'])
        self.result=analyze(self.request)
        self.manifest={'data_status':'measured','strict_gate_status':'PASS','release_action':'RELEASE','blocking_issues':[],'review_ids':['UNIT_TEST_REVIEW'],'input_sha256':digest(self.request),'assets':self.assets,'source_snapshot_sha256':digest(sorted([{'asset_id':a['asset_id'],'sha256':a['sha256']} for a in self.assets],key=lambda a:a['asset_id'])),'observations':self.observations,'required_evidence_ids':[o['evidence_id'] for o in self.observations]}

    def add_observations(self,site_id,body,values):
        asset=next(a for a in self.assets if a['body']==body)
        for feature,value in values.items():
            eid=site_id+'/'+feature;value['source_id']=eid
            if value['value'] is None or value['value']==value.get('missing_sentinel'):
                continue
            self.observations.append({'evidence_id':eid,'site_id':site_id,'body':body,'feature_id':feature,'value':value['value'],'unit':value['unit'],'data_status':'measured','evidence_kind':'derived_measurement','qa_status':'ACCEPT','valid_coverage_fraction':1,'spatial_resolution_m':100,'analysis_scale_m':1000,'source_asset_ids':[body],'source_checksum':asset['sha256'],'source_url':asset['source_url'],'source_product':asset['product_id']})

    def issues(self):
        return measured_release_issues(self.request,self.result,self.manifest,self.root)

    def test_constructed_semantic_control(self):
        self.assertEqual(self.issues(),[])

    def test_synthetic_cannot_release(self):
        self.manifest['data_status']='synthetic'
        self.assertIn('SYNTHETIC_OR_UNVERIFIED_DATA',self.issues())

    def test_null_required_value_blocks(self):
        self.observations[0]['value']=None
        self.assertTrue(any(i.startswith('MISSING_REQUIRED_MEASUREMENT') for i in self.issues()))

    def test_removed_evidence_and_required_list_cannot_bypass(self):
        feature=next(iter(self.request['mission']['features']))
        self.request['mission']['features'][feature]['required']=True
        self.result['input_sha256']=digest(self.request);self.manifest['input_sha256']=digest(self.request)
        target=self.request['target_profiles'][0]['observations'][feature]['source_id']
        self.manifest['observations']=[o for o in self.observations if o['evidence_id']!=target]
        self.manifest['required_evidence_ids'].remove(target)
        self.assertTrue(any(i.startswith('REQUIRED_FEATURE_NOT_ATTESTED') for i in self.issues()))

    def test_mutated_bytes_block(self):
        (self.root/'Earth').write_bytes(b'mutated')
        self.assertIn('SOURCE_BYTES_MISMATCH:Earth',self.issues())

    def test_quarantined_evidence_blocks(self):
        self.observations[0]['qa_status']='QUARANTINE'
        self.assertTrue(any(i.startswith('UNACCEPTED_EVIDENCE') for i in self.issues()))

    def test_user_assumption_cannot_be_measurement(self):
        self.observations[0]['evidence_kind']='user_assumption'
        self.assertTrue(any(i.startswith('NON_MEASUREMENT_EVIDENCE') for i in self.issues()))

    def test_source_path_escape_blocks(self):
        self.assets[0]['object_key']='../outside'
        self.assertIn('MISSING_SOURCE_BYTES:Earth',self.issues())

    def test_inconsistent_contribution_blocks(self):
        site=next(s for s in self.result['sites'] if s['contributions'])
        next(iter(site['contributions'].values()))['value']+=1
        self.assertTrue(any(i.startswith('CONTRIBUTION_EVIDENCE_MISMATCH') for i in self.issues()))

    def test_duplicate_evidence_blocks(self):
        self.observations.append(copy.deepcopy(self.observations[0]))
        self.assertIn('DUPLICATE_EVIDENCE_ID',self.issues())


@unittest.skipUnless(importlib.util.find_spec('jsonschema'), 'BLOCKED: jsonschema dependency unavailable; not a schema pass')
class SchemaTests(unittest.TestCase):
    def test_examples_validate(self):
        index=json.loads((ROOT/'contracts/examples/index.json').read_text())
        for entry in index['examples']:
            with self.subTest(file=entry['file']):
                validate(Path(entry['schema']).name.removesuffix('.schema.json'),json.loads((ROOT/'contracts'/entry['file']).read_text()))

    def test_sql_input_is_not_a_compare_request(self):
        value=json.loads((ROOT/'contracts/examples/data_compare_request.json').read_text());value['sql']='SELECT * FROM private_uploads'
        with self.assertRaises(Exception): validate('data_compare_request',value)

    def test_invalid_phase_rejected(self):
        value=json.loads((ROOT/'contracts/examples/progress_event.json').read_text());value['phase']='invented'
        with self.assertRaises(Exception): validate('progress_event',value)


if __name__=='__main__':
    unittest.main()
