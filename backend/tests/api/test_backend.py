"""C3 backend tests: store, worker, HTTP contract (incl. C0's frozen smoke).

Run from the worktree root:
  TWINSITE_REFERENCE_ENGINE_DIR=<.../ARES/implementation> PYTHONPATH=backend:. \
    python -m unittest discover -s backend/tests -t . -v
All mission inputs here are SYNTHETIC fixtures from contracts/examples.
"""
import dataclasses
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
for p in (str(ROOT / 'backend'), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
if 'TWINSITE_REFERENCE_ENGINE_DIR' not in os.environ:
    for candidate in (ROOT, ROOT.parents[1]):  # worktree, or main checkout two levels up
        engine = candidate / 'references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation'
        if (engine / 'ares/engine.py').is_file():
            os.environ['TWINSITE_REFERENCE_ENGINE_DIR'] = str(engine)
            break

from twinsite.api.openapi import build_openapi  # noqa: E402
from twinsite.api.server import make_server  # noqa: E402
from twinsite.jobs import science_adapter  # noqa: E402
from twinsite.jobs.contract import schema_validation_available, validate  # noqa: E402
from twinsite.jobs.worker import TransientError, Worker  # noqa: E402
from twinsite.storage import CapacityError, Conflict, LeaseLost, Store, load_settings  # noqa: E402

EXAMPLES = ROOT / 'contracts' / 'examples'
FIXTURES = ['mission', 'moon_mission', 'three_body_mission', 'zone_mission']


def fixture(name):
    return json.loads((EXAMPLES / f'{name}.synthetic.json').read_text())


def engine_available():
    try:
        science_adapter.load_engine()
        return True
    except science_adapter.ScienceUnavailable:
        return False


class TempDirCase(unittest.TestCase):
    def assert_c2_result(self, actual, expected, name):
        from twinsite.science import ENGINE_VERSION
        self.assertEqual(actual['algorithm_version'], ENGINE_VERSION)
        self.assertIn('SYNTHETIC', ' '.join(actual['limitations']))
        # C2 deliberately identifies its own engine and adds scientific limitations.
        # Every numerical field must still match the frozen reference exactly.
        for key in ('algorithm_version', 'limitations'):
            actual.pop(key)
            expected.pop(key)
        self.assertEqual(actual, expected, name)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='twinsite-c3-')
        self.settings = dataclasses.replace(load_settings(self.tmp.name), lease_seconds=5)

    def tearDown(self):
        self.tmp.cleanup()


class StoreTests(TempDirCase):
    def test_idempotency_and_conflict(self):
        store = Store(self.settings.db_path)
        payload = fixture('mission')
        run_id, replay = store.submit(payload, 'k1')
        self.assertFalse(replay)
        self.assertEqual(store.submit(payload, 'k1'), (run_id, True))
        changed = json.loads(json.dumps(payload))
        changed['mission']['id'] = 'other'
        with self.assertRaises(Conflict):
            store.submit(changed, 'k1')

    def test_bounded_queue(self):
        store = Store(self.settings.db_path, queue_limit=2)
        store.submit(fixture('mission'), 'a')
        store.submit(fixture('moon_mission'), 'b')
        with self.assertRaises(CapacityError):
            store.submit(fixture('zone_mission'), 'c')
        # A replay of an existing key still succeeds while full.
        self.assertTrue(store.submit(fixture('mission'), 'a')[1])

    def test_single_active_and_fenced_commit(self):
        store = Store(self.settings.db_path)
        store.submit(fixture('mission'), 'a')
        store.submit(fixture('moon_mission'), 'b')
        run = store.claim('w1', 30)
        self.assertIsNotNone(run)
        self.assertIsNone(store.claim('w2', 30), 'only one active mission')
        stale = dict(run, fence='not-the-fence')
        with self.assertRaises(LeaseLost):
            store.commit(stale, {}, {'release_action': 'BLOCK'}, '', 'completed_with_limits', 's')

    def test_expired_lease_requeues_then_exhausts(self):
        store = Store(self.settings.db_path, max_attempts=2)
        run_id, _ = store.submit(fixture('mission'), 'a')
        for attempt in (1, 2):
            run = store.claim('w', 0)  # lease expires immediately
            self.assertEqual(run['attempt'], attempt)
            time.sleep(0.01)
        self.assertIsNone(store.claim('w', 0))
        self.assertEqual(store.get(run_id)['status'], 'failed')
        events = store.events(run_id)
        self.assertEqual([e['sequence'] for e in events], list(range(1, len(events) + 1)))
        validate('events', events)

    def test_cancel_queued(self):
        store = Store(self.settings.db_path)
        run_id, _ = store.submit(fixture('mission'), 'a')
        self.assertEqual(store.request_cancel(run_id), 'cancelled')
        self.assertIsNone(store.claim('w', 30))
        self.assertIsNone(store.request_cancel('missing'))


