"""Offline tests for the free-only router, agents and gateway parsing (no network, fake wires)."""
import copy
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))

from twinsite.ai import adapters  # noqa: E402
from twinsite.ai.agents import Orchestrator, numeric_mismatches  # noqa: E402
from twinsite.ai.ledger import Ledger  # noqa: E402
from twinsite.ai.router import Router, Task  # noqa: E402
from twinsite.ai.secrets import SecretFileError, read_env_file  # noqa: E402

SECRETS = {'GROQ_API_KEY': 'g1', 'GROQ_API_KEY_B': 'g2', 'GOOGLE_API_KEY_A1': 'k1', 'OPENROUTER_API_KEY': 'o1',
           'CLOUDFLARE_API_TOKEN': 'c1', 'CLOUDFLARE_ACCOUNT_ID': 'acct', 'CLOUDFLARE_API_TOKEN_X': 'c2',
           'CLOUDFLARE_ACCOUNT_ID_X': 'acct'}


class FakeWire:
    def __init__(self, script):
        self.script, self.calls = script, []

    def __call__(self, endpoint, key, model, system, user, **kw):
        self.calls.append((endpoint, model))
        action = self.script(endpoint, model, len(self.calls))
        if isinstance(action, Exception):
            raise action
        return adapters.Completion(action, model, 200, 10, 5, 3)


def router(tmp, script, secrets=SECRETS):
    wire = FakeWire(script)
    return Router(Ledger(Path(tmp) / 'l.sqlite'), dict(secrets), {'openai_chat': wire, 'google_generate': wire}), wire


def task(**kw):
    base = dict(agent_id='A07', run_id='r', capability='json', system='s', user='u', use_cache=False)
    base.update(kw)
    return Task(**base)


class RouterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.pop('TWINSITE_AI_DISABLED', None)

    def test_success_records_provider_and_ledger(self):
        r, _ = router(self.tmp, lambda e, m, n: '{"ok": 1}')
        out = r.complete(task())
        self.assertTrue(out.ok)
        self.assertEqual(out.output, {'ok': 1})
        self.assertEqual(out.provider, 'groq')
        self.assertEqual(r.ledger.summary()['groq']['outcomes'], {'success': 1})

    def test_rate_limit_falls_back_to_another_quota_group_and_cools_down(self):
        r, wire = router(self.tmp, lambda e, m, n: adapters.ProviderError('rate_limited', '429', 429, 30) if n == 1 else '{"a":1}')
        out = r.complete(task())
        self.assertTrue(out.ok)
        self.assertEqual(out.attempts[0]['error'], 'rate_limited')
        self.assertTrue(r.ledger.breakers())

    def test_payment_required_opens_breaker_never_pays(self):
        r, _ = router(self.tmp, lambda e, m, n: adapters.ProviderError('payment_required', '402', 402))
        out = r.complete(task())
        self.assertFalse(out.ok)
        self.assertTrue(any('payment_required' in b['reason'] for b in r.ledger.breakers()))

    def test_invalid_json_moves_to_different_model(self):
        r, wire = router(self.tmp, lambda e, m, n: 'not json' if n == 1 else '{"a":1}')
        out = r.complete(task())
        self.assertTrue(out.ok)
        first, second = out.attempts[0], out.attempts[-1]
        self.assertNotEqual((first['provider'], first['model']), (second['provider'], second['model']))

    def test_max_attempts_bounded(self):
        r, wire = router(self.tmp, lambda e, m, n: adapters.ProviderError('server', '500', 500))
        out = r.complete(task())
        self.assertFalse(out.ok)
        self.assertLessEqual(len(wire.calls), 3)
        self.assertIn('All attempted free providers failed', out.error)

    def test_disabled_makes_no_calls(self):
        r, wire = router(self.tmp, lambda e, m, n: '{}', secrets={})
        out = r.complete(task())
        self.assertFalse(out.ok)
        self.assertEqual(wire.calls, [])
        with mock.patch.dict(os.environ, {'TWINSITE_AI_DISABLED': '1'}):
            r2, wire2 = router(self.tmp, lambda e, m, n: '{}')
            self.assertFalse(r2.complete(task()).ok)
            self.assertEqual(wire2.calls, [])

    def test_private_data_never_egresses_and_uploads_need_consent(self):
        r, wire = router(self.tmp, lambda e, m, n: '{}')
        self.assertFalse(r.complete(task(data_class='PRIVATE_OPERATIONS_NEVER_EGRESS')).ok)
        self.assertEqual(r.candidates(task(data_class='USER_UPLOAD_WITH_PROVIDER_CONSENT'))[0], [])
        cands, _ = r.candidates(task(data_class='USER_UPLOAD_WITH_PROVIDER_CONSENT', consent_providers=frozenset({'groq', 'google'})))
        self.assertTrue(cands)
        self.assertTrue(all(a.egress == 'E1_PRIVATE' for _, _, a, _ in cands))
        self.assertFalse(any(p.id == 'google' for p, _, _, _ in cands))  # free Gemini trains on inputs

    def test_shared_cloudflare_account_is_one_quota_group(self):
        r, _ = router(self.tmp, lambda e, m, n: '{}')
        groups = {a.quota_group for a in r.accounts if a.provider == 'cloudflare'}
        self.assertEqual(len(groups), 1)

    def test_daily_cap_and_dev_reserve(self):
        r, _ = router(self.tmp, lambda e, m, n: '{}', secrets={'GROQ_API_KEY': 'g'})
        for _ in range(30):
            r.ledger.record(provider='groq', account='GROQ_API_KEY', quota_group='groq:GROQ_API_KEY', model='m', outcome='success')
        self.assertEqual(r.candidates(task(priority='dev'))[0], [])      # 30 >= 60 * 0.5
        self.assertTrue(r.candidates(task(priority='mission'))[0])

    def test_openrouter_closed_when_not_free_tier(self):
        r, wire = router(self.tmp, lambda e, m, n: '{}', secrets={'OPENROUTER_API_KEY': 'o'})
        with mock.patch.object(adapters, 'get_json', return_value=(200, {'data': {'is_free_tier': False}})):
            out = r.complete(task())
        self.assertFalse(out.ok)
        self.assertEqual(wire.calls, [])
        self.assertTrue(all(':free' in m.model for m in __import__('twinsite.ai.catalog', fromlist=['x']).PROVIDER_BY_ID['openrouter'].models))

    def test_cache_is_labelled(self):
        r, wire = router(self.tmp, lambda e, m, n: '{"x":1}')
        self.assertFalse(r.complete(task(use_cache=True)).cached)
        again = r.complete(task(use_cache=True))
        self.assertTrue(again.cached)
        self.assertEqual(len(wire.calls), 1)


