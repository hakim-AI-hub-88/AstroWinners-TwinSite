# Linux VM deployment runbook — prepared, NOT deployed

Status, 2026-11-15:

- **Not yet tested on Linux, and not deployed.** Docker and nginx were not available on the build machine.
- **Tested locally on macOS:**
  - The production build was served through `vite preview`, with the same SPA fallback and `/v1` proxy as nginx.
  - `ops/vm/smoke.py`: 14/14 PASS.
  - Restart and crash recovery: `make verify`, which includes the `c5_http_restart_e2e` and `measured_http_restart_e2e` suites.
- **Not yet validated:** `nginx -t`, systemd sandboxing, and SELinux/AppArmor. Validate all three on the target VM before exposing it.

Deploy only to an approved host. Nothing here needs a paid API, an AI key, or an Earthdata token.

## 1. Host layout

| Path | Owner / mode | Contents |
| --- | --- | --- |
| `/opt/twinsite` | root, read-only to `twinsite` | Reviewed checkout at a tagged commit, `.venv`, `frontend/dist` |
| `/var/lib/twinsite` | `twinsite`, 0700 | SQLite queue/results (WAL), artifact blobs, reports |
| `/var/lib/twinsite/source-cache` | `twinsite`, 0700 | Pinned raw NASA assets and cleaned grids, addressed by `object_key` |
| `/etc/twinsite/twinsite.env` | root, 0644, optional | **Non-secret** overrides only, such as `TWINSITE_CORS_ORIGINS` |

The services receive **no credentials**. Both units point `TWINSITE_SECRET_ENV_FILE` at a path that does not exist, so a stray `.env` file is never read. Measured runs and the grid view read only the verified cache.

## 2. Install (as root, on the approved VM)

```sh
useradd --system --home /var/lib/twinsite --shell /usr/sbin/nologin twinsite
install -d -o twinsite -g twinsite -m 0700 /var/lib/twinsite /var/lib/twinsite/source-cache
git clone <reviewed remote> /opt/twinsite && git -C /opt/twinsite checkout <release tag>
python3.13 -m venv /opt/twinsite/.venv
/opt/twinsite/.venv/bin/pip install -r /opt/twinsite/requirements-integration.txt
(cd /opt/twinsite/frontend && npm ci && npm run build)
```

## 3. Provision the source cache (offline, hash-verified)

Copy the build machine's verified caches to the VM. Use `rsync`, or a tarball of
`.runtime/data` and `.runtime/official-data`. Then install exactly the objects named by the published pair:

```sh
sudo -u twinsite /opt/twinsite/.venv/bin/python /opt/twinsite/ops/provision_source_cache.py \
  --to /var/lib/twinsite/source-cache --from /tmp/twinsite-cache/data --from /tmp/twinsite-cache/official-data
sudo -u twinsite /opt/twinsite/.venv/bin/python /opt/twinsite/ops/provision_source_cache.py \
  --to /var/lib/twinsite/source-cache --check      # must print "Source cache ready"
```

The script verifies every SHA-256, never overwrites, and never downloads anything. Without this
step, measured runs fail with "Source bytes missing" and the grid view returns 404.

## 4. Services

```sh
install -m 0644 /opt/twinsite/ops/vm/twinsite-api.service /opt/twinsite/ops/vm/twinsite-worker.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now twinsite-api twinsite-worker
```

- **Restarts:** both units use `Restart=always`, which allows 10 restarts per 60 s.
- **Sandboxing:** `ProtectSystem=strict` and `ProtectHome` are set, and the only writable path is `/var/lib/twinsite`.
- **Recovery:** the persisted job leases recover interrupted runs after a crash or reboot, and result commits are fenced.
- **Network:** the API binds to `127.0.0.1:8080` only.

## 5. nginx

```sh
cp /opt/twinsite/ops/vm/nginx.conf /etc/nginx/conf.d/twinsite.conf   # loopback :8081 only
nginx -t && systemctl reload nginx
```

`nginx-common.conf` covers:

- Static files from `frontend/dist`.
- An SPA fallback, so deep links such as `/analysis/run-…` work.
- The `/v1/` reverse proxy, with the prefix kept.
- Immutable caching for `/assets/`.
- A rate limit.
- Security headers (`nginx-headers.conf`): CSP allowing only self, Google Fonts and NASA GIBS tiles; nosniff; DENY framing.

**HTTPS (public exposure):** copy `nginx-https.conf.example`, replace the hostname, then obtain certificates with
certbot (webroot) or the host's managed TLS. Keep the loopback block for health checks, and open only ports 80/443
in the firewall.

## 6. Health and acceptance

```sh
systemctl is-active twinsite-api twinsite-worker
/opt/twinsite/.venv/bin/python /opt/twinsite/ops/vm/smoke.py --base-url http://127.0.0.1:8081 --expect-security-headers
```

The smoke test checks the following:

- The index page and a hashed asset are served.
- Three deep links resolve.
- Health is ready, with AI off.
- The live catalog and the verified grid are served.
- One measured run completes with C2, P00–P90, BLOCK and a report.

API health alone does not prove the worker is running, which is why the smoke test submits a real run.

For restart behaviour, run `systemctl restart twinsite-worker` while a run is queued, and `kill -9` the worker
in the middle of a run. Both runs must still complete. `tests/e2e/measured_live.py` automates these checks on any host.

## 7. Operations

- **Backups:** use `sqlite3 /var/lib/twinsite/twinsite.sqlite ".backup /backup/twinsite-$(date +%F).sqlite"`, which is an online, WAL-safe backup. Also back up `source-cache`, and never alter its files in place.
- **Logs:** use `journalctl -u twinsite-api -u twinsite-worker`. Request headers, query strings, payloads and secrets are never logged. Full exception tracebacks appear only in the protected journal; public run errors stay redacted.
- **Upgrades:** check out the new tag, `pip install`, `npm ci && npm run build`, then `systemctl restart twinsite-api twinsite-worker`. Rerun the smoke test.

## 8. Credentials

The Earthdata token used earlier was exposed. It must be revoked and must never be deployed.
Acquiring new NASA data needs a replacement token. Run that acquisition from an operator account, not
from these services: use `scripts/integration/provision_earthdata.py` (mode 0600 file, value never echoed),
then publish the new pair through review and redeploy the cache. Scientific release remains **BLOCK**
(see `docs/release/SCIENTIFIC_REVIEW.md`).
