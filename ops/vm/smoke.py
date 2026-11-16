"""Production smoke test for a deployed TwinSite (nginx on the VM, Vercel in front, or `make dev`).

Checks, in order:
  1. Flask site pages (/ /app /auto /data /resources /sitemap /policy /sitemap.xml) and a /static/ asset
  2. Flask JSON APIs (/api/status, /api/data/datasets, /api/ai/status, /api/auto/missions)
  3. React console at /console/: index, hashed /console/assets/*.js, SPA deep links
  4. Platform API through /v1: health, live data catalog, cleaned grid
  5. One measured Zagora-Gale run end to end (C2 engine, BLOCK gate, P00-P90, report) unless --skip-mission
Read-only apart from submitting that one deterministic run. Exit code 0 only when every check passes.

    python ops/vm/smoke.py --base-url http://127.0.0.1:8081 [--expect-security-headers] [--skip-mission]
    python ops/vm/smoke.py --base-url http://127.0.0.1:5050 --skip-mission        # local `make dev`
"""
import argparse
import json
import re
import sys
import time
import uuid
import urllib.error
import urllib.request

PAGES = ('/', '/app', '/auto', '/data', '/resources', '/sitemap', '/policy')
APIS = ('/api/status', '/api/data/datasets', '/api/ai/status', '/api/auto/missions')
DEEP_LINKS = ('/console/analysis/run-0000000000000000000000000', '/console/data/earth-zagora-draa?tab=grid', '/console/docs')


def fetch(base, path, method='GET', body=None, headers=None, timeout=30):
    req = urllib.request.Request(base + path, method=method, headers={'User-Agent': 'twinsite-smoke', **(headers or {})},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as error:
        return error.code, {k.lower(): v for k, v in error.headers.items()}, error.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
        return 0, {}, str(error).encode()


def as_json(body):
    try:
        return json.loads(body)
    except (ValueError, TypeError):
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--expect-security-headers', action='store_true')
    parser.add_argument('--skip-mission', action='store_true', help='skip the measured end-to-end run')
    args = parser.parse_args()
    base = args.base_url.rstrip('/')
    results = []

    def check(name, ok, detail=''):
        results.append(bool(ok))
        print(('PASS ' if ok else 'FAIL ') + name + (f' | {detail}' if detail != '' else ''), flush=True)

    # 1. Flask pages ------------------------------------------------------------------------
    home_body, home_headers = b'', {}
    for page in PAGES:
        status, headers, body = fetch(base, page)
        check(f'page {page}', status == 200 and 'text/html' in headers.get('content-type', ''), status)
        if page == '/':
            home_body, home_headers = body, headers
    status, headers, body = fetch(base, '/sitemap.xml')
    check('sitemap.xml', status == 200 and b'<urlset' in body, status)
    static = re.search(rb'/static/[\w./\-]+\.(?:css|js)', home_body)
    if static:
        status, _, _ = fetch(base, static.group().decode())
        check('static asset served', status == 200, static.group().decode())
    else:
        check('home page references a /static/ asset', False)

    # 2. Flask JSON APIs ----------------------------------------------------------------------
    for path in APIS:
        status, headers, body = fetch(base, path)
        check(f'api {path}', status == 200 and as_json(body) is not None, status)

    # 3. React console ------------------------------------------------------------------------
    status, headers, body = fetch(base, '/console/')
    check('console index served', status == 200 and b'id="root"' in body, status)
    if args.expect_security_headers:
        check('strict CSP on /console/', "default-src 'self'" in headers.get('content-security-policy', ''))
        check('nosniff on /', home_headers.get('x-content-type-options') == 'nosniff')
    asset = re.search(rb'/console/assets/[\w.\-]+\.js', body)
    if asset:
        status, _, _ = fetch(base, asset.group().decode())
        check('console hashed JS asset served', status == 200, asset.group().decode())
    else:
        check('console index references /console/assets/*.js', False)
    for deep in DEEP_LINKS:
        status, _, body = fetch(base, deep)
        check(f'console deep link {deep}', status == 200 and b'id="root"' in body, status)

    # 4. Platform API through /v1 -------------------------------------------------------------
    status, _, body = fetch(base, '/v1/health')
    health = as_json(body) if status == 200 else {}
    check('platform API health through /v1', (health or {}).get('status') == 'ready'
          and isinstance((health or {}).get('ai_enabled'), bool), health)
    status, _, body = fetch(base, '/v1/data/catalog?limit=100')
    items = (as_json(body) or {}).get('items', []) if status == 200 else []
    check('live catalog lists measured sites', {i.get('data_status') for i in items} == {'measured'} and len(items) >= 2, len(items))
    status, _, body = fetch(base, '/v1/data/mars-gale-aeolis/grid')
    grid = as_json(body) if status == 200 else None
    check('cleaned grid served and verified', bool(grid) and grid.get('display', {}).get('nrows', 0) > 0, status)

    # 5. One measured run end to end -----------------------------------------------------------
    if not args.skip_mission:
        status, _, body = fetch(base, '/v1/missions/measured', 'POST', {'schema_version': '1.0', 'dataset_id': 'zagora-gale-v1'},
                                {'Content-Type': 'application/json', 'Idempotency-Key': 'smoke-' + uuid.uuid4().hex})
        check('measured mission accepted', status == 202, status)
        if status == 202:
            run_id = json.loads(body)['run_id']
            final = {}
            for _ in range(300):
                final = as_json(fetch(base, f'/v1/missions/{run_id}')[2]) or {}
                if final.get('status') in ('completed', 'completed_with_limits', 'failed', 'cancelled'):
                    break
                time.sleep(0.2)
            check('worker processed measured run', final.get('status') == 'completed_with_limits', final.get('status'))
            events = as_json(fetch(base, f'/v1/missions/{run_id}/events?after=0')[2]) or []
            check('P00-P90 events', sorted({e['phase'] for e in events}) == [f'P{i}0' for i in range(10)])
            result = as_json(fetch(base, f'/v1/missions/{run_id}/result')[2]) or {}
            evidence = as_json(fetch(base, f'/v1/missions/{run_id}/evidence')[2]) or {}
            check('C2 engine result, measured', str(result.get('algorithm_version', '')).startswith('twinsite-science/')
                  and result.get('data_status') == 'measured', result.get('algorithm_version'))
            check('release gate BLOCK', evidence.get('release_action') == 'BLOCK', evidence.get('blocking_issues'))
            status, _, body = fetch(base, f'/v1/missions/{run_id}/report')
            check('report rendered', status == 200 and b'BLOCK' in body, status)
    print(f'Smoke: {sum(results)}/{len(results)} PASS')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main())
