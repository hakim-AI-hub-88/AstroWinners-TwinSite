"""Pin contract files after owner review; --check never changes the freeze."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]


def current():
    folder=ROOT/'contracts'
    paths=sorted(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in ('FREEZE.json','.gitkeep'))
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--check',action='store_true');parser.add_argument('--initialize',action='store_true');args=parser.parse_args()
    path=ROOT/'contracts/FREEZE.json'
    if args.initialize:
        if path.exists():
            raise SystemExit('Freeze already exists. Contract amendments require explicit owner review, not automatic refresh.')
        path.write_text(json.dumps({'api_version':'v1','schema_version':'1.0','owner':'C0','sha256':current()},indent=2)+'\n')
    elif args.check:
        if not path.exists() or json.loads(path.read_text())['sha256']!=current():
            raise SystemExit('Contract freeze mismatch; stop merge and request C0 review.')
        print('PASS: contract freeze hashes match')
    else:
        parser.error('Choose --check or --initialize')


if __name__=='__main__':
    main()
