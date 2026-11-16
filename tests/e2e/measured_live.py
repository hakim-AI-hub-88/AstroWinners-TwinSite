"""Live HTTP acceptance for the MEASURED Zagora-Gale path (real API + worker processes).

Starts its own API and worker on a free loopback port with a throwaway data dir, then checks:
C2 engine identity, release gate, complete P00-P90 events, restart byte-identity,
idempotency after restart, worker-down queueing, SIGKILL mid-run recovery, and
server-side resolution guards. Never touches credentials: the Earthdata secret file
is disabled for every child process and no network acquisition is performed.

    python tests/e2e/measured_live.py [--json out.json]
"""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = ('completed', 'completed_with_limits', 'failed', 'cancelled')
MEASURED = {'schema_version': '1.0', 'dataset_id': 'zagora-gale-v1'}
EXPECTED_BLOCKERS = {'C5_INDEPENDENT_REVIEW_REQUIRED', 'NO_QUALIFIED_CANDIDATE', 'UNREGISTERED_FEATURE:dry_fraction'}


class Stack:
    def __init__(self, data_dir, port):
        self.port, self.base = port, f'http://127.0.0.1:{port}/v1'
        self.logs = Path(data_dir) / 'logs'
        self.logs.mkdir(parents=True, exist_ok=True)
        self.env = {k: v for k, v in os.environ.items() if 'TOKEN' not in k and 'SECRET' not in k and 'KEY' not in k}
        self.env.update(TWINSITE_SECRET_ENV_FILE=os.devnull + '.disabled', TWINSITE_AI_ENABLED='false',
                        TWINSITE_UPLOADS_ENABLED='false', TWINSITE_API_HOST='127.0.0.1', TWINSITE_API_PORT=str(port),
                        TWINSITE_DATA_DIR=str(data_dir),
                        TWINSITE_SOURCE_DATA_DIR=os.environ.get('TWINSITE_SOURCE_DATA_DIR', str(ROOT / '.runtime/data')),
                        PYTHONPATH=os.pathsep.join([str(ROOT / 'backend'), str(ROOT)]))
        self.procs = {}

    def start(self, kind):
        module = 'twinsite.api' if kind == 'api' else 'twinsite.jobs'
        log = (self.logs / f'{kind}.log').open('a')
        self.procs[kind] = subprocess.Popen([sys.executable, '-m', module], cwd=ROOT, env=self.env,
                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        if kind == 'api':
            for _ in range(100):
                try:
                    if self.req('GET', '/health')[0] == 200:
                        return
                except OSError:
                    pass
                time.sleep(0.1)
            raise RuntimeError('API did not become ready')

    def stop(self, kind, sig=signal.SIGTERM):
        proc = self.procs.pop(kind, None)
        if proc and proc.poll() is None:
            os.killpg(proc.pid, sig)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()

    def req(self, method, path, body=None, key=None):
        headers = {'Content-Type': 'application/json'}
        if key:
            headers['Idempotency-Key'] = key
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=15) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    def status(self, run_id):
        return json.loads(self.req('GET', f'/missions/{run_id}')[1])

    def wait(self, run_id, timeout=60):
        end = time.time() + timeout
        while time.time() < end:
            st = self.status(run_id)
            if st['status'] in TERMINAL:
                return st
            time.sleep(0.1)
        raise RuntimeError(f'{run_id} did not finish')

    def submit(self, key):
        status, body = self.req('POST', '/missions/measured', MEASURED, key)
        if status != 202:
            raise RuntimeError(f'measured submit returned {status}: {body[:200]!r}')
        return json.loads(body)['run_id']

    def artifacts(self, run_id):
        return {k: self.req('GET', f'/missions/{run_id}/{k}')[1] for k in ('result', 'evidence', 'report')}


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json')
    args = parser.parse_args()
    results = []

    def check(name, ok, detail=''):
        results.append({'check': name, 'status': 'PASS' if ok else 'FAIL', 'detail': str(detail)})
        print(('PASS ' if ok else 'FAIL ') + name + (f' | {detail}' if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='twinsite-measured-e2e-') as tmp:
        stack = Stack(tmp, free_port())
        try:
            stack.start('api')
            stack.start('worker')
            rid = stack.submit('measured-e2e-1')
            final = stack.wait(rid)
            check('measured run completes with limits', final['status'] == 'completed_with_limits', final['status'])
            first = stack.artifacts(rid)
            result, evidence = json.loads(first['result']), json.loads(first['evidence'])
            from twinsite.science import ENGINE_VERSION
            check('C2 engine executed (not historical ARES)', result['algorithm_version'] == ENGINE_VERSION
                  and 'ares' not in first['result'].decode().lower(), result['algorithm_version'])
            check('result and evidence declare measured data', result['data_status'] == 'measured'
                  and evidence['data_status'] == 'measured')
            check('release gate stays BLOCK with expected blockers',
                  evidence['release_action'] == 'BLOCK' and EXPECTED_BLOCKERS <= set(evidence['blocking_issues']),
                  evidence['blocking_issues'])
            check('no feasible portfolio preserved', result['status'] == 'no_feasible_portfolio'
                  and result['feasible_portfolio_count'] == 0, result['status'])
            events = json.loads(stack.req('GET', f'/missions/{rid}/events?after=0')[1])
            phases = [e['phase'] for e in events]
            last = {}
            for e in events:
                last[e['phase']] = e['state']
            check('events cover P00..P90 in order', sorted(set(phases)) == [f'P{i}0' for i in range(10)] and phases == sorted(phases),
                  ' '.join(phases))
            check('every worker phase ends succeeded', all(last[f'P{i}0'] == 'succeeded' for i in range(1, 10)), last)

            stack.stop('api')
            stack.stop('worker')
            stack.start('api')
            stack.start('worker')
            check('API+worker restart keeps measured artifacts byte-identical', stack.artifacts(rid) == first, rid)
            check('idempotency key replays same run after restart', stack.submit('measured-e2e-1') == rid)

            stack.stop('worker')
            queued = stack.submit('measured-e2e-queued')
            time.sleep(1.5)
            before = stack.status(queued)['status']
            stack.start('worker')
            after = stack.wait(queued)
            check('worker down: measured run stays queued, completes after start',
                  before == 'queued' and after['status'] == 'completed_with_limits', f'{before}->{after["status"]}')
            check('deterministic measured result across runs',
                  json.loads(stack.artifacts(queued)['result']) == result)

            killed_in, rk = None, None
            for attempt in range(40):
                stack.stop('worker')
                rk = stack.submit(f'measured-e2e-kill-{attempt}')
                stack.start('worker')
                end = time.time() + 10
                while time.time() < end:
                    st = stack.status(rk)['status']
                    if st in TERMINAL:
                        break
                    if st != 'queued':
                        stack.stop('worker', signal.SIGKILL)
                        killed_in = st
                        break
                    time.sleep(0.002)
                if killed_in:
                    break
            if killed_in:
                stack.start('worker')
                rec = stack.wait(rk, timeout=120)
                check('worker SIGKILL mid measured run recovers deterministically',
                      rec['status'] == 'completed_with_limits' and rec.get('attempt', 0) <= 3
                      and json.loads(stack.artifacts(rk)['result']) == result,
                      f'killed in {killed_in}; attempt {rec.get("attempt")}')
            else:
                stack.start('worker')
                results.append({'check': 'worker SIGKILL mid measured run recovers deterministically',
                                'status': 'NOT_EXERCISED', 'detail': 'run finished before it could be interrupted'})
                print('NOT_EXERCISED worker SIGKILL mid measured run', flush=True)

            s, b = stack.req('POST', '/missions', {'schema_version': '1.0', 'data_status': 'measured'}, 'guard-1')
            check('client-asserted measured payload rejected', s == 422 and b'SERVER_RESOLUTION_REQUIRED' in b, s)
            s, _ = stack.req('POST', '/missions/measured', {'schema_version': '1.0', 'dataset_id': 'elsewhere'}, 'guard-2')
            check('unknown measured dataset rejected', s == 422, s)
            s, _ = stack.req('POST', '/missions/measured', {**MEASURED, 'weights': {'slope_deg': 1}}, 'guard-3')
            check('client cannot alter server-resolved mission parameters', s == 422, s)
            s, _ = stack.req('GET', '/data/catalog?limit=100')
            check('data catalog served live', s == 200, s)
            for path, want in [('/data/catalog?limit=0', 422), ('/data/nope/records', 404),
                               ('/data/earth-zagora-draa/records?stage=bogus', 422)]:
                s, _ = stack.req('GET', path)
                check(f'GET {path} -> {want}', s == want, s)
            for body in ({'schema_version': '1.0', 'bogus': 1}, [1, 2]):
                s, _ = stack.req('POST', '/data/compare', body)
                check(f'invalid compare body {type(body).__name__} -> 422', s == 422, s)
        except Exception as error:  # noqa: BLE001 — reported as a failed check
            check('measured e2e harness', False, f'{type(error).__name__}: {error}')
        finally:
            stack.stop('worker')
            stack.stop('api')
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2) + '\n')
    failed = [r for r in results if r['status'] != 'PASS']
    print(f'Measured E2E: {len(results) - len(failed)} PASS, {len(failed)} not passing.', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.path[:0] = [str(ROOT / 'backend'), str(ROOT)]
    sys.exit(main())
