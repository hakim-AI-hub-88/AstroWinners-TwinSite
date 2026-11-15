# Linux VM configuration — prepared, not deployed

Use a dedicated unprivileged `twinsite` account. Install reviewed source under
`/opt/twinsite`, Python 3.13 with `.venv`, `requirements-integration.txt`, and
build the frontend using its committed lockfile (`npm ci && npm run build`).
The backend has no paid inference dependency. No reference ARES package is needed.

Provision `/var/lib/twinsite` owned by twinsite, mode 0700. Copy the reviewed raw
source tree to `/var/lib/twinsite/source-cache` with its relative object keys
intact. SQLite, durable queue, reports and artifact blobs live in the persistent
state directory. Back up SQLite using its online backup API or stop services;
do not copy a live SQLite main file without its WAL. Preserve source-cache hashes.

Provision `/etc/twinsite/worker.env` separately, root-owned mode 0600. Set
EARTHDATA_TOKEN through the host's secret manager or a protected editor. Systemd
injects this into the worker process. The API and frontend do not receive it.
Rotate the protected value and restart the worker; no code/image change is needed.
The acquisition CLI supports EARTHDATA_TOKEN or TWINSITE_SECRET_ENV_FILE (0600,
owned by the acquisition user). macOS Keychain is never needed for credentials.

Install the two service units and nginx configuration only on an approved host.
The nginx listener is deliberately loopback-only until host/TLS configuration is
reviewed. Put it behind the host's TLS proxy or configure the approved hostname and
certificates. Do not expose Python's development HTTP server directly to the internet.

Systemd restarts failed processes. C3's persisted leases recover interrupted jobs;
result commits are fenced. Check `/v1/health` through nginx and confirm the worker
with `systemctl is-active twinsite-worker`; API health alone does not prove worker
liveness. Observe actual P00–P90 events during a smoke mission. Logs omit headers,
query strings, payloads, secret values and exception text.

Run `make verify` after installation; perform HTTP/browser smoke checks, restart and
SIGKILL recovery tests, then independent C5 scientific review. Scientific releases
remain blocked. This configuration has not been exercised on a Linux VM.

## Post-merge recovery cache requirements

The published pair now references the official LP DAAC SRTM ZIP
(`2493d4ce40b0…`), not the ESA mirror ZIP (`a9c6dd5d6e41…`). The decoded
rasters are byte-identical, but the ZIP object keys and evidence IDs differ.
Deploy all five assets referenced by the published pair and their `asset.json`
metadata (including MOLA subset byte ranges) into the configured source cache.
Both the worker and `make verify` honor `TWINSITE_SOURCE_DATA_DIR`. Do not copy
only the old mirror cache. Preserve cached raw bytes and their metadata.

The previously exposed Earthdata token is compromised: do not deploy or reuse
it. Cached measured analysis requires no token. Future authenticated acquisition
requires a replacement credential provisioned server-side. Offline C5 arithmetic
and checksums pass; fresh independent origin checks and live VM/browser acceptance
are still pending. Scientific release remains BLOCK.
