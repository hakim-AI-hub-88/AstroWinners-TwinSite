# TwinSite deployment runbook (C5) — PREPARED, NOT EXECUTED

**Nothing is deployed.** No host, VM or account was named to C5 and none was created. Deploying needs the user's explicit OK plus a host and access (see Blockers).

## Why not free serverless hosting

The C3 backend is two long-lived processes: `python -m twinsite.api` (stdlib HTTP) and `python -m twinsite.jobs` (worker with lease/heartbeat). They share SQLite plus a blob directory under `TWINSITE_DATA_DIR`. Free PaaS tiers (Vercel/Netlify functions, sleeping Render/Fly free machines) have three problems:
- ephemeral disks
- no durable background worker
- sleep or kill on idle

Any of these loses queued jobs and committed results. C5 tested restart persistence only on a durable local disk. **Use one VM with a persistent disk.**

## Target shape (single VM)

| Item | Requirement |
| --- | --- |
| OS | Linux x86_64/arm64, systemd |
| Runtime | Python ≥ 3.13 (backend is stdlib; `jsonschema` only for verification); Node 22 only to *build* the frontend |
| Disk | Persistent volume mounted at `/srv/twinsite/data` (SQLite + raw NASA bytes + blobs). Not tmpfs, not container layer |
| Processes | exactly **one** API + **one** worker (contract: one active mission, queue 20, max 3 attempts) |
| Network | API bound to 127.0.0.1; reverse proxy (Caddy/nginx) terminates TLS and serves `frontend/dist` |
| Secrets | none required. Earthdata creds only for C1 acquisition, in `/etc/twinsite/env` (0600), never in repo or chat. `TWINSITE_AI_ENABLED=false`, `TWINSITE_UPLOADS_ENABLED=false` |

## Steps

```sh
# 1. code: the C0-merged main, a tagged release commit
git clone <public repo> /srv/twinsite/app && cd /srv/twinsite/app && git checkout <release-tag>
python3.13 -m venv .venv && .venv/bin/pip install -r requirements-integration.txt
make bootstrap            # extracts pinned reference archives (the synthetic engine is loaded from references/extracted)
# 2. frontend
cd frontend && npm ci && npm run build && cd ..
# 3. verify on the box BEFORE exposing it
ops/verify.sh --out /srv/twinsite/verify
```

`/etc/systemd/system/twinsite-api.service`. The worker unit is identical except `-m twinsite.jobs` and `Description`:

```ini
[Unit]
Description=TwinSite API
After=network-online.target
[Service]
User=twinsite
WorkingDirectory=/srv/twinsite/app
Environment=PYTHONPATH=/srv/twinsite/app/backend:/srv/twinsite/app
Environment=TWINSITE_DATA_DIR=/srv/twinsite/data
Environment=TWINSITE_API_HOST=127.0.0.1
Environment=TWINSITE_API_PORT=8080
Environment=TWINSITE_AI_ENABLED=false
Environment=TWINSITE_UPLOADS_ENABLED=false
EnvironmentFile=-/etc/twinsite/env
ExecStart=/srv/twinsite/app/.venv/bin/python -m twinsite.api
Restart=on-failure
RestartSec=2
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/srv/twinsite/data
[Install]
WantedBy=multi-user.target
```

Reverse proxy (Caddy):

```
twinsite.example.org {
  handle /v1/* { reverse_proxy 127.0.0.1:8080 }
  handle { root * /srv/twinsite/app/frontend/dist; try_files {path} /index.html; file_server }
}
```

Note `try_files … /index.html`: SPA routes such as `/analysis/:runId` must return the app, and unknown `/v1/*` must stay a JSON 404. `tests/acceptance/http_contract.py` checks the latter.

## Post-deploy acceptance (run against the public URL)

```sh
python tests/acceptance/http_contract.py --base-url https://<host> --repo .
sudo systemctl restart twinsite-api twinsite-worker   # then re-GET a committed run: bytes must be identical
sudo systemctl kill -s KILL twinsite-worker           # mid-run: systemd restarts it; run completes with attempt <= 3
```

The C5 e2e harness `tests/e2e/run_stack.py` automates exactly these restart and kill checks locally. All of them PASSED on the composite tree of 2026-11-15 (see QA_STATUS.md).

## Backups and lifecycle

- Snapshot `/srv/twinsite/data` (SQLite file + blobs) before every redeploy. Raw NASA source bytes are immutable inputs: alternative portfolios must reuse them, never re-download.
- Redeploy = stop worker → stop API → swap code → `ops/verify.sh` → start API → start worker. Committed results must survive; the restart test proves the local equivalent.

## Blockers (user-owned)

1. **Host + access**: which VM/provider, SSH access and a DNS name. Nothing is named in the kit.
2. **Explicit OK to deploy publicly** and to create any hosting account.
3. Earthdata login, only if C1 acquisition runs on the server (cached raw bytes can be shipped instead).
