"""One terminal, supervised API + worker + UI. No implicit reference fallback."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT/'references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--reference',action='store_true');parser.add_argument('--port',type=int,default=8080);parser.add_argument('--no-ai',action='store_true',help='Simple Analysis only');args=parser.parse_args()
    if not 1024 <= args.port <= 65535:
        raise SystemExit('Use an unprivileged TCP port (1024–65535).')
    env=os.environ.copy()
    # AI-Powered Analysis is the default when the protected free-provider secret file exists
    # (created by ops/migrate_vesper_credentials.py). Uploads stay disabled.
    secrets_file=ROOT/'.runtime/secrets/ai-providers.env'
    ai=not args.no_ai and secrets_file.exists()
    env.update(TWINSITE_AI_ENABLED='true' if ai else 'false',TWINSITE_UPLOADS_ENABLED='false',TWINSITE_API_HOST='127.0.0.1',TWINSITE_API_PORT=str(args.port))
    if ai:
        env['TWINSITE_AI_SECRET_ENV_FILE']=str(secrets_file)
    print('AI-Powered Analysis: '+('ON (free providers only)' if ai else 'OFF (Simple Analysis only)'),flush=True)
    runtime=ROOT/'.runtime';runtime.mkdir(exist_ok=True)
    env['TWINSITE_DATA_DIR']=str(runtime)
    if args.reference:
        if not (REFERENCE/'ares/server.py').exists():
            raise SystemExit('Run make bootstrap first.')
        db=str(runtime/'reference-synthetic.sqlite')
        commands=[([sys.executable,'-m','ares','serve','--db',db,'--port',str(args.port)],REFERENCE),([sys.executable,'-m','ares','worker','--db',db],REFERENCE)]
        print('REFERENCE ONLY: synthetic scoring and historical ARES UI; no NASA science release.',flush=True)
    else:
        missing=[p for p in ['backend/twinsite/api/__main__.py','backend/twinsite/jobs/__main__.py','frontend/package.json'] if not (ROOT/p).exists()]
        if missing:
            raise SystemExit('G1 BLOCKED: owner entry points missing: '+', '.join(missing)+'. Use make reference-dev only for the historical synthetic baseline.')
        env['PYTHONPATH']=os.pathsep.join([str(ROOT/'backend'),str(ROOT)])
        commands=[([sys.executable,'-m','twinsite.api'],ROOT),([sys.executable,'-m','twinsite.jobs'],ROOT),(['npm','run','dev','--','--host','127.0.0.1'],ROOT/'frontend')]
    children=[]
    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop)
    try:
        for command,cwd in commands:
            children.append(subprocess.Popen(command,cwd=cwd,env=env,start_new_session=True))
        print(f'API: http://127.0.0.1:{args.port} — Ctrl+C stops all child processes.',flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(.25)
        raise SystemExit('A service exited; shutting down the stack. See preceding service output.')
    except KeyboardInterrupt:
        pass
    finally:
        for process in children:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
        for process in children:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL);process.wait()


if __name__=='__main__':
    main()
