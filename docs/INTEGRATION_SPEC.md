# TwinSite platform integration — shared spec (all agents read this first)

Repo: /Users/macbook/Projects/AstroWinners-TwinSite (public GitHub hakim-AI-hub-88/AstroWinners-TwinSite, default branch `master`).
Integration branch: `platform-integration`. It already contains BOTH histories:
- the repo's Flask app (backend/app.py, backend/{routes,services,utils}, templates/, static/, data_ready/) = THE PRODUCT BASE
- the local TwinSite platform (backend/twinsite/ stdlib API + worker, contracts/, frontend/ React console, ops/, scripts/, tests/, references/)

Do NOT rewrite or delete existing repo features or data_ready/. Add on top. Never commit secrets, .env, .runtime/.
Never fabricate data: if a live source fails, say so in the UI/API (explicit `status: "unavailable"` + reason).

## Process layout
| Process | Command | Port | Serves |
|---|---|---|---|
| Web (Flask) | `python backend/app.py` (prod: gunicorn `--chdir backend "app:create_app()"`) | 5050 | `/`, `/app`, `/auto`, `/data`, `/resources`, `/sitemap`, `/policy`, `/api/*`, `/console/*` (React dist), `/v1/*` proxy → platform API |
| Platform API | `PYTHONPATH=backend:. python -m twinsite.api` | 8080 | `/v1/*` (missions, agents, science gateway, data) |
| Worker | `PYTHONPATH=backend:. python -m twinsite.jobs` | – | mission jobs incl. 13 AI agents |
Env: `TWINSITE_API_URL` (default `http://127.0.0.1:8080`) is how Flask reaches the platform API.
`make dev` starts all three. Production: nginx → Flask on 5050 for everything except `/v1` → 8080.

## Page routes (Flask, owned by backend/routes/platform_routes.py)
`/` home (expanded landing) · `/app` existing dashboard · `/auto` Agentic Auto Mode · `/data` Data Hub ·
`/resources` Guides, docs, stack, APIs, architecture · `/sitemap` · `/policy` · `/sitemap.xml` · `/robots.txt` ·
`/console/` React mission console (frontend/dist, Vite base `/console/`, router basename `/console`).

Every Jinja page uses the shared partials:
- `templates/partials/head.html` (fonts + `static/css/site.css`)
- `templates/partials/nav.html` (top nav: Home, Mission Control `/app`, Auto Mode `/auto`, Data Hub `/data`, Console `/console/`, Resources `/resources`)
- `templates/partials/footer.html` (columns: Platform, Data & APIs, Guides & Docs, Project; links to sitemap, policy, MIT license, GitHub, NASA Space Apps)
Pass `active="<key>"` via `{% set active = 'auto' %}` before including nav.

## New JSON APIs (Flask)
### Data Hub — `/api/data` (backend/routes/data_routes.py, backend/services/datasets.py)
- `GET /api/data/datasets` → `{datasets:[{id, body, zone, stage, title, rows, columns:[...], file, bytes, resolution, license, source}]}`
  ids like `mars.harmonized`, `mars.harmonized_normalized`, `earth.processed`, `merzouga.harmonized` …
- `GET /api/data/datasets/<id>` → metadata: columns + per-column stats (min/max/mean/null %), quality flag meanings & counts, normalization params, provenance (from data_ready reports)
- `GET /api/data/datasets/<id>/records?limit=100&offset=0&bbox=minLon,minLat,maxLon,maxLat&columns=a,b&cleaning=<profile>&format=json|csv` → `{dataset, total, offset, limit, columns, rows, cleaning:{profile, removed, report}}`; csv streams with Content-Disposition. limit ≤ 5000 for json, ≤ 200000 for csv.
- `GET /api/data/cleaning` → `{profiles:[{id, name, description, steps:[...]}], default:"standard"}`
- `POST /api/data/clean` body `{dataset, profile, bbox?}` → cleaning report only (counts per step, per feature)
- `GET /api/data/sources` → merged list: bundled datasets + live platform connectors (from `/v1/science/sources` via proxy, explicit unavailable if API down)

### Cleaning algorithms — backend/services/cleaning.py
Profiles (id → behaviour), applied to a pandas DataFrame with `quality_flags` bitmask and feature columns:
- `raw` — no cleaning (provenance view)
- `standard` — DEFAULT, current engine behaviour (flags lower weights; NaN rows excluded per feature). Must reproduce existing scores exactly.
- `strict` — drop cells whose quality_flags contain estimated/proxy/gap-filled bits; physical range checks
- `robust` — strict + per-feature median/MAD outlier rejection (|robust z| > 3.5) + isolated-cell despeckle (optional)
Function: `apply(df, profile, features) -> (clean_df, report)`; report = `{profile, rows_in, rows_out, steps:[{step, removed, detail}], per_feature:{f:{removed, nulls}}}`.

