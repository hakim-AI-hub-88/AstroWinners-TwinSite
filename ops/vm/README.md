# Linux VM deployment runbook

TwinSite runs as three processes behind nginx on one persistent Linux VM. Vercel can sit in front as an
edge proxy ([docs/deployment/VERCEL.md](../../docs/deployment/VERCEL.md)); the VM stays the origin.

Status, 2026-11-15: **prepared, not yet deployed.** The units, nginx files and `install.sh` were reviewed
and syntax-checked on macOS (`bash -n`). The stack itself was exercised locally with `make dev` and
`ops/vm/smoke.py`. `nginx -t`, systemd sandboxing and SELinux/AppArmor were **not** run on Linux yet:
validate all three on the target VM before exposing it. Deploy only to an approved host.

## 0. Architecture

```
browser ─▶ (Vercel edge, optional) ─▶ nginx :443 / :8081 (loopback)
                                        ├─ /v1/*              ─▶ twinsite-api    127.0.0.1:8080  python -m twinsite.api
                                        ├─ /static/*          ─▶ /srv/twinsite/app/static/            (files)
                                        ├─ /console/assets/*  ─▶ /srv/twinsite/app/frontend/dist/assets/ (files, immutable)
                                        └─ everything else    ─▶ twinsite-web    127.0.0.1:5050  gunicorn "app:create_app()"
                                                                   (pages, /api/*, /console/ SPA fallback)
                         twinsite-worker  python -m twinsite.jobs   (mission queue, 13 agents)  ── SQLite + blobs in /var/lib/twinsite
```

| Path | Owner / mode | Contents |
| --- | --- | --- |
| `/srv/twinsite/app` | root, read-only to `twinsite` | Checkout at a reviewed tag/branch, incl. `data_ready/` (~260 MB) and `frontend/dist` |
| `/srv/twinsite/venv` | root | Python venv (`requirements.txt`: Flask, gunicorn, jsonschema, pandas, scikit-learn …) |
| `/var/lib/twinsite` | `twinsite`, 0700 | SQLite queue/results (WAL), artifact blobs, reports, Auto Mode state (`auto/`), seeded sites |
| `/var/lib/twinsite/source-cache` | `twinsite`, 0700 | Pinned raw NASA assets and cleaned grids, addressed by `object_key` |
| `/etc/twinsite/env` | root, 0600 | Site settings for all three units ([`env.example`](env.example), names only in git) |
| `/etc/twinsite/ai-providers.env` | `twinsite`, 0600 | Optional free-tier AI provider keys (`GROQ_API_KEY=…`) |

Ports 5050 and 8080 bind to `127.0.0.1` only. Open only 80/443 in the firewall.

## 1. Provision the VM

- Debian 12 / Ubuntu 22.04+ (systemd), 2 vCPU, **4 GB RAM** (two gunicorn workers each load the
  harmonized datasets), 20 GB disk.
- Packages: `apt install git nginx python3 python3-venv nodejs npm` (Node.js ≥ 20; use NodeSource if the
  distro's is older). Python ≥ 3.11.
- A DNS name pointing at the VM (used below as `twinsite.example.org`).

## 2. Install (idempotent)

```sh
git clone https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite.git /srv/twinsite/app   # or let install.sh clone
sudo REF=master bash /srv/twinsite/app/ops/vm/install.sh
```

[`install.sh`](install.sh) creates the `twinsite` user and directories, updates the checkout to `$REF`,
builds the venv and installs `requirements.txt`, runs `npm ci && npm run build` for the console, installs
`/etc/twinsite/env` from `env.example` (only if missing), installs and (re)starts `twinsite-web`,
`twinsite-api` and `twinsite-worker`, then installs the loopback nginx site and runs `nginx -t`.
Re-run it for upgrades. Variables: `APP_DIR`, `VENV`, `REF`, `REPO_URL`, `PYTHON`, `SKIP_GIT=1`, `SKIP_NGINX=1`.

Optional AI (free tiers only; nothing paid is ever called):

```sh
sudo install -m 0600 -o twinsite -g twinsite /dev/null /etc/twinsite/ai-providers.env
sudoedit /etc/twinsite/ai-providers.env        # GROQ_API_KEY=..., MISTRAL_API_KEY=..., names in env.example
sudo systemctl restart twinsite-web twinsite-api twinsite-worker
```

Without the file every deterministic feature works and AI features answer "not configured".

## 3. Seed analog sites and the source cache

Sites for the console's Explorer and matching come from real public data (AWS Terrain Tiles, NASA POWER,
LRO LOLA/Diviner, MGS MOLA). Run once as the service user; failures are reported per site, never guessed:

```sh
cd /srv/twinsite/app
sudo -u twinsite env PYTHONPATH=backend:. TWINSITE_DATA_DIR=/var/lib/twinsite \
  /srv/twinsite/venv/bin/python ops/seed_sites.py --workers 4
```

Measured runs and the console grid view also need the verified source cache. Copy the build machine's
caches (`.runtime/data`, `.runtime/official-data`) to the VM, then install exactly the pinned objects:

```sh
sudo -u twinsite env PYTHONPATH=backend:. /srv/twinsite/venv/bin/python ops/provision_source_cache.py \
  --to /var/lib/twinsite/source-cache --from /tmp/twinsite-cache/data --from /tmp/twinsite-cache/official-data
sudo -u twinsite env PYTHONPATH=backend:. /srv/twinsite/venv/bin/python ops/provision_source_cache.py \
  --to /var/lib/twinsite/source-cache --check      # must print "Source cache ready"
```

It verifies every SHA-256, never overwrites and never downloads. Without it, measured runs fail with
"Source bytes missing" and the grid view returns an error (the smoke test reports both).

## 4. Smoke test

```sh
systemctl is-active twinsite-web twinsite-api twinsite-worker
/srv/twinsite/venv/bin/python /srv/twinsite/app/ops/vm/smoke.py --base-url http://127.0.0.1:8081 --expect-security-headers
```

[`smoke.py`](smoke.py) checks every Flask page (`/ /app /auto /data /resources /sitemap /policy /sitemap.xml`),
a `/static/` file, the Flask APIs (`/api/status`, `/api/data/datasets`, `/api/ai/status`, `/api/auto/missions`),
the console (`/console/`, a hashed asset, three deep links), `/v1/health`, the live catalog and grid, and
submits one measured run that must finish with C2, P00–P90, BLOCK and a report (API health alone does
not prove the worker runs). `--skip-mission` skips the run. Exit code 0 only when everything passes.

## 5. TLS (public exposure)

```sh
sudo install -d /var/www/letsencrypt
sudo cp /srv/twinsite/app/ops/vm/nginx-https.conf.example /etc/nginx/conf.d/twinsite-https.conf
sudo sed -i 's/twinsite.example.org/YOUR.HOST.NAME/g' /etc/nginx/conf.d/twinsite-https.conf
# first issue the certificate with only the :80 block active (comment the :443 block), then:
sudo certbot certonly --webroot -w /var/www/letsencrypt -d YOUR.HOST.NAME
sudo nginx -t && sudo systemctl reload nginx
/srv/twinsite/venv/bin/python /srv/twinsite/app/ops/vm/smoke.py --base-url https://YOUR.HOST.NAME --expect-security-headers --skip-mission
```

Keep the loopback block (`nginx.conf`, :8081) for health checks. If Vercel fronts the site, this hostname
is the `TWINSITE_VM_HOST` in `vercel.json`.

## 6. Security notes

- `nginx-headers.conf` (Flask pages): nosniff, HSTS, `frame-ancestors 'self'`, referrer policy. It sets no
  script CSP because `/app` loads CesiumJS/Leaflet from public CDNs and uses inline scripts.
- `nginx-console-headers.conf` (`/console/`, `/v1/`): strict CSP (self, Google Fonts, NASA GIBS/Trek tiles), DENY framing.
- `/v1/` is rate limited (10 r/s per client IP, burst 80). Behind Vercel the client IP is an edge IP, so the
  limit applies per edge node.
- Units: `ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges`, `PrivateTmp`; the only writable path is
  `/var/lib/twinsite`. Services never hold Earthdata credentials (`TWINSITE_SECRET_ENV_FILE` points at a
  path that does not exist). The Earthdata token used earlier was exposed: it must be revoked and never deployed.

## 7. Operations

- **Logs:** `journalctl -u twinsite-web -u twinsite-api -u twinsite-worker`. Secrets and payloads are never logged.
- **Backups:** `sqlite3 /var/lib/twinsite/twinsite.sqlite ".backup /backup/twinsite-$(date +%F).sqlite"` (online,
  WAL-safe), plus `source-cache` and `auto/`. Never alter cache files in place.
- **Upgrades:** `sudo REF=<tag> bash /srv/twinsite/app/ops/vm/install.sh`, then rerun the smoke test.
- **Restart behaviour:** units use `Restart=always` (10 restarts / 60 s). Persisted job leases recover
  interrupted runs after a crash or reboot; `tests/e2e/measured_live.py` exercises this on any host.
- **Scientific release** remains **BLOCK** (see `docs/release/SCIENTIFIC_REVIEW.md`).