@unittest.skipUnless(engine_available(), 'scoring engine unavailable (run make bootstrap)')
class WorkerTests(TempDirCase):
    def worker(self, **kw):
        return Worker(self.settings, worker_id='test', retry_base_seconds=0.01, **kw)

    def drain(self, worker, run_id, limit=10):
        for _ in range(limit):
            worker.run_once()
            if worker.store.get(run_id)['status'] in ('completed', 'completed_with_limits', 'failed', 'cancelled'):
                return worker.store.get(run_id)
            time.sleep(0.02)
        self.fail('run did not finish')

    def test_fixtures_reproduce_frozen_results(self):
        worker = self.worker()
        for name in FIXTURES:
            run_id, _ = worker.store.submit(fixture(name), 'k-' + name)
            run = self.drain(worker, run_id)
            self.assertEqual(run['status'], 'completed_with_limits')
            committed = worker.store.committed(run_id)
            expected = json.loads((EXAMPLES / f'{name}.result.synthetic.json').read_text())
            self.assert_c2_result(json.loads(committed['result']), expected, name)
            evidence = json.loads(committed['evidence'])
            self.assertEqual((evidence['data_status'], evidence['release_action']), ('synthetic', 'BLOCK'))
            self.assertEqual(evidence['source_snapshot_id'], run['source_snapshot_id'])
            self.assertIn('SYNTHETIC', committed['report'])
            phases = [e['phase'] for e in worker.store.events(run_id)]
            self.assertEqual(sorted(set(phases)), ['P00', 'P10', 'P20', 'P30', 'P40', 'P50', 'P60', 'P70', 'P80', 'P90'])

    def test_measured_input_is_never_published(self):
        worker = self.worker()
        payload = fixture('mission')
        payload['data_status'] = 'measured'
        run_id, _ = worker.store.submit(payload, 'measured')
        run = self.drain(worker, run_id)
        self.assertEqual(run['status'], 'failed')
        self.assertTrue(run['error'].startswith('INVALID_MISSION'))
        self.assertIsNone(worker.store.committed(run_id))

    def test_transient_failure_retries(self):
        real = science_adapter.load_engine()
        calls = []

        def flaky(payload, progress=None):
            calls.append(1)
            if len(calls) == 1:
                raise TransientError('upstream timeout')
            return real.analyze(payload, progress=progress)

        worker = self.worker(engine_loader=lambda: dataclasses.replace(real, analyze=flaky))
        run_id, _ = worker.store.submit(fixture('mission'), 'flaky')
        run = self.drain(worker, run_id)
        self.assertEqual((run['status'], run['attempt']), ('completed_with_limits', 2))
        self.assertIn('retry_wait', [e['state'] for e in worker.store.events(run_id)])

    def test_permanent_failure_not_retried(self):
        real = science_adapter.load_engine()

        def broken(payload, progress=None):
            raise ValueError('feature unit mismatch')

        worker = self.worker(engine_loader=lambda: dataclasses.replace(real, analyze=broken))
        run_id, _ = worker.store.submit(fixture('mission'), 'broken')
        run = self.drain(worker, run_id)
        self.assertEqual((run['status'], run['attempt']), ('failed', 1))
        self.assertTrue(run['error'].startswith('INVALID_MISSION'))

    def test_cancel_during_run(self):
        real = science_adapter.load_engine()
        holder = {}

        def cancelling(payload, progress=None):
            holder['store'].request_cancel(holder['run_id'])
            return real.analyze(payload, progress=progress)

        worker = self.worker(engine_loader=lambda: dataclasses.replace(real, analyze=cancelling))
        holder['store'] = worker.store
        holder['run_id'], _ = worker.store.submit(fixture('mission'), 'cancel')
        run = self.drain(worker, holder['run_id'])
        self.assertEqual(run['status'], 'cancelled')
        self.assertIsNone(worker.store.committed(holder['run_id']))
        self.assertEqual(worker.store.events(holder['run_id'])[-1]['state'], 'cancelled')


