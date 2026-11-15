#!/usr/bin/env bash
# TwinSite VM install / upgrade (Debian/Ubuntu with systemd + nginx). Idempotent: safe to re-run.
#
#   sudo REF=master bash ops/vm/install.sh            # from a checkout, or
#   curl -fsSL <raw url>/ops/vm/install.sh | sudo bash
#
# What it does (each step skips work that is already done):
#   1. system user `twinsite`, dirs /srv/twinsite, /var/lib/twinsite (0700), /etc/twinsite
#   2. clone or update the checkout at $APP_DIR (root-owned, read-only to the service)
#   3. Python venv at $VENV + pip install -r requirements.txt (Flask, gunicorn, jsonschema ...)
#   4. npm ci && npm run build for the React console (frontend/dist, served at /console/)
#   5. /etc/twinsite/env from ops/vm/env.example (only if missing; never overwritten)
#   6. systemd units twinsite-web / twinsite-api / twinsite-worker: install, enable, (re)start
#   7. nginx site (loopback :8081) + `nginx -t` + reload
# It never writes secrets, never creates accounts and never opens firewall ports.
set -euo pipefail

APP_DIR=${APP_DIR:-/srv/twinsite/app}
VENV=${VENV:-/srv/twinsite/venv}
DATA_DIR=${DATA_DIR:-/var/lib/twinsite}
ETC_DIR=${ETC_DIR:-/etc/twinsite}
REPO_URL=${REPO_URL:-https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite.git}
REF=${REF:-master}
PYTHON=${PYTHON:-python3}
SKIP_GIT=${SKIP_GIT:-0}       # 1 = use $APP_DIR as-is (e.g. rsynced tree)
SKIP_NGINX=${SKIP_NGINX:-0}
SERVICE_USER=twinsite

log() { printf '\n== %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "run as root (sudo)"
command -v "$PYTHON" >/dev/null || die "$PYTHON not found (need Python >= 3.11; apt install python3 python3-venv)"
"$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' || die "Python >= 3.11 required"
command -v npm >/dev/null || die "npm not found (Node.js >= 20 needed to build the console)"
command -v git >/dev/null || [ "$SKIP_GIT" = 1 ] || die "git not found"

log "1/7 user and directories"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
install -d -o root -g root -m 0755 /srv/twinsite
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0700 "$DATA_DIR" "$DATA_DIR/source-cache"
install -d -o root -g "$SERVICE_USER" -m 0750 "$ETC_DIR"

log "2/7 checkout ($REF)"
if [ "$SKIP_GIT" = 1 ]; then
  [ -f "$APP_DIR/backend/app.py" ] || die "SKIP_GIT=1 but $APP_DIR has no backend/app.py"
elif [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch --tags origin
  git -C "$APP_DIR" checkout --force "$REF"
  git -C "$APP_DIR" pull --ff-only origin "$REF" 2>/dev/null || true   # no-op for tags / detached refs
else
  git clone --branch "$REF" "$REPO_URL" "$APP_DIR"
fi
[ -d "$APP_DIR/data_ready" ] || echo "WARNING: $APP_DIR/data_ready missing; the Flask analysis pages will report unavailable datasets."

log "3/7 Python venv + requirements"
[ -x "$VENV/bin/python" ] || "$PYTHON" -m venv "$VENV"
"$VENV/bin/python" -m pip install --upgrade pip >/dev/null
"$VENV/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

log "4/7 React console build (frontend/dist)"
(cd "$APP_DIR/frontend" && npm ci --no-audit --no-fund && npm run build)

log "5/7 environment file"
if [ ! -f "$ETC_DIR/env" ]; then
  install -m 0600 -o root -g root "$APP_DIR/ops/vm/env.example" "$ETC_DIR/env"
  echo "Created $ETC_DIR/env from env.example (all lines commented = defaults)."
else
  echo "Keeping existing $ETC_DIR/env"
fi
[ -f "$ETC_DIR/ai-providers.env" ] || echo "Note: no $ETC_DIR/ai-providers.env -> AI features report 'not configured' (see ops/vm/README.md)."

log "6/7 systemd units"
for unit in twinsite-api twinsite-worker twinsite-web; do
  install -m 0644 "$APP_DIR/ops/vm/$unit.service" "/etc/systemd/system/$unit.service"
done
systemctl daemon-reload
systemctl enable twinsite-api twinsite-worker twinsite-web >/dev/null
systemctl restart twinsite-api twinsite-worker twinsite-web

log "7/7 nginx"
if [ "$SKIP_NGINX" = 1 ]; then
  echo "SKIP_NGINX=1: not touching nginx"
elif command -v nginx >/dev/null; then
  install -m 0644 "$APP_DIR/ops/vm/nginx.conf" /etc/nginx/conf.d/twinsite.conf
  nginx -t
  systemctl reload nginx
else
  echo "nginx not installed (apt install nginx), then re-run this script."
fi

log "status"
sleep 3
systemctl --no-pager --lines=0 status twinsite-api twinsite-worker twinsite-web || true
echo
echo "Next: $VENV/bin/python $APP_DIR/ops/seed_sites.py   (as $SERVICE_USER, see README)"
echo "      $VENV/bin/python $APP_DIR/ops/vm/smoke.py --base-url http://127.0.0.1:8081 --expect-security-headers"
