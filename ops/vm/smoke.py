"""Production smoke test for a deployed TwinSite (through nginx on the VM, or `vite preview` locally).

Checks static serving, SPA deep links, hashed assets, API health, the live data catalog, and one
measured Zagora-Gale run end to end (C2 engine, BLOCK gate, P00-P90, report). Read-only apart
from submitting that one deterministic run. Exit code 0 only when every check passes.

    python ops/vm/smoke.py --base-url http://127.0.0.1:8081 [--expect-security-headers]
"""
import argparse
import json
import re
import sys
import time
import uuid
import urllib.error
import urllib.request


def fetch(base, path, method='GET', body=None, headers=None):
    req = urllib.request.Request(base + path, method=method, headers=headers or {},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expect-security-headers', action='store_true')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    results = []

    def check(name, ok, detail=''):
        results.append(ok)
        print(('PASS ' if ok else 'FAIL ') + name + (f' | {detail}' if detail else ''), flush=True)

    status, headers, body = fetch(base, '/')
    check('index served', status == 200 and b'id="root"' in body, status)
    if args.expect_security_headers:
        lower = {k.lower(): v for k, v in headers.items()}
        check('security headers on index', 'content-security-policy' in lower and lower.get('x-content-type-options') == 'nosniff')
    asset = re.search(rb'/assets/[\w.\-]+\.js', body)
    if asset:
        status, headers, _ = fetch(base, asset.group().decode())
        check('hashed JS asset served', status == 200, asset.group().decode())
    else:
        check('hashed JS asset referenced by index', False)
    for deep in ('/analysis/run-0000000000000000000000000', '/data/earth-zagora-draa?tab=grid', '/docs'):
        status, _, body = fetch(base, deep)
        check(f'SPA deep link {deep}', status == 200 and b'id="root"' in body, status)
    status, _, body = fetch(base, '/v1/health')
    health = json.loads(body) if status == 200 else {}
    check('API health through proxy', health.get('status') == 'ready' and isinstance(health.get('ai_enabled'), bool), health)
    status, _, body = fetch(base, '/v1/data/catalog?limit=100')
    items = json.loads(body).get('items', []) if status == 200 else []
    check('live catalog lists measured sites', {i.get('data_status') for i in items} == {'measured'} and len(items) >= 2, len(items))
    status, _, body = fetch(base, '/v1/data/mars-gale-aeolis/grid')
    check('cleaned grid served and verified', status == 200 and json.loads(body)['display']['nrows'] > 0, status)

    status, _, body = fetch(base, '/v1/missions/measured', 'POST', {'schema_version': '1.0', 'dataset_id': 'zagora-gale-v1'},
                            {'Content-Type': 'application/json', 'Idempotency-Key': 'smoke-' + uuid.uuid4().hex})
    check('measured mission accepted', status == 202, status)
    if status == 202:
        run_id = json.loads(body)['run_id']
        final = {}
        for _ in range(300):
            final = json.loads(fetch(base, f'/v1/missions/{run_id}')[2])
            if final.get('status') in ('completed', 'completed_with_limits', 'failed', 'cancelled'):
                break
            time.sleep(0.2)
        check('worker processed measured run', final.get('status') == 'completed_with_limits', final.get('status'))
        events = json.loads(fetch(base, f'/v1/missions/{run_id}/events?after=0')[2])
        check('P00-P90 events', sorted({e['phase'] for e in events}) == [f'P{i}0' for i in range(10)])
        result = json.loads(fetch(base, f'/v1/missions/{run_id}/result')[2] or b'{}')
        evidence = json.loads(fetch(base, f'/v1/missions/{run_id}/evidence')[2] or b'{}')
        check('C2 engine result, measured', str(result.get('algorithm_version', '')).startswith('twinsite-science/')
              and result.get('data_status') == 'measured', result.get('algorithm_version'))
        check('release gate BLOCK', evidence.get('release_action') == 'BLOCK', evidence.get('blocking_issues'))
        status, _, body = fetch(base, f'/v1/missions/{run_id}/report')
        check('report rendered', status == 200 and b'BLOCK' in body, status)
    print(f'Smoke: {sum(results)}/{len(results)} PASS')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