### Mission options — accepted by EVERY mission entry point
JSON fields (all optional, defaults keep today's behaviour):
- `data_mode`: `"bundled"` (default; data_ready) | `"auto"` (bundled + live NASA acquisition of the target point via platform gateway `/v1/science/characterize`; results attached as `live_evidence`)
- `cleaning`: `"standard"` (default) | `"raw"` | `"strict"` | `"robust"`
Applied in: `POST /api/similarity`, `POST /api/report`, `POST /api/auto/missions`. Response echoes `options:{data_mode, cleaning}` + `cleaning_report` + (`live_evidence` when auto).
Live data helper: backend/services/live_data.py → `characterize(body, lon, lat, name) -> {status:"ok"|"unavailable", reason?, observations:[...], source_products:[...]}` (HTTP to TWINSITE_API_URL, timeout 60 s).

### Agentic Auto Mode — `/api/auto` (backend/routes/auto_routes.py, backend/services/auto_mode.py)
- `POST /api/auto/missions` body `{target:{planet, location}|{planet, lat, lon, name}, objective, slope_limit?, zones?:["atacama","merzouga"], data_mode, cleaning, ai:true|false}` → `202 {mission_id}`
- `GET /api/auto/missions/<id>` → `{mission_id, state:"running"|"completed"|"failed", steps:[{id, label, state, started, finished, detail}], options, result:{similarity summary, top regions, cleaning_report, live_evidence, platform_run_id, agents:[...], report_url}}`
- `GET /api/auto/missions` → recent list.
Steps: `plan` → `acquire` (bundled load + live when auto) → `clean` → `analyze` (similarity on all zones) → `agents` (submit `/v1/missions/match?analysis_mode=ai|simple` for Moon/Mars custom lat/lon; poll `/v1/missions/{run}` + `/agents`) → `report` (`/api/report` facts + AI narrative). A step that cannot run is `skipped` or `failed` with a reason; others continue.
State persisted as JSON under `$TWINSITE_DATA_DIR/auto/` (default `.runtime/auto/`), background thread per mission.

### AI — backend/services/ai_bridge.py
One place resolving AI for the Flask side: multi-provider free router from `twinsite.ai` (Groq, Cloudflare, Google, Mistral, OpenRouter, NVIDIA …) using keys from env or `TWINSITE_AI_SECRET_ENV_FILE`. Assistant keeps Groq tool-calling when a Groq key exists, otherwise answers through the router without tools. Report narrative uses the router. `GET /api/ai/status` → providers configured (names only, never values).

## Design system
Dark mission-control theme already in repo (`static/css/style.css`, `home.css`): bg #07080b, accent #ff7a2f / #ffb36b, glass panels with orange borders, Inter + Orbitron. New pages use `static/css/site.css` (shared tokens identical to style.css `:root`) — clean, generous spacing, no clutter, accessible contrast, mobile ≥ 360 px without horizontal scroll.

## Function contracts between lanes
- `services.analysis.run(planet, location, rover_mode=False, max_slope=15.0, zone="atacama", cleaning="standard")` (data lane) — cached; result gains `options:{cleaning}` and `cleaning_report`. `cleaning="standard"` must return exactly today's result plus those two keys.
- `services.live_data.characterize(planet, lon, lat, name)` and `services.live_data.for_target(planet, location)` (data lane) → live evidence dict, never raises.
- `services.report.build(planet, location, rover_mode, max_slope, use_ai=True, cleaning="standard", data_mode="bundled")` (data lane changes the signature/facts; auto lane changes only `narrative()`).
- `services.ai_bridge.complete_text(system, user, json_mode=False, purpose="narrative") -> {"status":"ok"|"unavailable", "text", "provider", "model", "reason"}` and `services.ai_bridge.status()` (auto lane).
- `services.cleaning.PROFILES`, `services.cleaning.apply(df, profile, features)` (data lane).

## Lane ownership (files you may create/modify)
- data: backend/services/{cleaning,datasets,live_data,analysis,similarity_engine}.py, backend/routes/{data_routes,similarity_routes,report_routes}.py, report.py `build/build_facts` only, templates/data.html, static/js/data.js, static/css/data.css, templates/index.html + static/js/app.js (mission option controls only), backend/tests/flask/test_data_*.py
- auto: backend/services/{auto_mode,ai_bridge}.py, backend/routes/{auto_routes,ai_routes,assistant_routes}.py, backend/services/assistant.py, report.py `narrative()` only, templates/auto.html, static/js/auto.js, static/css/auto.css, backend/tests/flask/test_auto_*.py
- content: templates/{home,resources,sitemap,policy,console_missing,base}.html, templates/partials/*, static/css/{site,home}.css, static/img/diagrams/*, static/js/site.js, LICENSE
- ops: frontend/** (console base path), Makefile, requirements*.txt, ops/**, vercel.json, .github/**, scripts/**, README.md, docs/** (except this spec), root *_STATUS.md moves
