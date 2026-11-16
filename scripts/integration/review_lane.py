"""Read-only merge preflight. Does not merge or erase another lane's changes."""
import argparse
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]


def main():
    lanes=json.loads((ROOT/'contracts/lanes.json').read_text())['lanes']
    parser=argparse.ArgumentParser();parser.add_argument('branch',choices=[l['branch'] for l in lanes if l['id']!='C0']);args=parser.parse_args()
    lane=next(l for l in lanes if l['branch']==args.branch)
    result=subprocess.run(['git','diff','--name-only','-z','main...'+args.branch],cwd=ROOT,check=True,capture_output=True)
    paths=[p for p in result.stdout.decode().split('\0') if p]
    violations=[p for p in paths if not any(p.startswith(prefix) for prefix in lane['owns'])]
    if violations:
        raise SystemExit('Cross-owner changes require review: '+', '.join(violations))
    if not paths:
        raise SystemExit('No lane changes to integrate.')
    print(f"PASS: {lane['id']} changed {len(paths)} files inside its ownership. Review diff, run candidate checks, then C0 may merge.")


if __name__=='__main__':
    main()
