"""Run from a session/terminal permitted to write .git; preserves the current C0 workspace.
Never reset/clean or modify lane worktrees. Makes a source backup plus a Git stash,
merges the exact reviewed lane commits, then restores the assembled C0 files.
Leaves the final C0 integration changes uncommitted for verification and review.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import time

ROOT=Path(__file__).resolve().parents[2]
def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()

if git('branch','--show-current') != 'main': raise SystemExit('Run only on main')
if git('rev-parse','--short=7','HEAD') != '9b8570c':
    raise SystemExit('Main changed: inspect history before resuming. Nothing modified.')
lanes={'data':'c942bb7','science':'5330b4b','backend':'0383322','frontend':'af0c0e5','qa':'8a4ac74'}
for lane,head in lanes.items():
    if git('rev-parse','--short=7','lane/'+lane)!=head:
        raise SystemExit('Lane changed: '+lane+'; review before merging')
paths=set(filter(None,git('ls-files','-co','--exclude-standard','-z').split('\0')))
backup=ROOT/'.runtime/c0'/('merge-backup-'+str(int(time.time())))
backup.mkdir(parents=True)
missing=[]
with tarfile.open(backup/'source.tar','w') as archive:
    for name in sorted(paths):
        path=ROOT/name
        if path.is_file(): archive.add(path,arcname=name,recursive=False)
        elif not path.exists(): missing.append(name)
(backup/'missing.json').write_text(json.dumps(missing))
# Stash keeps originals recoverable, including all untracked lane files. Ignored
# credentials and caches stay in place and are never included in Git or archive.
subprocess.run(['git','stash','push','--include-untracked','-m','C0 integration before lane merges'],cwd=ROOT,check=True)
for lane,head in lanes.items():
    subprocess.run(['git','merge','--no-ff',head,'-m','C0: integrate reviewed lane/'+lane],cwd=ROOT,check=True)
with tarfile.open(backup/'source.tar') as archive:
    archive.extractall(ROOT,filter='data')
for name in missing:
    path=ROOT/name
    if path.is_file(): path.unlink()
print('Five lanes merged; C0 workspace restored. Backup: '+str(backup))
print('Stash preserved. Run make verify; then review and commit only source changes.')