@unittest.skipUnless(engine_available(), 'scoring engine unavailable (run make bootstrap)')
class HttpTests(TempDirCase):
    def setUp(self):
        super().setUp()
        self.server = make_server(self.settings, host='127.0.0.1', port=0)
        self.base = 'http://127.0.0.1:%d' % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.worker = Worker(self.settings, worker_id='http-test', poll_seconds=0.05)
        self.worker_thread = threading.Thread(target=self.worker.run_forever, daemon=True)
        self.worker_thread.start()

    def tearDown(self):
        self.worker.stop_event.set()
        self.worker_thread.join(5)
        self.server.shutdown()
        self.server.server_close()
        super().tearDown()

    def call(self, method, path, body=None, headers=None):
        data = body if isinstance(body, bytes) or body is None else json.dumps(body).encode()
        request = Request(self.base + path, data=data, method=method, headers=headers or {})
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, response.headers, response.read()

    @unittest.skipUnless(schema_validation_available(), 'jsonschema not installed')
    def test_c0_frozen_smoke(self):
        sys.path.insert(0, str(ROOT / 'scripts' / 'integration'))
        import smoke
        smoke.run(self.base)

    def test_http_submission_hashes_original_and_reproduces_fixture(self):
        from contracts.validation import digest
        for name in FIXTURES:
            raw = (EXAMPLES / f'{name}.synthetic.json').read_bytes()
            status, _, body = self.call('POST', '/v1/missions', raw,
                                        {'Content-Type': 'application/json', 'Idempotency-Key': 'orig-' + name})
            self.assertEqual(status, 202)
            run_id = json.loads(body)['run_id']
            deadline = time.monotonic() + 20
            while True:
                code, _, result = self.call('GET', f'/v1/missions/{run_id}/result')
                if code == 200:
                    break
                self.assertEqual(code, 409)
                self.assertLess(time.monotonic(), deadline)
                time.sleep(0.05)
            _, _, status_body = self.call('GET', f'/v1/missions/{run_id}')
            self.assertEqual(json.loads(status_body)['input_sha256'], digest(json.loads(raw)))
            expected = json.loads((EXAMPLES / f'{name}.result.synthetic.json').read_text())
            self.assert_c2_result(json.loads(result), expected, name)

    def test_health_and_reserved_routes(self):
        status, _, body = self.call('GET', '/v1/health')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), {'schema_version': '1.0', 'status': 'ready', 'ai_enabled': False, 'uploads_enabled': False})
        self.assertEqual(self.call('GET', '/v1/data/catalog')[0], 200)
        self.assertEqual(self.call('GET', '/v1/data/x/records')[0], 404)
        for method, path in [('POST', '/v1/uploads'),
                             ('POST', '/v1/missions/run-x/portfolios/alternatives')]:
            status, _, body = self.call(method, path, b'{}', {'Content-Type': 'application/json'})
            self.assertEqual(status, 501, path)
            validate('error', json.loads(body))
        self.assertEqual(self.call('GET', '/nope')[0], 404)
        self.assertEqual(self.call('DELETE', '/v1/health')[0], 405)

    def test_request_failures(self):
        json_headers = {'Content-Type': 'application/json'}
        self.assertEqual(self.call('POST', '/v1/missions', fixture('mission'), json_headers)[0], 400)
        big = b'{"pad":"' + b'x' * 1_000_001 + b'"}'
        self.assertEqual(self.call('POST', '/v1/missions', big, {**json_headers, 'Idempotency-Key': 'big'})[0], 413)
        self.assertEqual(self.call('POST', '/v1/missions', b'{"a": NaN}', {**json_headers, 'Idempotency-Key': 'nan'})[0], 422)
        self.assertEqual(self.call('GET', '/v1/missions/run-missing/events?after=-1')[0], 400)
        self.assertEqual(self.call('GET', '/v1/missions/run-missing/events')[0], 404)
        self.assertEqual(self.call('POST', '/v1/missions/run-missing/cancel')[0], 404)

    def test_cors_for_dev_frontend(self):
        origin = 'http://127.0.0.1:5173'
        _, headers, _ = self.call('GET', '/v1/health', headers={'Origin': origin})
        self.assertEqual(headers.get('Access-Control-Allow-Origin'), origin)
        _, headers, _ = self.call('GET', '/v1/health', headers={'Origin': 'https://evil.example'})
        self.assertIsNone(headers.get('Access-Control-Allow-Origin'))

    def test_committed_openapi_is_current(self):
        committed = json.loads((ROOT / 'backend/twinsite/api/openapi.json').read_text())
        self.assertEqual(committed, json.loads(json.dumps(build_openapi())),
                         'regenerate: python -m twinsite.api --print-openapi > backend/twinsite/api/openapi.json')


if __name__ == '__main__':
    unittest.main()
