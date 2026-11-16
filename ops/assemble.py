"""Assemble a throwaway composite TwinSite tree OUTSIDE the repo for C5 testing.

main is the base; each lane's changes (relative to main) are overlaid on top.
Nothing is checked out, switched, merged or written inside the repository.

  python ops/assemble.py --out <scratch-dir>                # committed lane branches
  python ops/assemble.py --out <scratch-dir> --from-worktrees  # + uncommitted lane work (read-only copy)

Writes <out>/.c5_assembly.json describing the sources, ownership violations
and cross-lane file conflicts. A conflict or ownership violation is reported,
never silently resolved: the later lane in lanes.json order wins and the
report flags it.
"""
import argparse
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

QA_ROOT = Path(__file__).resolve().parents[1]


def git(*args, cwd=None, binary=False):
    out = subprocess.run(['git', *args], cwd=cwd or QA_ROOT, capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode()


def main_checkout():
    # The common dir of a worktree is <main>/.git
    common = Path(git('rev-parse', '--path-format=absolute', '--git-common-dir').strip())
    return common.parent


def extract(tar_bytes, out):
    with tarfile.open(fileobj=io.BytesIO(tar_bytes)) as tar:
        tar.extractall(out, filter='data')


def owned(path, owns):
    return any(path == o.rstrip('/') or path.startswith(o if o.endswith('/') else o + '/') for o in owns)


def lane_changes(branch, worktree, from_worktrees):
    committed = [p for p in git('diff', '--name-only', '--diff-filter=ACMRT', 'main...' + branch).splitlines() if p]
    deleted = [p for p in git('diff', '--name-only', '--diff-filter=D', 'main...' + branch).splitlines() if p]
    dirty = []
    if from_worktrees and worktree and worktree.exists():
        dirty = [p for p in git('ls-files', '-m', '-o', '--exclude-standard', cwd=worktree).splitlines() if p]
    return committed, deleted, dirty


def assemble(out, from_worktrees=False, qa_from_worktree=True):
    out = Path(out).resolve()
    repo = main_checkout()
    if out == repo or repo in out.parents:
        raise SystemExit('Refusing to assemble inside the repository: ' + str(out))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    extract(git('archive', 'main', binary=True), out)
    lanes = json.loads((out / 'contracts/lanes.json').read_text())['lanes']
    worktrees = {'lane/data': 'data', 'lane/science': 'science', 'lane/backend': 'backend',
                 'lane/frontend': 'frontend', 'lane/qa': 'qa'}
    report = {'base': git('rev-parse', 'main').strip(), 'from_worktrees': from_worktrees, 'lanes': [],
              'ownership_violations': [], 'conflicts': [], 'main_checkout': str(repo)}
    writer = {}
    for lane in lanes:
        branch = lane['branch']
        if branch == 'main':
            continue
        wt = repo / '.worktrees' / worktrees.get(branch, '')
        use_wt = from_worktrees or (branch == 'lane/qa' and qa_from_worktree)
        committed, deleted, dirty = lane_changes(branch, wt, use_wt)
        entry = {'id': lane['id'], 'branch': branch, 'head': git('rev-parse', branch).strip(),
                 'ahead_of_main': int(git('rev-list', '--count', 'main..' + branch).strip()),
                 'committed_files': len(committed), 'uncommitted_files': len(dirty), 'deleted_files': deleted}
        if committed:
            extract(git('archive', branch, '--', *committed, binary=True), out)
        for rel in dirty:
            src = wt / rel
            if src.is_file() and not any(part in ('node_modules', '.venv', '__pycache__', 'dist') for part in Path(rel).parts):
                dst = out / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        for rel in sorted(set(committed) | set(dirty)):
            if not owned(rel, lane['owns']):
                report['ownership_violations'].append({'lane': lane['id'], 'path': rel})
            if rel in writer and writer[rel] != lane['id']:
                report['conflicts'].append({'path': rel, 'lanes': [writer[rel], lane['id']]})
            writer[rel] = lane['id']
        report['lanes'].append(entry)
    # The reference/handoff extractions are gitignored; link them read-only from main.
    extracted = repo / 'references/extracted'
    if extracted.exists() and not (out / 'references/extracted').exists():
        os.symlink(extracted, out / 'references/extracted')
    report['references_extracted'] = extracted.exists()
    (out / '.c5_assembly.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    parser.add_argument('--from-worktrees', action='store_true')
    args = parser.parse_args()
    report = assemble(args.out, args.from_worktrees)
    for lane in report['lanes']:
        print(f"{lane['id']} {lane['branch']}: +{lane['ahead_of_main']} commits, "
              f"{lane['committed_files']} committed / {lane['uncommitted_files']} uncommitted files")
    for v in report['ownership_violations']:
        print('OWNERSHIP VIOLATION:', v['lane'], v['path'])
    for c in report['conflicts']:
        print('CONFLICT:', c['path'], c['lanes'])
    print('Composite tree:', Path(args.out).resolve())


if __name__ == '__main__':
    sys.exit(cli())
