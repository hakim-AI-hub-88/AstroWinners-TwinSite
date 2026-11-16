#!/usr/bin/env bash
# Free Hugging Face Space (Gradio SDK) boot: the Space's one-line app.py clones this branch into
# $HOME/twinsite and runs this script. It builds the React console when npm is available
# (packages.txt: nodejs npm), points runtime state at a writable directory and hands over to the
# same one-container entrypoint used by Docker/Render (ops/container/start.sh) on port 7860.
set -u
APP="${APP_DIR:-$HOME/twinsite}"
export APP_DIR="$APP"
export PORT="${PORT:-7860}"
export PYTHON="${PYTHON:-python}"
export TWINSITE_DATA_DIR="${TWINSITE_DATA_DIR:-$HOME/twinsite-data}"
mkdir -p "$TWINSITE_DATA_DIR"
echo "[boot] commit $(git -C "$APP" rev-parse --short HEAD 2>/dev/null || echo unknown) · python $($PYTHON -V 2>&1)"

if [ ! -f "$APP/frontend/dist/index.html" ]; then
  if command -v npm >/dev/null 2>&1; then
    echo "[boot] building Mission Console with node $(node -v)"
    ( cd "$APP/frontend" && npm ci --no-audit --no-fund --loglevel=error && { npm run build || npx vite build; } ) \
      || echo "[boot] console build failed; /console/ will show its not-built page"
  else
    echo "[boot] npm not available; /console/ will show its not-built page"
  fi
fi

chmod +x "$APP/ops/container/start.sh"
exec bash "$APP/ops/container/start.sh"
