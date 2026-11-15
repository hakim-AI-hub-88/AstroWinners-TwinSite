"""C5 black-box HTTP acceptance against a RUNNING TwinSite API (not the ARES reference).

Covers what scripts/integration/smoke.py does not. Every check is PASS / FAIL /
NOT_EXERCISED; NOT_EXERCISED never counts as PASS.

  python tests/acceptance/http_contract.py --base-url http://127.0.0.1:8080 [--repo <tree>] [--json out.json]

The repo tree must contain contracts/ (for schemas and the synthetic fixture).
SYNTHETIC ONLY: this submits the frozen synthetic fixture; a pass here is
transport/contract evidence, never scientific evidence.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Strings that must never appear in any public response body or header.
LEAK_PATTERNS = [
    (re.compile(r'(?i)(api[_-]?key|secret|password|passwd|bearer\s+[a-z0-9._-]{8,})\s*["\'=:]\s*["\']?[A-Za-z0-9._/+-]{8,}'), 'credential-like assignment'),
    (re.compile(r'\bsk-[A-Za-z0-9]{16,}'), 'provider secret key'),
    (re.compile(r'\bgsk_[A-Za-z0-9]{16,}'), 'Groq key'),
    (re.compile(r'\bAIza[0-9A-Za-z_-]{20,}'), 'Google API key'),
    (re.compile(r'(?i)X-Amz-(Signature|Credential)|[?&](sig|signature|token|access_token|X-Goog-Signature)='), 'signed URL / capability query'),
    (re.compile(r'(/Users/[^/\s"]+/|/home/[^/\s"]+/|[A-Z]:\\\\Users\\\\)'), 'private filesystem path'),
    (re.compile(r'(?i)EARTHDATA_(USERNAME|PASSWORD|TOKEN)\s*[=:]\s*\S'), 'Earthdata credential'),
    (re.compile(r'(?i)Traceback \(most recent call last\)'), 'stack trace'),
]


def no_nan(text):
    def bad(c):
        raise ValueError('non-finite JSON constant ' + c)
    return json.loads(text, parse_constant=bad)


class Client:
    def __init__(self, base):
        self.base = base.rstrip('/')

    def call(self, path, body=None, key=None, content_type='application/json', raw=None, method=None):
        headers = {}
        data = None
        if raw is not None:
            data = raw
            headers['Content-Type'] = content_type
        elif body is not None:
            data = json.dumps(body, allow_nan=False).encode()
            headers['Content-Type'] = content_type
        if key:
            headers['Idempotency-Key'] = key
        req = Request(self.base + path, data=data, headers=headers, method=method)
        try:
            resp = urlopen(req, timeout=15)
        except HTTPError as err:
            resp = err
        with resp:
            text = resp.read().decode('utf-8', errors='replace')
            return resp.status, dict(resp.headers), text


class Suite:
    def __init__(self, base, repo):
        self.c = Client(base)
        self.repo = Path(repo)
        sys.path.insert(0, str(self.repo))
        from contracts.validation import validate, digest  # noqa: E402
        self.validate, self.digest = validate, digest
        self.payload = json.loads((self.repo / 'contracts/examples/mission.synthetic.json').read_text())
        self.results = []

    def record(self, name, status, detail=''):
        self.results.append({'check': name, 'status': status, 'detail': detail})
        print(f'{status:14} {name}' + (f' — {detail}' if detail else ''), flush=True)

    def check(self, name, fn):
        try:
            outcome = fn()
            if isinstance(outcome, tuple):
                self.record(name, *outcome)
            else:
                self.record(name, 'PASS', outcome or '')
        except AssertionError as err:
            self.record(name, 'FAIL', str(err))
        except (URLError, OSError) as err:
            self.record(name, 'FAIL', 'transport: ' + type(err).__name__ + ' ' + str(err)[:200])
        except Exception as err:  # unexpected harness/server shape: still a failure, never a pass
            self.record(name, 'FAIL', type(err).__name__ + ': ' + str(err)[:300])

    def leaks(self, *texts):
        found = []
        for text in texts:
            for pattern, label in LEAK_PATTERNS:
                m = pattern.search(text or '')
                if m:
                    found.append(f'{label}: {m.group(0)[:60]!r}')
        return found

    def error_body(self, text):
        body = no_nan(text)
        self.validate('error', body)
        return body

    # ------------------------------------------------------------------ checks
    def health(self):
        code, headers, text = self.c.call('/v1/health')
        assert code == 200, f'health HTTP {code}'
        body = no_nan(text)
        self.validate('health', body)
        assert body['status'] == 'ready', body
        assert body['ai_enabled'] is False, 'ai_enabled must be false in default/AI-free mode'
        assert body['uploads_enabled'] is False, 'uploads must be disabled by default'
        leaks = self.leaks(text, json.dumps(headers))
        assert not leaks, leaks
        return f'{body}'

    def missing_key(self):
        code, _, text = self.c.call('/v1/missions', self.payload)
        assert code == 400, f'missing Idempotency-Key expected 400, got {code}'
        self.error_body(text)

    def oversize(self):
        # A server may answer 413 from Content-Length alone and close early; read the status
        # before streaming the body so an early close is not misread as a failure.
        import http.client
        from urllib.parse import urlparse
        u = urlparse(self.c.base)
        conn = http.client.HTTPConnection(u.hostname, u.port, timeout=15)
        size = 1_000_100
        conn.putrequest('POST', '/v1/missions')
        conn.putheader('Content-Type', 'application/json')
        conn.putheader('Idempotency-Key', 'c5-oversize-' + uuid.uuid4().hex)
        conn.putheader('Content-Length', str(size))
        conn.endheaders()
        early = True
        try:
            conn.sock.settimeout(2)
            resp = conn.getresponse()
        except (TimeoutError, OSError):
            early = False
            conn.sock.settimeout(15)
            try:
                conn.send(b'{"pad":"' + b'x' * (size - 10) + b'"}')
            except OSError:
                pass
            resp = conn.getresponse()
        code = resp.status
        conn.close()
        assert code == 413, f'>1,000,000-byte body expected 413, got {code}'
        return 'PASS', '413 sent from Content-Length before body' if early else '413 after body'

    def bad_json(self):
        code, _, _ = self.c.call('/v1/missions', raw=b'{"schema_version":', key='c5-badjson-' + uuid.uuid4().hex)
        assert code in (400, 422), f'malformed JSON expected 400/422, got {code}'

    def relabel_measured(self):
        # Client-asserted data_status=measured must not be trusted as science.
        p = copy.deepcopy(self.payload)
        p['data_status'] = 'measured'
        code, _, text = self.c.call('/v1/missions', p, key='c5-relabel-' + uuid.uuid4().hex)
        if code in (400, 422):
            return 'PASS', f'rejected up front with {code}'
        assert code == 202, f'unexpected {code}'
        run_id = no_nan(text)['run_id']
        self.wait_terminal(run_id)
        code, _, ev = self.c.call(f'/v1/missions/{run_id}/evidence')
        if code == 409:
            return 'PASS', 'run did not commit (blocked)'
        assert code == 200, f'evidence HTTP {code}'
        ev = no_nan(ev)
        assert ev['release_action'] == 'BLOCK', f'synthetic values relabelled measured were released: {ev["release_action"]}'
        assert ev['strict_gate_status'] != 'PASS', 'strict gate PASS on relabelled synthetic input'
        return 'PASS', f'evidence release_action=BLOCK, issues={ev["blocking_issues"][:4]}'

    def wait_terminal(self, run_id, timeout=60):
        deadline = time.monotonic() + timeout
        while True:
            code, _, text = self.c.call(f'/v1/missions/{run_id}')
            assert code == 200, f'status HTTP {code}'
            st = no_nan(text)
            if st['status'] in ('completed', 'completed_with_limits', 'failed', 'cancelled'):
                return st
            assert time.monotonic() < deadline, f'run {run_id} stuck in {st["status"]} > {timeout}s'
            time.sleep(0.2)

    def lifecycle(self):
        key = 'c5-life-' + uuid.uuid4().hex
        code, _, text = self.c.call('/v1/missions', self.payload, key=key)
        assert code == 202, f'submit HTTP {code}: {text[:200]}'
        acc = no_nan(text)
        self.validate('mission_accepted', acc)
        assert acc['id'] == acc['run_id'], 'acceptance id != run_id'
        assert acc['status'] == 'queued', 'acceptance status must be queued'
        run_id = acc['run_id']
        self.run_id = run_id
        # Early result must be 409 (unless the worker is extremely fast).
        code, _, early = self.c.call(f'/v1/missions/{run_id}/result')
        early_note = f'early result HTTP {code}'
        assert code in (200, 409), early_note
        if code == 409:
            self.error_body(early)
        # Identical retry returns identical acceptance payload.
        code, _, replay = self.c.call('/v1/missions', self.payload, key=key)
        assert code == 202 and no_nan(replay) == acc, 'idempotent replay differs from original acceptance'
        st = self.wait_terminal(run_id)
        self.validate('mission_status', st)
        assert st['id'] == st['run_id'] == run_id, 'status id/run_id disagree'
        assert st['input_sha256'] == self.digest(self.payload), 'status input_sha256 != canonical SHA-256 of original input'
        assert st['status'] in ('completed', 'completed_with_limits'), f'synthetic fixture run ended {st["status"]}: {st["error"]}'
        assert st['attempt'] <= 3, f'attempt {st["attempt"]} exceeds max 3'
        self.status = st
        return f'run {run_id} -> {st["status"]}; {early_note}'

    def need_run(self):
        if not getattr(self, 'run_id', None):
            raise AssertionError('lifecycle failed; dependent check cannot run')
        return self.run_id

    def result(self):
        run_id = self.need_run()
        code, headers, text = self.c.call(f'/v1/missions/{run_id}/result')
        assert code == 200, f'result HTTP {code}'
        assert 'application/json' in headers.get('Content-Type', ''), headers.get('Content-Type')
        res = no_nan(text)
        self.validate('mission_result', res)
        assert res['data_status'] == 'synthetic', 'synthetic input produced non-synthetic result'
        assert res['input_sha256'] == self.digest(self.payload), 'result input_sha256 != canonical original-input hash'
        code2, _, text2 = self.c.call(f'/v1/missions/{run_id}/result')
        assert text2 == text, 'result body changed between two GETs'
        leaks = self.leaks(text)
        assert not leaks, leaks
        self.result_body = res

    def evidence(self):
        run_id = self.need_run()
        code, _, text = self.c.call(f'/v1/missions/{run_id}/evidence')
        assert code == 200, f'evidence HTTP {code}'
        ev = no_nan(text)
        self.validate('release_evidence', ev)
        assert ev['run_id'] == run_id, 'evidence run_id mismatch'
        assert ev['input_sha256'] == self.digest(self.payload), 'evidence input_sha256 mismatch'
        assert ev['data_status'] == 'synthetic', 'synthetic run evidence not marked synthetic'
        assert ev['release_action'] == 'BLOCK', f'synthetic run release_action={ev["release_action"]} (must be BLOCK)'
        assert ev['strict_gate_status'] != 'PASS', 'synthetic run strict_gate_status PASS'
        if self.status.get('source_snapshot_id') is not None:
            assert self.status['source_snapshot_id'] == ev['source_snapshot_id'], 'status/evidence source_snapshot_id disagree'
        leaks = self.leaks(text)
        assert not leaks, leaks
        return f'release_action=BLOCK snapshot={ev["source_snapshot_id"]}'

    def events(self):
        run_id = self.need_run()
        for bad in ('-1', 'oops', '1.5'):
            code, _, _ = self.c.call(f'/v1/missions/{run_id}/events?after={bad}')
            assert code == 400, f'events?after={bad} expected 400, got {code}'
        code, _, text = self.c.call(f'/v1/missions/{run_id}/events?after=0')
        assert code == 200
        page = no_nan(text)
        self.validate('events', page)
        assert 0 < len(page) <= 200, f'page size {len(page)}'
        seqs = [e['sequence'] for e in page]
        assert seqs == sorted(set(seqs)) and seqs[0] > 0, f'sequence not strictly ascending/positive: {seqs[:10]}'
        assert all(e['mission_id'] == run_id for e in page), 'event mission_id != run_id'
        phases = [e['phase'] for e in page]
        assert 'P00' in phases or seqs[0] > 1, 'first page lacks P00 start event'
        ts = [e['timestamp'] for e in page]
        assert ts == sorted(ts), 'event timestamps go backwards'
        terminal = [e for e in page if e['state'] in ('succeeded', 'failed', 'cancelled', 'quarantined')]
        assert terminal, 'no terminal task state in committed events'
        mid = seqs[len(seqs) // 2]
        code, _, tail = self.c.call(f'/v1/missions/{run_id}/events?after={mid}')
        tail = no_nan(tail)
        assert all(e['sequence'] > mid for e in tail), 'cursor returned sequence <= after'
        for e in page:
            if e['total_units'] is None:
                pass  # unknown total: completed_units is a count, not a percentage
            else:
                assert e['completed_units'] <= e['total_units'], f'completed>{e["total_units"]} at seq {e["sequence"]}'
        leaks = self.leaks(text)
        assert not leaks, leaks
        return f'{len(page)} events, phases {sorted(set(phases))}'

    def report(self):
        run_id = self.need_run()
        code, headers, text = self.c.call(f'/v1/missions/{run_id}/report')
        assert code == 200, f'report HTTP {code}'
        ctype = headers.get('Content-Type', '').lower().replace(' ', '')
        assert ctype == 'text/html;charset=utf-8', f'report content-type {ctype!r}'
        assert 'synthetic' in text.lower(), 'report not visibly synthetic'
        leaks = self.leaks(text)
        assert not leaks, leaks

    def report_escapes(self):
        p = copy.deepcopy(self.payload)
        marker = 'c5xss' + uuid.uuid4().hex[:8]
        p['sites'][0]['name'] = f'<script>window.{marker}=1</script><img src=x onerror=alert(1)>'
        code, _, text = self.c.call('/v1/missions', p, key='c5-xss-' + uuid.uuid4().hex)
        if code in (400, 422):
            return 'PASS', f'markup in site name rejected with {code}'
        assert code == 202, f'submit HTTP {code}'
        run_id = no_nan(text)['run_id']
        st = self.wait_terminal(run_id)
        code, _, html = self.c.call(f'/v1/missions/{run_id}/report')
        if code == 409:
            return 'NOT_EXERCISED', f'XSS run ended {st["status"]}; no report'
        assert code == 200
        assert f'<script>window.{marker}' not in html, 'UNESCAPED <script> from user input in report (XSS)'
        assert '<img src=x onerror' not in html, 'UNESCAPED onerror attribute in report (XSS)'

    def not_found(self):
        ghost = 'c5-' + uuid.uuid4().hex
        for suffix in ('', '/events?after=0', '/result', '/evidence', '/report'):
            code, _, text = self.c.call(f'/v1/missions/{ghost}{suffix}')
            assert code == 404, f'unknown run {suffix or "/"} expected 404, got {code}'
        code, _, _ = self.c.call('/v1/definitely-not-a-route')
        assert code == 404, f'unknown API route expected 404, got {code}'
        code, _, _ = self.c.call('/v1/missions/../../etc/passwd')
        assert code in (400, 404), f'path traversal probe returned {code}'

    def get_does_not_create(self):
        # GET on the collection must not start a job (405/404 are fine; 2xx with a new run is not).
        code, _, text = self.c.call('/v1/missions')
        assert code in (404, 405) or not ('run_id' in text and 'queued' in text), 'GET /v1/missions appears to create a run'
        return f'GET /v1/missions -> {code}'

    def uploads_disabled(self):
        code, _, text = self.c.call('/v1/uploads', raw=b'not-really-a-file', content_type='application/octet-stream',
                                    key='c5-upload-' + uuid.uuid4().hex)
        assert not (200 <= code < 300), f'uploads accepted ({code}) while uploads_enabled=false'
        return f'POST /v1/uploads -> {code}'

    def ai_route_disabled(self):
        statuses = []
        for path in ('/v1/ai', '/v1/ai/requests', '/v1/missions/' + self.need_run() + '/ai'):
            code, _, _ = self.c.call(path, body={'provider': 'any', 'purpose': 'narrative_summary'},
                                     key='c5-ai-' + uuid.uuid4().hex)
            statuses.append(code)
            assert not (200 <= code < 300), f'{path} accepted an AI request ({code}) with AI disabled'
        return f'AI probes -> {statuses}'

    def data_explorer(self):
        code, _, text = self.c.call('/v1/data/catalog?limit=10')
        if code == 501 or code == 404:
            return 'NOT_EXERCISED', f'/v1/data/catalog -> {code} (reserved G3 route not implemented)'
        assert code == 200, f'catalog HTTP {code}'
        for bad in ('0', '101', '-5', 'x'):
            c2, _, _ = self.c.call(f'/v1/data/catalog?limit={bad}')
            assert c2 in (400, 422), f'catalog limit={bad} expected 400/422, got {c2}'
        c3, _, _ = self.c.call('/v1/data/compare', body={'sql': 'SELECT * FROM pg_user; DROP TABLE missions;'},
                               key='c5-sql-' + uuid.uuid4().hex)
        assert c3 in (400, 404, 405, 415, 422, 501), f'SQL-shaped compare request returned {c3}'
        leaks = self.leaks(text)
        assert not leaks, leaks
        return 'catalog bounds enforced, SQL payload refused'

    def run_all(self):
        self.check('health: schema, AI off, uploads off, no leaks', self.health)
        self.check('POST without Idempotency-Key -> 400 error body', self.missing_key)
        self.check('POST > 1,000,000 bytes -> 413', self.oversize)
        self.check('POST malformed JSON -> 400/422', self.bad_json)
        self.check('lifecycle: 202, id==run_id, replay, terminal, canonical input hash', self.lifecycle)
        self.check('result: schema, synthetic, input hash, stable bytes', self.result)
        self.check('evidence sidecar: synthetic => BLOCK, hashes agree', self.evidence)
        self.check('events: cursor 400s, <=200, ascending, phases, no leaks', self.events)
        self.check('report: text/html;charset=utf-8, visibly synthetic', self.report)
        self.check('report escapes user markup (XSS)', self.report_escapes)
        self.check('client data_status=measured on synthetic values is not released', self.relabel_measured)
        self.check('unknown run/route -> 404', self.not_found)
        self.check('GET never creates a job', self.get_does_not_create)
        self.check('uploads disabled by default', self.uploads_disabled)
        self.check('AI routes refuse with AI disabled (no external transmission)', self.ai_route_disabled)
        self.check('data explorer bounds / no SQL (G3)', self.data_explorer)
        return self.results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base-url', default='http://127.0.0.1:8080')
    ap.add_argument('--repo', default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument('--json')
    args = ap.parse_args()
    results = Suite(args.base_url, args.repo).run_all()
    failed = [r for r in results if r['status'] == 'FAIL']
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2) + '\n')
    print(f'\nHTTP acceptance: {sum(r["status"] == "PASS" for r in results)} PASS, {len(failed)} FAIL, '
          f'{sum(r["status"] == "NOT_EXERCISED" for r in results)} NOT_EXERCISED. SYNTHETIC ONLY.')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
