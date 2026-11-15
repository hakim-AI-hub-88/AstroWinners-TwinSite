"""Idempotent initialization. Run outside restricted sandbox if .git is read-only."""
from pathlib import Path
import json
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def git(*args):
    return subprocess.run(['git', *args], cwd=ROOT, check=True, text=True, capture_output=True).stdout


def main():
    if not (ROOT / '.git').exists():
        git('init', '-b', 'main')
    if git('branch', '--show-current').strip() != 'main':
        raise SystemExit('Run from main; no automatic branch switch.')
    # Only explicitly approved integration scaffolding, never blanket git add .
    if subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT, capture_output=True).returncode:
        for key in ('user.name', 'user.email'):
            if subprocess.run(['git', 'config', '--get', key], cwd=ROOT, capture_output=True).returncode:
                raise SystemExit(f'Set {key} locally before creating the initial commit; identity is not invented.')
        paths = ['.gitignore', '.env.example', 'Makefile', 'README.md', 'INTEGRATION_STATUS.md',
                 'requirements-integration.txt', 'contracts', 'scripts/integration',
                 'references/SNAPSHOT.json', 'references/execution-kit',
                 'references/TwinSite_Engineering_Handoff.zip',
                 'references/ARES_NASA_Feasibility_Architecture.zip',
                 'references/TwinSite_Execution_Kit_2026-11-15.zip']
        paths += [str(p.relative_to(ROOT)) for base in ['backend','frontend','tests','ops','docs']
                  for p in (ROOT/base).rglob('.gitkeep')]
        git('add', '--', *paths)
        git('commit', '-m', 'Initialize TwinSite integration contracts and lane scaffolding')
    lanes = json.loads((ROOT / 'contracts/lanes.json').read_text())['lanes']
    registered = git('worktree', 'list', '--porcelain')
    for lane in lanes:
        if lane['id'] == 'C0':
            continue
        target = ROOT / '.worktrees' / lane['branch'].split('/')[-1]
        if f'worktree {target}\n' in registered:
            continue
        if target.exists():
            raise SystemExit(f'Unregistered directory exists; inspect manually: {target}')
        exists = subprocess.run(['git','show-ref','--verify','--quiet','refs/heads/'+lane['branch']],cwd=ROOT).returncode == 0
        git('worktree','add', *([] if exists else ['-b',lane['branch']]), str(target), lane['branch'] if exists else 'main')
        print(f"{lane['id']}: {lane['branch']} -> {target}")
    print('Only C0 merges into main; no owner code was modified.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr or 'Git initialization failed')
