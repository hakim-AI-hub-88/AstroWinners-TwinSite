"""Independently re-download the published MOLA MEGDR assets from the NASA PDS Geosciences Node.

Labels are fetched whole. Image assets are subsets, so the exact rows are read with HTTP Range
requests using the window recorded in the site provenance, then hashed and compared with the
recorded SHA-256. Public data only: no credentials are read or sent, and only the PDS host is allowed.

    python scripts/integration/verify_mola_origin.py [--json .runtime/c0/mola-origin-verification.json]
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend'))
from twinsite.sources.fetch import ssl_context  # noqa: E402 — same verified TLS context as acquisition
PAIR = ROOT / 'backend/twinsite/processing/published/g2_feature_pair.json'
HOST = 'pds-geosciences.wustl.edu'
WINDOW = re.compile(r'subset lines (\d+)\.\.(\d+), samples (\d+)\.\.(\d+) of (\d+)x(\d+)')
AGENT = {'User-Agent': 'twinsite-qa-provenance/1.0'}


def get(url, byte_range=None):
    if urllib.parse.urlsplit(url).hostname != HOST or not url.startswith('https://'):
        raise ValueError(f'refusing non-PDS URL {url}')
    headers = dict(AGENT)
    if byte_range:
        headers['Range'] = 'bytes=%d-%d' % byte_range
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60, context=ssl_context()) as resp:
        if byte_range and resp.status != 206:
            raise ValueError(f'{url}: server ignored Range request ({resp.status})')
        return resp.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', default=str(ROOT / '.runtime/c0/mola-origin-verification.json'))
    args = parser.parse_args()
    pair = json.loads(PAIR.read_text())
    mars = next(s for s in pair['sites'] if s['body'] == 'Mars')
    window = next(m for t in mars['provenance']['transformations'] if (m := WINDOW.search(str(t))))
    l0, l1, s0, s1, _lines, samples = map(int, window.groups())
    results = []
    for asset in (a for a in pair['assets'] if a['body'] == 'Mars'):
        url = asset['source_url']
        if url.endswith('.lbl'):
            data = get(url)
            method = 'full label download'
        else:
            # Bytes per sample follow from the recorded subset size.
            bps = asset['byte_size'] // ((l1 - l0 + 1) * (s1 - s0 + 1))
            if bps not in (1, 2) or bps * (l1 - l0 + 1) * (s1 - s0 + 1) != asset['byte_size']:
                raise ValueError(f'{asset["asset_id"]}: subset size does not match the recorded window')
            data = b''.join(get(url, ((line * samples + s0) * bps, (line * samples + s1 + 1) * bps - 1))
                            for line in range(l0, l1 + 1))
            method = f'HTTP Range rows {l0}..{l1}, samples {s0}..{s1}, {bps} byte(s)/sample'
        digest = hashlib.sha256(data).hexdigest()
        results.append({'asset_id': asset['asset_id'], 'source_url': url, 'method': method, 'bytes': len(data),
                        'sha256': digest, 'recorded_sha256': asset['sha256'], 'matches': digest == asset['sha256']})
        print(('MATCH    ' if digest == asset['sha256'] else 'MISMATCH ') + asset['asset_id'], flush=True)
    report = {'host': HOST, 'credentials_used': False, 'assets': results,
              'all_match': all(r['matches'] for r in results) and bool(results)}
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(report, indent=2) + '\n')
    print(f'{sum(r["matches"] for r in results)}/{len(results)} Mars assets match NASA PDS origin bytes. Report: {args.json}')
    return 0 if report['all_match'] else 1


if __name__ == '__main__':
    sys.exit(main())
