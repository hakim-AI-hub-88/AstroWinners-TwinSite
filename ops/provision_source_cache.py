"""Install the published pair's source bytes into a worker cache, verified offline by SHA-256.

The measured workflow and the Data Explorer grid view read pinned objects from
TWINSITE_SOURCE_DATA_DIR by `object_key`. This copies every raw asset and cleaned grid
named in the published pair from one or more existing caches, verifying each file's
SHA-256 before and after copying. It never overwrites, never downloads and needs no credentials.

    python ops/provision_source_cache.py --to /var/lib/twinsite/source-data \
        --from .runtime/data --from .runtime/official-data [--check]
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
PAIR = ROOT / 'backend/twinsite/processing/published/g2_feature_pair.json'


def required_objects():
    pair = json.loads(PAIR.read_text())
    objects = [(a['object_key'], a['sha256']) for a in pair['assets']]
    objects += [(s['provenance']['cleaned_object_key'], s['provenance']['cleaned_sha256']) for s in pair['sites']]
    return objects


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def inside(root, key):
    path = (root / key).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError(f'object key escapes cache root: {key}')
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--to', required=True, type=Path)
    parser.add_argument('--from', dest='sources', action='append', type=Path, default=[])
    parser.add_argument('--check', action='store_true', help='verify the target only; copy nothing')
    args = parser.parse_args()
    target = args.to.resolve()
    problems = 0
    for key, digest in required_objects():
        dest = inside(target, key)
        if dest.exists():
            ok = sha256(dest) == digest
            print(('OK       ' if ok else 'MISMATCH ') + key)
            problems += not ok  # never overwritten: a mismatching file needs human review
            continue
        if args.check:
            print('MISSING  ' + key)
            problems += 1
            continue
        source = next((inside(s.resolve(), key) for s in args.sources
                       if inside(s.resolve(), key).is_file() and sha256(inside(s.resolve(), key)) == digest), None)
        if source is None:
            print('MISSING  ' + key + ' (no verified copy in --from caches)')
            problems += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        partial = dest.with_name(dest.name + '.partial')
        shutil.copyfile(source, partial)
        if sha256(partial) != digest:
            partial.unlink()
            print('COPYFAIL ' + key)
            problems += 1
            continue
        partial.rename(dest)
        print('COPIED   ' + key)
    print(f'{"Source cache ready" if not problems else str(problems) + " object(s) need attention"}: {target}')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
