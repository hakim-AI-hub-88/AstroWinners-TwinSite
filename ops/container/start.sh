#!/usr/bin/env bash
# One-container entrypoint: platform API + worker in the background, gunicorn (Flask site) in the foreground.
# If any child exits, everything is stopped and the container exits non-zero (the host restarts it).
# Every variable below can be overridden from the environment (Space secrets / Render envVars).
set -u

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
PYTHON="${PYTHON:-python}"
export PORT="${PORT:-7860}"

# --- Paths -------------------------------------------------------------------------------------
export PYTHONPATH="${APP_DIR}/backend:${APP_DIR}${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1
export DATA_READY_DIR="${DATA_READY_DIR:-$APP_DIR/data_ready}"
export TWINSITE_DATA_DIR="${TWINSITE_DATA_DIR:-/data/twinsite}"
export TWINSITE_SOURCE_DATA_DIR="${TWINSITE_SOURCE_DATA_DIR:-$TWINSITE_DATA_DIR/source-cache}"
export TWINSITE_CONSOLE_DIST="${TWINSITE_CONSOLE_DIST:-$APP_DIR/frontend/dist}"

# --- Platform API (loopback only; Flask proxies public /v1 to it) ------------------------------
export TWINSITE_API_HOST="${TWINSITE_API_HOST:-127.0.0.1}"
export TWINSITE_API_PORT="${TWINSITE_API_PORT:-8080}"
export TWINSITE_API_URL="${TWINSITE_API_URL:-http://127.0.0.1:${TWINSITE_API_PORT}}"

# --- Features ----------------------------------------------------------------------------------
export TWINSITE_AI_ENABLED="${TWINSITE_AI_ENABLED:-true}"
export TWINSITE_UPLOADS_ENABLED="${TWINSITE_UPLOADS_ENABLED:-false}"
# AI keys come from the environment (host secrets); no secret files inside the container.
export TWINSITE_AI_SECRET_ENV_FILE="${TWINSITE_AI_SECRET_ENV_FILE:-/nonexistent/ai-providers.env}"
# Services never hold Earthdata credentials; never read a stray repo .env.
export TWINSITE_SECRET_ENV_FILE="${TWINSITE_SECRET_ENV_FILE:-/nonexistent/services-have-no-secrets}"
export TWINSITE_BEHIND_PROXY="${TWINSITE_BEHIND_PROXY:-1}"
export PUBLIC_BASE_URL="${PUBLIC_BASE_URL:-}"
# Seed the real analog sites/targets at boot (network: AWS terrain tiles, NASA POWER, LOLA, MOLA).
# Idempotent and cached under TWINSITE_DATA_DIR; runs in the background and never blocks serving.
SEED_ON_START="${TWINSITE_SEED_ON_START:-1}"
SEED_WORKERS="${TWINSITE_SEED_WORKERS:-2}"
WEB_THREADS="${WEB_THREADS:-8}"
WEB_TIMEOUT="${WEB_TIMEOUT:-180}"

mkdir -p "$TWINSITE_DATA_DIR" "$TWINSITE_SOURCE_DATA_DIR"

# One-secret option: TWINSITE_AI_ENV holds a whole ai-providers.env (KEY=value lines). It is written to an
# owner-only 0600 file read by the AI router, then removed from the environment of every child process.
if [ -n "${TWINSITE_AI_ENV:-}" ]; then
  SECRET_DIR="$TWINSITE_DATA_DIR/secrets"
  ( umask 077; mkdir -p "$SECRET_DIR"; printf '%s\n' "$TWINSITE_AI_ENV" > "$SECRET_DIR/ai-providers.env" )
  chmod 600 "$SECRET_DIR/ai-providers.env"
  export TWINSITE_AI_SECRET_ENV_FILE="$SECRET_DIR/ai-providers.env"
  unset TWINSITE_AI_ENV
  echo "[start] AI keys loaded from the TWINSITE_AI_ENV secret ($(grep -c '=' "$TWINSITE_AI_SECRET_ENV_FILE") lines)"
fi
cd "$APP_DIR" || exit 1

PIDS=()
cleanup() {
  trap - TERM INT EXIT
  for pid in "${PIDS[@]}"; do kill -TERM "$pid" 2>/dev/null; done
  sleep 2
  for pid in "${PIDS[@]}"; do kill -KILL "$pid" 2>/dev/null; done
}
trap 'cleanup; exit 143' TERM INT

echo "[start] data_ready=$DATA_READY_DIR runtime=$TWINSITE_DATA_DIR port=$PORT api=$TWINSITE_API_URL"

"$PYTHON" -m twinsite.api & API_PID=$!; PIDS+=("$API_PID")
"$PYTHON" -m twinsite.jobs & WORKER_PID=$!; PIDS+=("$WORKER_PID")

# Wait (max ~30 s) for the API to accept connections before the web tier starts proxying to it.
for _ in $(seq 1 60); do
  "$PYTHON" - <<PY 2>/dev/null && break
import socket; socket.create_connection(("${TWINSITE_API_HOST}", ${TWINSITE_API_PORT}), 1).close()
PY
  kill -0 "$API_PID" 2>/dev/null || { echo "[start] platform API exited during startup"; cleanup; exit 1; }
  sleep 0.5
done

"$PYTHON" -m gunicorn --chdir "$APP_DIR/backend" "app:create_app()" \
  --bind "0.0.0.0:${PORT}" -w 1 --threads "$WEB_THREADS" --timeout "$WEB_TIMEOUT" --graceful-timeout 30 \
  --forwarded-allow-ips '*' --access-logfile - --error-logfile - &
WEB_PID=$!; PIDS+=("$WEB_PID")

if [ "$SEED_ON_START" = "1" ]; then
  # Seed only after the site answers, so seeding never overlaps the dataset load (memory peak).
  ( for _ in $(seq 1 180); do
      "$PYTHON" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:${PORT}/api/status', timeout=5)" \
        2>/dev/null && break
      sleep 5
    done
    "$PYTHON" ops/seed_sites.py --workers "$SEED_WORKERS" > "$TWINSITE_DATA_DIR/seed.log" 2>&1 \
      && echo "[start] site seeding finished (see $TWINSITE_DATA_DIR/seed.log)" \
      || echo "[start] site seeding reported errors (see $TWINSITE_DATA_DIR/seed.log)" ) &
fi

# Supervise: if any core child dies, stop the rest and exit so the platform restarts the container.
while :; do
  for pid in "$API_PID" "$WORKER_PID" "$WEB_PID"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid"; code=$?
      echo "[start] child $pid exited (code $code); stopping container"
      cleanup
      [ "$code" -eq 0 ] && code=1   # an unexpected exit is always a failure
      exit "$code"
    fi
  done
  sleep 2
done