class SecretsTests(unittest.TestCase):
    def test_rejects_group_readable_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 's.env'
            p.write_text('GROQ_API_KEY=abc\n')
            os.chmod(p, 0o644)
            with self.assertRaises(SecretFileError):
                read_env_file(p)
            os.chmod(p, 0o600)
            self.assertEqual(read_env_file(p), {'GROQ_API_KEY': 'abc'})

    def test_no_secret_in_tracked_catalog(self):
        text = (ROOT / 'backend/twinsite/ai/catalog.py').read_text()
        self.assertNotRegex(text, r'gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_\-]{30,}|sk-or-v1-[0-9a-f]{20,}|nvapi-[A-Za-z0-9_\-]{20,}')


MEASURED = json.loads((ROOT / 'backend/twinsite/processing/published/g2_feature_pair.json').read_text())


class OrchestratorTests(unittest.TestCase):
    def payload_result(self):
        from twinsite.jobs.measured import resolve_request
        from twinsite.science import analyze_mission
        payload = resolve_request({'schema_version': '1.0', 'dataset_id': 'zagora-gale-v1'})
        out = analyze_mission(payload, evidence=MEASURED['observations'], mode='strict')
        sidecar = {'release_action': 'BLOCK', 'blocking_issues': ['C5_INDEPENDENT_REVIEW_REQUIRED']}
        return payload, out['result'], sidecar

    def test_fallback_when_disabled_never_claims_ai(self):
        payload, result, sidecar = self.payload_result()
        r, wire = router(tempfile.mkdtemp(), lambda e, m, n: '{}', secrets={})
        trace = Orchestrator(r).run('r', payload, result, sidecar, MEASURED['observations'])
        self.assertEqual(trace['ai_roles_executed'], [])
        self.assertEqual(len({x['agent_id'] for x in trace['records']}), 13)
        self.assertEqual(wire.calls, [])
        self.assertTrue(all(not x['agent_result']['ai_used'] for x in trace['records']))
        from twinsite.jobs.contract import validate
        for rec in trace['records']:
            validate('agent_result', dict(rec['agent_result'], run_id='r'))

    def test_ai_roles_cite_only_known_evidence_and_result_unchanged(self):
        payload, result, sidecar = self.payload_result()
        ev = MEASURED['observations'][0]['evidence_id']

        def script(e, model, n):
            return json.dumps({'scenarios': [{'name': 'x', 'weights': {'slope_deg': 0.5, 'roughness_m': 0.3, 'dry_fraction': 0.2},
                                              'rationale': 'r'}],
                               'findings': [{'domain': 'topography', 'claim': 'slope is gentle at the site', 'evidence_ids': [ev]},
                                            {'domain': 'topography', 'claim': 'fabricated finding text', 'evidence_ids': ['ev-fake']}],
                               'summary': 's', 'key_claims': [{'claim': 'slope is 99.9 degrees', 'evidence_ids': [ev], 'basis': 'measured'}],
                               'reviews': [{'claim_index': 0, 'verdict': 'supported', 'reason': 'ok'}],
                               'rechecks': [{'claim_index': 0, 'revised_claim': 'withdrawn', 'evidence_ids': [], 'verdict': 'withdrawn'}]})
        r, wire = router(tempfile.mkdtemp(), script)
        before = copy.deepcopy(result)
        rescore = lambda w: {'status': 'ok'}  # noqa: E731
        trace = Orchestrator(r, rescore=rescore).run('r', payload, result, sidecar, MEASURED['observations'])
        self.assertEqual(result, before)
        recs = {x['agent_id']: x for x in trace['records']}
        self.assertEqual(recs['A06']['output']['dropped_uncited_findings'], 1)
        self.assertEqual(recs['A09']['output']['numeric_mismatches'][0], ['99.9'])   # deterministic check catches fabrication
        self.assertEqual(recs['A12']['execution'], 'ai')
        self.assertIn('A07', trace['ai_roles_executed'])
        self.assertTrue(all(x['inference']['provider'] for x in trace['records'] if x['execution'] == 'ai'))

    def test_numeric_check(self):
        packet = {'e': {'evidence_id': 'e', 'value': 0.5838, 'interval_p10_p90': [0.1461, 1.4995]}}
        self.assertEqual(numeric_mismatches({'claim': 'slope 0.584 deg (0.146-1.50)', 'evidence_ids': ['e']}, packet), [])
        self.assertEqual(numeric_mismatches({'claim': 'slope 12.5 deg', 'evidence_ids': ['e']}, packet), ['12.5'])


