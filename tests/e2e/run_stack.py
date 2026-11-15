"""C5 G1/G5 end-to-end harness: boots C3's API + worker from a composite tree with
ALL provider credentials stripped, then runs:

  1. C0 smoke (scripts/integration/smoke.py --base-url)  — reused, not duplicated
  2. C5 HTTP acceptance (tests/acceptance/http_contract.py)
  3. Restart persistence: full API+worker restart keeps result/evidence/events/report byte-identical
  4. Worker-down queueing + SIGKILL-mid-run recovery (attempt <= 3, deterministic result)
  5. AI flag ON with zero keys still completes with an identical result (no AI dependency)
  6. Unusable storage => health 503 or refusal to start (never "ready")

  python tests/e2e/run_stack.py --tree <composite> [--python <venv python>] [--json out.json]

SYNTHETIC ONLY. Every check is PASS / FAIL / NOT_EXERCISED / BLOCKED.
"""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve()
SECRET_ENV = re.compile(r'(KEY|TOKEN|SECRET|PASSW|EARTHDATA|OPENAI|ANTHROPIC|CLAUDE|GROQ|GEMINI|GOOGLE|MISTRAL|'
                        r'OPENROUTER|CLOUDFLARE|CF_|HF_|HUGGING|COHERE|TOGETHER|AWS_|AZURE|GCP|NETRC)', re.I)


def scrubbed_env(tree, data_dir, port, ai='false'):
    env = {k: v for k, v in os.environ.items() if not SECRET_ENV.search(k)}
    env.update(TWINSITE_AI_ENABLED=ai, TWINSITE_UPLOADS_ENABLED='false', TWINSITE_API_HOST='127.0.0.1',
               TWINSITE_API_PORT=str(port), TWINSITE_DATA_DIR=str(data_dir),
               PYTHONPATH=os.pathsep.join([str(Path(tree) / 'backend'), str(tree)]),
               NETRC=os.devnull, HOME=str(data_dir))  # no ~/.netrc Earthdata creds, no user config
    return env


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def http(base, path, body=None, key=None):
    headers = {}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers['Content-Type'] = 'application/json'
    if key:
        headers['Idempotency-Key'] = key
    try:
        resp = urlopen(Request(base + path, data=data, headers=headers), timeout=10)
    except HTTPError as e:
        resp = e
    with resp:
        return resp.status, resp.read().decode('utf-8', 'replace')


class Stack:
    def __init__(self, tree, python, data_dir, logs, ai='false'):
        self.tree, self.python, self.data_dir, self.logs, self.ai = Path(tree), python, Path(data_dir), Path(logs), ai
        self.port = free_port()
        self.base = f'http://127.0.0.1:{self.port}'
        self.api = self.worker = None

    def _spawn(self, module, tag):
        env = scrubbed_env(self.tree, self.data_dir, self.port, self.ai)
        log = open(self.logs / f'{tag}-{int(time.time()*1000)}.log', 'wb')
        return subprocess.Popen([self.python, '-m', module], cwd=self.tree, env=env, stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True)

    def start_api(self, timeout=30):
        self.api = self._spawn('twinsite.api', 'api')
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.api.poll() is not None:
                raise RuntimeError(f'twinsite.api exited with {self.api.returncode}; see {self.logs}')
            try:
                code, _ = http(self.base, '/v1/health')
                if code == 200:
                    return
            except (URLError, ConnectionError, OSError):
                pass
            time.sleep(0.2)
        raise RuntimeError('twinsite.api did not report healthy within %ss' % timeout)

    def start_worker(self):
        self.worker = self._spawn('twinsite.jobs', 'worker')
        time.sleep(0.5)
        if self.worker.poll() is not None:
            raise RuntimeError(f'twinsite.jobs exited with {self.worker.returncode}; see {self.logs}')

    @staticmethod
    def _stop(proc, sig=signal.SIGTERM):
        if proc and proc.poll() is None:
            try:
                os.killpg(proc.pid, sig)
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            except ProcessLookupError:
                pass

    def stop_worker(self, sig=signal.SIGTERM):
        self._stop(self.worker, sig)

    def stop(self):
        self._stop(self.worker)
        self._stop(self.api)


