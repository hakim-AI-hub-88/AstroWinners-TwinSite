"""One terminal, the whole TwinSite stack: Flask web (5050) + platform API (8080) + worker.

    python scripts/integration/dev.py                      # web + api + worker
    python scripts/integration/dev.py --only web           # Flask only (proxies /v1 to TWINSITE_API_URL)
    python scripts/integration/dev.py --web-port 5051 --api-port 8091 --vite
    python scripts/integration/dev.py --reference          # historical synthetic ARES baseline (API + worker)

Reads an optional repo-root .env (KEY=VALUE; variables already set in the shell win).
Every child gets PYTHONPATH=backend:. and the same TWINSITE_DATA_DIR. Ctrl+C stops all children;
if any child exits, the whole stack is shut down. No implicit reference fallback.
"""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT/'references/extracted/ARES_NASA_Feasibility_Architecture/ARES/implementation'
SERVICES = ('web', 'api', 'worker')
AI_KEY_PREFIXES = ('GROQ_API_KEY', 'CLOUDFLARE_API_TOKEN', 'GOOGLE_API_KEY', 'MISTRAL_API_KEY', 'OPENROUTER_API_KEY',
                   'NVIDIA_NIM_API_KEY')


def load_dotenv(path):
    """Minimal KEY=VALUE reader; never overrides variables that are already set. Values are never printed."""
    if not path.is_file():
        return 0
    count = 0
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.removeprefix('export ').split('=', 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value
            count += 1
    return count


def port_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
        except OSError:
            return False
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--reference', action='store_true', help='historical synthetic ARES API + worker only')
    parser.add_argument('--only', default=','.join(SERVICES), help='comma list of services: web,api,worker')
    parser.add_argument('--web-port', type=int, default=None, help='Flask port (default $APP_PORT or 5050)')
    parser.add_argument('--api-port', '--port', dest='api_port', type=int, default=None,
                        help='platform API port (default $TWINSITE_API_PORT or 8080)')
    parser.add_argument('--vite', action='store_true', help='also start the Vite dev server for the console (5173)')
    parser.add_argument('--no-ai', action='store_true', help='Simple Analysis only')
    args = parser.parse_args()

    loaded = load_dotenv(ROOT/'.env')
    if loaded:
        print(f'.env: {loaded} variable(s) loaded (values not shown)', flush=True)
    web_port = args.web_port or int(os.environ.get('APP_PORT') or 5050)
    api_port = args.api_port or int(os.environ.get('TWINSITE_API_PORT') or 8080)
    for port in (web_port, api_port):
        if not 1024 <= port <= 65535:
            raise SystemExit('Use an unprivileged TCP port (1024-65535).')
    only = {s.strip() for s in args.only.split(',') if s.strip()}
    unknown = only - set(SERVICES)
    if unknown:
        raise SystemExit(f'Unknown service(s): {", ".join(sorted(unknown))}. Choose from {", ".join(SERVICES)}.')

    env = os.environ.copy()
    runtime = ROOT/'.runtime'
    runtime.mkdir(exist_ok=True)
    env.setdefault('TWINSITE_DATA_DIR', str(runtime))
    # AI: the free-provider secret file (0600) or provider keys in the environment / .env enable it.
    secrets_file = runtime/'secrets/ai-providers.env'
    if 'TWINSITE_AI_SECRET_ENV_FILE' not in env and secrets_file.exists():
        env['TWINSITE_AI_SECRET_ENV_FILE'] = str(secrets_file)
    has_keys = any(k.startswith(AI_KEY_PREFIXES) and v.strip() for k, v in env.items())
    if args.no_ai:
        env['TWINSITE_AI_ENABLED'] = 'false'
    elif 'TWINSITE_AI_ENABLED' not in os.environ:
        env['TWINSITE_AI_ENABLED'] = 'true' if ('TWINSITE_AI_SECRET_ENV_FILE' in env or has_keys) else 'false'
    ai = env['TWINSITE_AI_ENABLED'].lower() in ('1', 'true', 'yes', 'on')
    env.update(TWINSITE_UPLOADS_ENABLED='false', TWINSITE_API_HOST='127.0.0.1', TWINSITE_API_PORT=str(api_port),
               APP_HOST=env.get('APP_HOST') or '127.0.0.1', APP_PORT=str(web_port),
               PYTHONUNBUFFERED='1')
    # Flask reaches the platform API we start; with --only web an explicit TWINSITE_API_URL is kept.
    if 'api' in only or args.reference or not env.get('TWINSITE_API_URL'):
        env['TWINSITE_API_URL'] = f'http://127.0.0.1:{api_port}'
    env['PYTHONPATH'] = os.pathsep.join([str(ROOT/'backend'), str(ROOT)] + ([env['PYTHONPATH']] if env.get('PYTHONPATH') else []))
    print('AI-Powered Analysis: ' + ('ON (free providers only)' if ai else 'OFF (Simple Analysis only)'), flush=True)

    commands = []
    if args.reference:
        if not (REFERENCE/'ares/server.py').exists():
            raise SystemExit('Run make bootstrap first.')
        db = str(runtime/'reference-synthetic.sqlite')
        commands = [('api', [sys.executable, '-m', 'ares', 'serve', '--db', db, '--port', str(api_port)], REFERENCE),
                    ('worker', [sys.executable, '-m', 'ares', 'worker', '--db', db], REFERENCE)]
        print('REFERENCE ONLY: synthetic scoring and historical ARES UI; no NASA science release.', flush=True)
    else:
        missing = [p for p in ['backend/app.py', 'backend/twinsite/api/__main__.py', 'backend/twinsite/jobs/__main__.py']
                   if not (ROOT/p).exists()]
        if missing:
            raise SystemExit('Entry points missing: ' + ', '.join(missing))
        if 'web' in only:
            commands.append(('web', [sys.executable, 'backend/app.py'], ROOT))
        if 'api' in only:
            commands.append(('api', [sys.executable, '-m', 'twinsite.api'], ROOT))
        if 'worker' in only:
            commands.append(('worker', [sys.executable, '-m', 'twinsite.jobs'], ROOT))
        if args.vite:
            if not (ROOT/'frontend/node_modules').exists():
                raise SystemExit('frontend/node_modules missing: run `make console` (npm ci) first, or drop --vite.')
            commands.append(('vite', ['npm', 'run', 'dev', '--', '--host', '127.0.0.1'], ROOT/'frontend'))
        if 'web' in only and not (ROOT/'frontend/dist/index.html').exists():
            print('Note: frontend/dist missing, /console/ shows build instructions. Run `make console` to build it.', flush=True)
        if 'web' in only and not Path(env.get('DATA_READY_DIR') or ROOT/'data_ready').is_dir():
            print('Note: data_ready/ not found; set DATA_READY_DIR. /api/status will report the missing datasets.', flush=True)

    busy = [f'{name}:{port}' for name, port in (('web', web_port), ('api', api_port))
            if any(c[0] == name for c in commands) and not port_free(port)]
    if busy:
        raise SystemExit(f'Port(s) already in use: {", ".join(busy)}. Stop that process or pick other ports, '
                         'e.g. `make dev WEB_PORT=5051 API_PORT=8091`.')

    children = []

    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    try:
        for _name, command, cwd in commands:
            children.append(subprocess.Popen(command, cwd=cwd, env=env, start_new_session=True))
        names = [c[0] for c in commands]
        if 'web' in names:
            print(f'Web:     http://127.0.0.1:{web_port}  (console: /console/, API proxy: /v1)', flush=True)
        if 'api' in names:
            print(f'API:     http://127.0.0.1:{api_port}/v1/health', flush=True)
        if 'vite' in names:
            print('Console dev server: http://127.0.0.1:5173/console/', flush=True)
        print('Ctrl+C stops all child processes.', flush=True)
        while all(p.poll() is None for p in children):
            time.sleep(.25)
        raise SystemExit('A service exited; shutting down the stack. See preceding service output.')
    except KeyboardInterrupt:
        pass
    finally:
        for process in children:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for process in children:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == '__main__':
    main()