class GatewayTests(unittest.TestCase):
    def test_power_parse_fill_values_units_and_kind(self):
        from twinsite.sources import gateway
        months = {m: 10.0 + i for i, m in enumerate(gateway.MONTHS)}
        doc = {'header': {'fill_value': -999.0, 'range': '2001-2025'}, 'geometry': {'coordinates': [-5.8, 30.35, 900]},
               'parameters': {'T2M': {'units': 'C'}, 'PS': {'units': 'kPa'}},
               'properties': {'parameter': {'T2M': dict(months, ANN=15.5), 'PS': dict(months, ANN=-999.0)}}}
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(gateway, '_get', return_value=(json.dumps(doc).encode(), 'application/json')):
            out = gateway.acquire_power(Path(tmp), 'site-x', -5.8, 30.35)
            rows = {o['quantity']: o for o in out['observations']}
            self.assertEqual(rows['air_temperature_2m']['value'], 15.5)
            self.assertEqual(rows['air_temperature_2m']['kind'], 'reanalysis_model')
            self.assertIsNone(rows['surface_pressure']['value'])
            self.assertEqual(rows['surface_pressure']['missing_reason'], 'POWER fill value')
            self.assertEqual(rows['air_temperature_seasonal_amplitude']['value'], 11.0)
            from twinsite.storage.science_db import science_db
            total, persisted = science_db(Path(tmp)).observations(['site-x'])
            self.assertEqual(total, len(out['observations']))
            self.assertTrue(all(p['asset_id'] == out['asset_id'] for p in persisted))


if __name__ == '__main__':
    unittest.main()
