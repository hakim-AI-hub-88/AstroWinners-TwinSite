# Free hosting for the platform-integration build

This branch deploys as **one container** (`Dockerfile` + `ops/container/start.sh`): the Flask site
(gunicorn, 1 worker x 8 threads, because Auto Mode uses in-process threads), the platform API
(`python -m twinsite.api`, loopback only) and the job worker (`python -m twinsite.jobs`). Flask serves
every page, `/console` (React build, compiled in the Docker node stage) and proxies `/v1` to the API.
The bundled datasets in `data_ready/` are copied into the image.

It is a **separate deployment**. The `master` service on Render
(https://astrowinners-twinsite-1.onrender.com/) is not affected: different branch, different service.

## Fastest path today

1. **Render Blueprint (no upload from your machine).** Render builds straight from GitHub: New → Blueprint →
   repo `hakim-AI-hub-88/AstroWinners-TwinSite`, branch `platform-integration` → it reads `render.yaml` and
   creates the separate `twinsite-visionary` service. Paste the AI keys in the dashboard. Watch the first build
   log (it is the first build of this image). If the free 512 MB instance restarts with out-of-memory, switch the
   service to a larger instance type or use option 2.
2. **Hugging Face Spaces (16 GB RAM, free) — no data upload.** Create a Docker Space and add only
   `ops/container/hf/Dockerfile` and `ops/container/hf/README.md`. The build clones this branch from GitHub on
   Hugging Face's network, so `data_ready/` is never uploaded and no LFS is needed. Add AI keys as Space secrets.
   New commits: Settings → Factory rebuild. (Pushing the whole repo instead needs LFS, see below.)
3. **Hugging Face Spaces, full-repo push.** Best free fit for the full Mars data, but six files in `data_ready/`
   are 20–48 MB, so they must be pushed with Git LFS/Xet from a **full** clone on a fast connection (see below).
   A blob-less or slow clone would download ~260 MB before it can push.

## Options compared

| Host | Free resources | Fit for TwinSite |
|---|---|---|
| **Hugging Face Spaces (Docker SDK)** - recommended | CPU basic: 2 vCPU, 16 GB RAM; sleeps after ~48 h without traffic; disk is **not persistent** (resets on restart) | Best free fit. The Mars dataset is ~1.84M rows and pandas needs the RAM. Runtime state (jobs, Auto Mode missions, seeded sites) is rebuilt after each restart; sites re-seed in the background at boot. |
| Render free web service | 512 MB RAM, 0.1 CPU, sleeps after 15 min idle (cold start ~1 min), no persistent disk | Works for the pages, but 512 MB **may be too small** for the full Mars data plus API and worker; expect out-of-memory restarts. Blueprint: `render.yaml`. |
| Oracle Cloud Always Free (Ampere ARM VM) | Up to 4 OCPU / 24 GB RAM, persistent block storage | Most capable free option and persistent; needs a VM you administer. Use `ops/vm/` (systemd units, nginx, `install.sh`) rather than this container, or run the container with Docker. Account sign-up needs a card for verification. |
| Google Cloud free tier e2-micro | 2 shared vCPU (burst), 1 GB RAM | Too small for the datasets. |
| Vercel | - | **Not needed.** Flask serves all pages and the console. `vercel.json` is only an optional edge proxy in front of a Python host. |

**NASA:** there is no general free NASA cloud for the public. NASA SMCE and NASA cloud credits are for
NASA-funded researchers/projects. Space Apps partner credits (cloud providers) vary from year to year:
check the current resources page on spaceappschallenge.org.

## Secrets (all optional)

Set as host secrets / env vars, never committed. Missing AI keys => AI features report "not
configured" and every deterministic feature still works (only free-tier providers are used).

| Name | Purpose |
|---|---|
| `GROQ_API_KEY` (and `GROQ_API_KEY_2`, ...) | Groq free tier (AI Mission Assistant, agents) |
| `GROQ_MODEL` | optional model override (default `openai/gpt-oss-120b`) |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | Cloudflare Workers AI |
| `GOOGLE_API_KEY` | Google AI Studio (Gemini) free tier |
| `MISTRAL_API_KEY` | Mistral free tier |
| `OPENROUTER_API_KEY` | OpenRouter free models |
| `NVIDIA_NIM_API_KEY` | NVIDIA NIM |
| `PUBLIC_BASE_URL` | canonical URL for sitemap.xml / robots.txt (not secret) |

Never set Earthdata credentials on the service; measured runs read only the verified source cache.

## Container settings (env, with defaults from `ops/container/start.sh`)

`PORT=7860`, `TWINSITE_DATA_DIR=/data/twinsite`, `DATA_READY_DIR=/app/data_ready`,
`TWINSITE_API_PORT=8080` (loopback), `TWINSITE_API_URL=http://127.0.0.1:8080`,
`TWINSITE_CONSOLE_DIST=/app/frontend/dist`, `TWINSITE_AI_ENABLED=true`, `TWINSITE_UPLOADS_ENABLED=false`,
`TWINSITE_SEED_ON_START=1`, `TWINSITE_SEED_WORKERS=2`, `WEB_THREADS=8`, `WEB_TIMEOUT=180`.

Health check: `GET /v1/health` (through the Flask proxy, so it checks web + API together).

Seeding: `ops/seed_sites.py` characterizes the analog sites and Moon/Mars targets from public data
(AWS Terrain Tiles, NASA POWER, LRO LOLA/Diviner, MGS MOLA). It is idempotent and cached; the container
runs it in the background at boot (log: `$TWINSITE_DATA_DIR/seed.log`). Set `TWINSITE_SEED_ON_START=0`
to skip it. `ops/provision_source_cache.py` is **not** run in the container: it copies verified source
bytes from an existing cache and never downloads, so it only applies on a VM that has such a cache
(see `ops/vm/README.md`). Without it, measured runs that need the pinned source cache report the
source as unavailable instead of guessing.

## Step by step: Hugging Face Spaces (recommended)

1. Sign in at huggingface.co, then **New Space**: choose a name, **SDK: Docker** (Blank template),
   hardware **CPU basic (free)**, visibility Public.
2. Add the Space as a git remote (use a write access token from Settings > Access Tokens as the password):
   ```bash
   git remote add hf https://huggingface.co/spaces/<user>/<space>
   ```
3. A Space reads its config from the YAML front-matter at the top of its `README.md`. Keep the GitHub
   README unchanged and add the header on a deploy-only branch:
   ```bash
   git checkout -b hf-deploy platform-integration
   cat ops/container/hf_space_header.md README.md > /tmp/README.hf && mv /tmp/README.hf README.md
   git commit -am "Space header"
   git push hf hf-deploy:main
   ```
   Header (`ops/container/hf_space_header.md`):
   ```yaml
   ---
   title: TwinSite
   colorFrom: indigo
   colorTo: gray
   sdk: docker
   app_port: 7860
   pinned: false
   license: mit
   ---
   ```
   If the Space README already carries this header (for example you created it once in the web UI and
   merged), later updates are just `git push hf platform-integration:main` after merging the header in.
   Hugging Face rejects files over 10 MB unless they are tracked with Git LFS/Xet; if the push is refused
   for a large `data_ready/` file, run `git lfs track "data_ready/**/*.csv"` (or the extension it names)
   on the deploy branch, commit, and push again.
4. In the Space: **Settings > Variables and secrets > New secret** for each key in the secrets table.
   Secrets are passed to the container as environment variables. Optionally add the variable
   `PUBLIC_BASE_URL=https://<user>-<space>.hf.space`.
5. The Space builds the Dockerfile (node stage for the console, then Python). Open
   `https://<user>-<space>.hf.space/` and check `/v1/health` and `/console`.

## Step by step: Render (separate service from master)

1. Render dashboard > **New > Blueprint**, pick the GitHub repo, and point it at `render.yaml` on branch
   `platform-integration` (the blueprint creates `twinsite-visionary`, runtime Docker, plan free,
   health check `/v1/health`). This does not modify the existing master service.
2. When prompted, fill the `sync: false` variables (AI keys, `PUBLIC_BASE_URL`) or leave them empty.
3. Deploy. If the service restarts with out-of-memory errors, the free 512 MB is too small for the full
   datasets: use Hugging Face Spaces or a paid Render instance.

## Local check

```bash
docker build -t twinsite .
docker run --rm -p 7860:7860 -e GROQ_API_KEY=... twinsite
curl -s localhost:7860/v1/health
```
Without Docker: `PORT=5077 TWINSITE_DATA_DIR=$PWD/.runtime/container bash ops/container/start.sh`
(needs `pip install -r requirements.txt`).
