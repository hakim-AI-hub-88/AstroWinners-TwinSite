"""Verify the actual current checkout, including C0 edits, without rebuilding lane overlays."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '.runtime/c0/verification'
if OUT.exists():
    archive = OUT.with_name('verification-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    shutil.copytree(OUT, archive)
OUT.mkdir(parents=True, exist_ok=True)
ENV = dict(os.environ, PYTHONPATH=str(ROOT / 'backend') + os.pathsep + str(ROOT))
# Verification never needs Earthdata credentials: disable the repo .env secret file unless the
# caller explicitly points at one, and drop any token inherited from the shell.
ENV.setdefault('TWINSITE_SECRET_ENV_FILE', str(ROOT / '.runtime/no-secrets.env'))
ENV.pop('EARTHDATA_TOKEN', None)
# Verification is offline and AI-free: no provider credentials, no inference spend.
ENV['TWINSITE_AI_SECRET_ENV_FILE'] = str(ROOT / '.runtime/no-ai-secrets.env')
for _name in [n for n in ENV if n.startswith(('CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_ACCOUNT_ID', 'GOOGLE_API_KEY', 'GROQ_API_KEY',
                                            'MISTRAL_API_KEY', 'NVIDIA_NIM_API_KEY', 'OLLAMA_API_KEY', 'OPENROUTER_API_KEY',
                                            'ELEVENLABS_API_KEY'))]:
    ENV.pop(_name)
results = []

def run(name, command, cwd=ROOT):
    with (OUT / (name + '.log')).open('w') as log:
        p = subprocess.run(command, cwd=cwd, env=ENV, stdout=log, stderr=subprocess.STDOUT)
    status = 'PASS' if p.returncode == 0 else 'FAIL'
    results.append({'check':name,'status':status,'exit_code':p.returncode})
    print(name + ': ' + status, flush=True)

py=sys.executable
run('schemas',[py,'scripts/integration/validate_contracts.py'])
run('types',[py,'scripts/integration/generate_types.py','--check'])
for name, directory in [('integration','scripts/integration/tests'),('science','backend/tests/science'),('data','backend/tests/data'),('c0','backend/tests/integration'),('qa_negative_controls','tests/acceptance'),('ai_router_agents_gateway','backend/tests/ai')]:
    run(name,[py,'-m','unittest','discover','-s',directory,'-p','test_*.py','-v'])
run('store_worker',[py,'-m','unittest','backend.tests.api.test_backend.StoreTests','backend.tests.api.test_backend.WorkerTests','-v'])
for name, command in [('frontend_typecheck',['npm','run','typecheck']),('frontend_build',['npm','run','build']),('frontend_tests',['npm','test'])]:
    run(name, command, ROOT / 'frontend')
try:
    with socket.socket() as probe: probe.bind(('127.0.0.1',0))
except PermissionError:
    for name in ('backend_http','c5_http_restart_e2e','measured_http_restart_e2e','browser_smoke'):
        results.append({'check':name,'status':'BLOCKED','reason':'Session prohibits local socket binding'})
        (OUT / (name + '.log')).write_text('BLOCKED: Session prohibits local socket binding; prior results are archived, not current verification.\n')
        print(name + ': BLOCKED (local socket binding prohibited)', flush=True)
else:
    run('backend_http',[py,'-m','unittest','backend.tests.api.test_backend.HttpTests','-v'])
    run('c5_http_restart_e2e',[py,'tests/e2e/run_stack.py','--tree',str(ROOT),'--python',py,'--json',str(OUT/'e2e.json')])
    run('measured_http_restart_e2e',[py,'tests/e2e/measured_live.py','--json',str(OUT/'measured-e2e.json')])
    results.append({'check':'browser_smoke','status':'BLOCKED','reason':'Requires separate browser verification'})
# Scan the distributable source and built browser assets, not ignored local secrets/caches.
with tempfile.TemporaryDirectory(prefix='twinsite-scan-') as tmp:
    stage=Path(tmp)
    paths=subprocess.check_output(['git','ls-files','-co','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    for name in set(filter(None,paths)):
        source=ROOT/name
        if source.is_file():
            dest=stage/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
    if (ROOT/'frontend/dist').exists(): shutil.copytree(ROOT/'frontend/dist',stage/'browser-build')
    run('secret_scan',[py,'ops/secret_scan.py',str(stage)])
if next(r for r in results if r['check'] == 'c0')['status'] == 'PASS':
    run('c5_measured_provenance',[py,'tests/acceptance/provenance_check.py','--evidence','.runtime/c0/measured-evidence.json','--result','.runtime/c0/measured-result.json','--artifact-root',ENV.get('TWINSITE_SOURCE_DATA_DIR',str(ROOT/'.runtime/data')),'--repo',str(ROOT),'--json',str(OUT/'provenance.json')])
else:
    results.append({'check':'c5_measured_provenance','status':'BLOCKED','reason':'C0 did not regenerate current evidence; stale evidence is not verified'})
    (OUT / 'c5_measured_provenance.log').write_text('BLOCKED: C0 did not regenerate current evidence.\n')
(OUT/'summary.json').write_text(json.dumps(results,indent=2)+'\n')
print('Summary: '+str(OUT/'summary.json'))
sys.exit(1 if any(r['status']!='PASS' for r in results) else 0)
