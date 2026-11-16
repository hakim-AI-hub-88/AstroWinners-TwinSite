# Vercel in front of the TwinSite VM

Vercel is the **edge only**: TLS on your domain, a global CDN for `/static/*`, and a reverse proxy for
everything else. The application itself runs on the Linux VM ([ops/vm/README.md](../../ops/vm/README.md)).

## Why not run TwinSite on Vercel itself

| TwinSite needs | Vercel Functions give |
| --- | --- |
| A **long-running worker** (`python -m twinsite.jobs`) that leases jobs from a queue and runs the 13 agent roles for minutes | Request-scoped functions with execution time limits; no always-on background process |
| **SQLite + artifact blobs** in `TWINSITE_DATA_DIR` (queue, results, reports, Auto Mode state) shared by API, worker and web | Ephemeral, per-instance filesystem; nothing persists between invocations or is shared across instances |
| **~260 MB of bundled datasets** (`data_ready/`) loaded into memory by the Flask app at start | Function bundle size limits well below that, plus a cold start that would reload the data |
| Background threads for Auto Mode missions | Threads are frozen or killed when the response is sent |

So the VM keeps all state and processes; Vercel adds a domain, HTTPS and caching without changing the app.

## How the config works

- [`vercel.json`](../../vercel.json): one rewrite `/(.*)` → `https://TWINSITE_VM_HOST/$1`. Vercel checks
  its own files first, so `/static/*` is served from the deployment (edge-cached, `s-maxage` one year,
  browsers one day; each new Vercel deployment invalidates the edge cache). Every other path (pages,
  `/api/*`, `/console/*`, `/v1/*`) is proxied to the VM. Baseline security headers (HSTS, nosniff,
  referrer and permissions policy) are added at the edge; the path-specific CSP and framing headers come
  from nginx on the VM.
- [`.vercelignore`](../../.vercelignore) is an allowlist: only `static/` and `vercel.json` are uploaded.
  Backend code, `.env*`, `data_ready/`, `.runtime/`, `.venv/` and `node_modules/` never leave the repo, and
  cannot be served by Vercel by mistake.

## Steps

1. Deploy the VM first and make it reachable over HTTPS on its own hostname (e.g. `origin.example.org`):
   [ops/vm/README.md](../../ops/vm/README.md) sections 2–5. Check it with
   `python ops/vm/smoke.py --base-url https://origin.example.org --skip-mission`.
2. In `vercel.json`, replace the placeholder **`TWINSITE_VM_HOST`** with that hostname (no scheme, no path):
   `"destination": "https://origin.example.org/$1"`.
3. Link the project and deploy from the repo root (Vercel CLI, logged in to your own account):
   ```sh
   vercel link            # once; framework preset "Other", no build command
   vercel --prod
   ```
4. In the Vercel dashboard, add your public domain (e.g. `twinsite.example.org`) to the project and set
   the DNS records it shows. The VM keeps its own origin hostname.
5. Verify through the edge:
   `python ops/vm/smoke.py --base-url https://twinsite.example.org --skip-mission`.
6. Whenever `static/` changes, redeploy Vercel (`vercel --prod`) together with the VM so both serve the same files.

## Limits to know

- **Proxy timeout.** Vercel applies a timeout to proxied (external rewrite) requests; check the current
  limit for your plan. Long synchronous calls such as `POST /api/report` with an AI narrative can exceed it.
  Auto Mode (`POST /api/auto/missions` → 202, then polling) and platform missions (`/v1/missions` → 202) are
  asynchronous and unaffected.
- **Client IP.** The VM sees Vercel edge IPs; the nginx `/v1/` rate limit therefore applies per edge node.
- **Host header.** The VM receives its own hostname as `Host`. Absolute URLs that Flask builds from the
  request (for example in `/sitemap.xml` and `/robots.txt`) show the origin host unless the app is told the
  public URL.
- **Uploads** are disabled in the platform (`TWINSITE_UPLOADS_ENABLED=false`); request bodies are small.