def wait_status(base, run_id, terminal=True, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        code, text = http(base, f'/v1/missions/{run_id}')
        st = json.loads(text) if code == 200 else {}
        if st.get('status') in ('completed', 'completed_with_limits', 'failed', 'cancelled') or not terminal:
            return st
        time.sleep(0.1)
    raise AssertionError(f'{run_id} not terminal within {timeout}s (last {st.get("status")})')


def snapshot(base, run_id):
    out = {}
    for part in ('', '/result', '/evidence', '/report', '/events?after=0'):
        out[part or '/status'] = http(base, f'/v1/missions/{run_id}{part}')
    return out


class Harness:
    def __init__(self, tree, python, json_out):
        self.tree, self.python, self.json_out = Path(tree), python, json_out
        self.results = []
        self.work = Path(tempfile.mkdtemp(prefix='c5-e2e-'))
        self.payload = json.loads((self.tree / 'contracts/examples/mission.synthetic.json').read_text())

    def record(self, name, status, detail=''):
        self.results.append({'check': name, 'status': status, 'detail': detail})
        print(f'{status:14} {name}' + (f' — {detail}' if detail else ''), flush=True)

    def guarded(self, name, fn):
        try:
            out = fn()
            if isinstance(out, tuple):
                self.record(name, *out)
            else:
                self.record(name, 'PASS', out or '')
        except AssertionError as e:
            self.record(name, 'FAIL', str(e)[:400])
        except Exception as e:
            self.record(name, 'FAIL', f'{type(e).__name__}: {str(e)[:400]}')

    def new_stack(self, tag, ai='false'):
        data = self.work / f'data-{tag}'
        data.mkdir(exist_ok=True)
        logs = self.work / 'logs'
        logs.mkdir(exist_ok=True)
        return Stack(self.tree, self.python, data, logs, ai)

    def submit(self, base, key=None, payload=None):
        code, text = http(base, '/v1/missions', payload or self.payload, key or 'c5-e2e-' + uuid.uuid4().hex)
        assert code == 202, f'submit HTTP {code}: {text[:200]}'
        return json.loads(text)['run_id']

    def run(self):
        missing = [p for p in ('backend/twinsite/api/__main__.py', 'backend/twinsite/jobs/__main__.py') if not (self.tree / p).exists()]
        if missing:
            self.record('C3 API/worker entry points present', 'BLOCKED', 'missing: ' + ', '.join(missing))
            return self.finish()
        stack = self.new_stack('main')
        try:
            stack.start_api()
            stack.start_worker()
        except Exception as e:
            self.record('stack boots with zero provider keys', 'FAIL', str(e))
            stack.stop()
            return self.finish()
        self.record('stack boots with zero provider keys (AI-free env)', 'PASS', stack.base)
        try:
            self.guarded('C0 smoke (scripts/integration/smoke.py --base-url)', lambda: self.subprocess_check(
                [self.python, 'scripts/integration/smoke.py', '--base-url', stack.base]))
            acc = HERE.parents[1] / 'acceptance/http_contract.py'
            self.guarded('C5 HTTP acceptance suite', lambda: self.subprocess_check(
                [self.python, str(acc), '--base-url', stack.base, '--repo', str(self.tree),
                 '--json', str(self.work / 'http_contract.json')]))
            self.guarded('restart: API+worker restart keeps committed artifacts byte-identical',
                         lambda: self.restart_persistence(stack))
            self.guarded('worker down: job stays queued, completes after worker starts', lambda: self.worker_down(stack))
            self.guarded('worker SIGKILL mid-run: recovers, attempt<=3, deterministic', lambda: self.worker_kill(stack))
        finally:
            stack.stop()
        self.guarded('AI flag ON with zero keys: completes, identical result', self.ai_flag_without_keys)
        self.guarded('unusable storage: never reports ready', self.bad_storage)
        return self.finish()

    def subprocess_check(self, cmd):
        done = subprocess.run(cmd, cwd=self.tree, capture_output=True, text=True, timeout=600,
                              env=scrubbed_env(self.tree, self.work, 0))
        tail = (done.stdout + done.stderr).strip().splitlines()[-25:]
        (self.work / 'logs' / (Path(cmd[1]).stem + '.out')).write_text(done.stdout + done.stderr)
        assert done.returncode == 0, f'exit {done.returncode}: ' + ' | '.join(tail[-6:])
        return tail[-1] if tail else ''

    def restart_persistence(self, stack):
        key = 'c5-restart-' + uuid.uuid4().hex
        run_id = self.submit(stack.base, key)
        st = wait_status(stack.base, run_id)
        assert st['status'] in ('completed', 'completed_with_limits'), st
        before = snapshot(stack.base, run_id)
        stack.stop()
        stack.start_api()
        stack.start_worker()
        after = snapshot(stack.base, run_id)
        diffs = [k for k in before if before[k] != after[k]]
        assert not diffs, f'changed after restart: {diffs}'
        code, text = http(stack.base, '/v1/missions', self.payload, key)
        assert code == 202 and json.loads(text)['run_id'] == run_id, 'idempotency key forgotten after restart'
        self.reference_result = before['/result']
        return f'{run_id} identical across restart; idempotency persisted'

    def worker_down(self, stack):
        stack.stop_worker()
        run_id = self.submit(stack.base)
        time.sleep(2)
        st = wait_status(stack.base, run_id, terminal=False)
        code, _ = http(stack.base, f'/v1/missions/{run_id}/result')
        assert st['status'] == 'queued', f'without a worker status is {st["status"]} (fake progress?)'
        assert code == 409, f'result without worker HTTP {code}'
        stack.start_worker()
        st = wait_status(stack.base, run_id)
        assert st['status'] in ('completed', 'completed_with_limits'), st
        res = http(stack.base, f'/v1/missions/{run_id}/result')
        if hasattr(self, 'reference_result'):
            assert res == self.reference_result, 'identical input produced a different result'

    def worker_kill(self, stack):
        run_id = self.submit(stack.base)
        deadline = time.monotonic() + 20
        killed_in = None
        while time.monotonic() < deadline:
            st = wait_status(stack.base, run_id, terminal=False)
            if st['status'] in ('completed', 'completed_with_limits', 'failed', 'cancelled'):
                break
            if st['status'] != 'queued':
                stack.stop_worker(signal.SIGKILL)
                killed_in = st['status']
                break
            time.sleep(0.01)
        if killed_in is None:
            stack.stop_worker(signal.SIGKILL)
            stack.start_worker()
            return 'NOT_EXERCISED', 'run finished before a non-queued state was observable; kill not mid-run'
        stack.start_worker()
        st = wait_status(stack.base, run_id, timeout=120)
        assert st['status'] in ('completed', 'completed_with_limits'), f'after SIGKILL in {killed_in}: {st}'
        assert st['attempt'] <= 3, f'attempt {st["attempt"]}'
        res = http(stack.base, f'/v1/missions/{run_id}/result')
        if hasattr(self, 'reference_result'):
            assert res == self.reference_result, 'post-crash result differs from clean run'
        return f'killed during {killed_in}; recovered at attempt {st["attempt"]}'

    def ai_flag_without_keys(self):
        stack = self.new_stack('aiflag', ai='true')
        try:
            stack.start_api()
            stack.start_worker()
            code, text = http(stack.base, '/v1/health')
            health = json.loads(text)
            run_id = self.submit(stack.base)
            st = wait_status(stack.base, run_id)
            assert st['status'] in ('completed', 'completed_with_limits'), st
            res = http(stack.base, f'/v1/missions/{run_id}/result')
            if hasattr(self, 'reference_result'):
                assert res == self.reference_result, 'result changed when AI flag on (AI must not affect measurements/scores)'
            return f'health ai_enabled={health.get("ai_enabled")} with no keys'
        finally:
            stack.stop()

    def bad_storage(self):
        stack = self.new_stack('badstore')
        blocker = self.work / 'not-a-directory'
        blocker.write_text('x')
        os.chmod(blocker, 0o400)
        stack.data_dir = blocker / 'nested'
        try:
            stack.start_api(timeout=10)
        except RuntimeError as e:
            return f'refused to start: {str(e)[:120]}'
        try:
            code, text = http(stack.base, '/v1/health')
            assert code == 503, f'health {code} {text[:120]} with unusable TWINSITE_DATA_DIR'
            return 'health 503'
        finally:
            stack.stop()

    def finish(self):
        if self.json_out:
            Path(self.json_out).write_text(json.dumps(self.results, indent=2) + '\n')
        failed = [r for r in self.results if r['status'] in ('FAIL', 'BLOCKED')]
        print(f'\nE2E: {sum(r["status"] == "PASS" for r in self.results)} PASS, '
              f'{sum(r["status"] == "FAIL" for r in self.results)} FAIL, '
              f'{sum(r["status"] == "BLOCKED" for r in self.results)} BLOCKED, '
              f'{sum(r["status"] == "NOT_EXERCISED" for r in self.results)} NOT_EXERCISED. Logs: {self.work}/logs. SYNTHETIC ONLY.')
        return 1 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tree', required=True)
    ap.add_argument('--python', default=sys.executable)
    ap.add_argument('--json')
    args = ap.parse_args()
    return Harness(args.tree, args.python, args.json).run()


if __name__ == '__main__':
    sys.exit(main())
