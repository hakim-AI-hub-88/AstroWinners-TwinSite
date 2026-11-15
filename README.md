# Planetary Analog Discovery System

Web application for the NASA Space Apps Challenge. It finds places in the **Atacama Desert
(Earth)** whose environment resembles a selected **Mars** or **Moon** target, using NASA data
processed by the pipeline in `../pipeline/`.

Current stage: **working similarity engine**. You pick a target, and the app ranks the Atacama regions
(~11 km), explains each match, refines each region to an exact ~1 km point, and draws a similarity map.

## TWINSITE interface (current design)

- **Home page** at `/` (`templates/home.html` and `static/css/home.css`): a full-screen hero ("The next world starts here.") with the Earth, the Moon and Mars linked to an analogue site, and a "Find my analogue terrain" button. The photos are in `static/img/home/`, with their sources in `credits.json`.
- **Interactive globes** at the top of Mission Control (`static/js/twinmap.js`, CesiumJS 1.140, `backend/services/layers.py`, `routes/twin_routes.py`):
  - **Target globe.** Switch between the Moon and Mars, then click anywhere to select a square region (50, 100 or 200 km wide), or click a NASA landing site.
  - **Data check.** `GET /api/region-info` checks the harmonized data inside the region: number of cells, comparable parameters, and physical values.
  - **Analysis.** "Find Earth analogues for this region" runs the full analysis with that region as the target. It is named `Selected region @ lat, lon / R km`, so the score, pattern analysis, assistant and report all work with it unchanged.
  - **Earth globe.** It shows the similarity overlay of both zones, the numbered matches and a "Best matches" list. Clicking a match selects it in the whole dashboard and zooms the map onto it.
  - **3D and 2D.** Both globes are 3D when zoomed out and switch to a flat 2D map when zoomed in; the 2D/3D button forces the mode.
  - **Layers.**
    - Moon base map: NASA Trek LRO WAC.
    - Mars base maps: NASA Trek Viking and MOLA.
    - Earth base maps: Esri satellite imagery (with place names) and NASA GIBS Blue Marble.
    - NASA overlay: MODIS land surface temperature.
    - The project's own **harmonized data layers** (`GET /api/layers`, `GET /api/layer/<body>/<feature>.png`): day and night temperature, albedo, elevation, slope, relief, thermal inertia, iron, and data coverage.
  - **Report.** The mission report includes both globe views as displayed.
- **Dashboard** at `/app`. The pages are `/app#mission`, `/app#explorer`, `/app#science` and `/app#applications`. The TWINSITE logo links back to the home page.

The project is presented as **TWINSITE**. Its look (starfield, Earth horizon, Mars limb, glass panels,
orange accents, Orbitron and Inter fonts, mission bar) comes from the design template in `../index.html`.
All features of the previous single-page version are kept; that version is backed up in `legacy/v1/`.

The left panel (mission target, rover filter, scenarios), the mission bar and the assistant are on every
page. The results are split across **4 pages** inside one document, so changing page never reloads the analysis:

| Page | Content |
|---|---|
| `#mission` Mission Control | target and Earth-analog visual cards, mission brief, **Analog Similarity Index** (score ring), selection rationale with **"How the score is built"**, candidate sites, parameter comparison |
| `#explorer` Site Explorer | Atacama and Merzouga similarity maps, target map (NASA Trek), environmental-signature radar, Analog Zone Benchmark |
| `#science` Science & Validation | Cross-Planet Pattern Analysis (Planetary Environment Atlas = PCA, Terrain Signature Classes = K-means), field validation, methodology |
| `#applications` Applications & Report | 7 mission-application **photo cards** (each with a headline metric and a status), **Mission Report** |

- **Explainable score.** Score = 100 × (1 − d), where d² is the sum of the weighted squared differences
  of all compared parameters. The points lost, 100 − score, are therefore split exactly by each
  parameter's share of d². For example, Jezero vs the Atacama: 100 − 13.2 = 86.8, of which night temperature costs 11.4 points.
- **Photos:** NASA public-domain images in `static/img/missions/`. Their sources are listed in `credits.json`.
- **Mission report** (`POST /api/report`, `backend/services/report.py`):
  - the backend analyses both zones and draws one PNG similarity map per zone with Pillow (no external tiles);
  - the Groq LLM writes the executive summary, findings, recommendations and risks from these facts only, in JSON mode. Without a key or a network connection, a deterministic summary is used instead;
  - the browser adds the tables, radar, atlas, photo cards, validation and methodology, then opens a printable page. Use "Print / Save as PDF" to export it.
  - Open it from the Applications page, the mission bar, or the assistant's "Generate mission report" chip.

## Data roles (never mixed)

| Data | Files | Used for |
|---|---|---|
| Harmonized + normalized (0–1) | `*_features_harmonized_normalized.csv.gz` | **Scoring and ranking only** |
| Harmonized, physical units | `*_features_harmonized.csv.gz` | **Explanations only** (K, °, m shown to the user) |
| Earth processed (~1 km) | `pipeline/data_ready/earth/processed/earth_features.csv` | **Refinement only**: exact point inside a top region |

## How the score works (`backend/services/similarity_engine.py`)

1. **Target profile:** mean normalized features of the cells within 50 km of the target.
2. **Features compared:** those valid on both sides.
   - `elevation` is excluded: each body has a different reference surface.
   - `thermal_inertia` and `mineral_index` join automatically once Earth has data.
3. **Weighted distance:** `d = sqrt(Σ w (x − t)² / Σ w)` and `score = 100 × (1 − d)`.
   - Values flagged uncertain (estimated temperatures, proxy albedo) get 30 % less weight.
   - Only cells with **every** compared feature are scored; otherwise missing data would inflate the score.
4. **Confidence:** the share of the planned evidence that was available and reliable.
5. **Ranking:** the top 10 regions, at least 25 km apart.
6. **Refinement** (`refinement.py`): inside each region, the 1 km cell with no water, slope ≤ 15°, and day/night temperatures closest to the target.

Weights, penalty, separation and thresholds are set in `backend/utils/config.py`.

**Typical results:** Jezero 87, Gale 87, Mare Tranquillitatis 63, Apollo 15 70. The Atacama is clearly
more Mars-like than Moon-like. Night temperature dominates the remaining difference: Atacama nights are 85–180 K warmer.

## Targets

| Planet | Location | Lat, Lon | Why |
|---|---|---|---|
| Mars | Jezero Crater | 18.38, 77.58 | Perseverance site, ancient delta |
| Mars | Gale Crater | −5.40, 137.80 | Curiosity site, layered sediments |
| Moon | Mare Tranquillitatis | 8.50, 31.40 | Apollo 11 region, basaltic plains |
| Moon | Apollo 15 | 26.13, 3.63 | Hadley Rille, mare/highland boundary |

Targets are defined in `backend/utils/config.py`.

## Architecture

```
app/
├── backend/
│   ├── app.py                     Flask entry point (create_app, page route, data preload)
│   ├── routes/
│   │   └── similarity_routes.py   /api/targets, /api/status, /api/similarity
│   ├── services/
│   │   ├── data_loader.py         load_earth_data / load_mars_data / load_moon_data (pandas)
│   │   └── similarity_engine.py   PLACEHOLDER: compute() contract for the next step
│   ├── utils/
│   │   └── config.py              paths, targets, features, server settings
│   └── README.md                  backend details
├── templates/
│   └── index.html                 the whole interface (one Jinja2 template)
├── static/
│   ├── css/style.css              dashboard design (responsive)
│   └── js/app.js                  vanilla JS: calls the API, fills the dashboard
├── requirements.txt
└── README.md
```

```
browser (index.html + app.js) ──fetch──► Flask routes ──► data_loader ──► pipeline/data_ready/harmonized/*.csv.gz
                                                      └──► similarity_engine.compute()  (next step)
```

The data is **read in place** from `../pipeline/data_ready/harmonized/` and never copied.
It is loaded once at start-up and kept in memory.

## Run

```bash
cd app
python3 -m venv .venv                     # local Python environment (not committed)
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                      # then put your own GROQ_API_KEY in .env
python backend/app.py                     # http://127.0.0.1:5050 (home) · /app (dashboard)
```

- **Self-contained data:** the app reads `app/data_ready/`, a copy of the pipeline output `pipeline/data_ready/`
  (harmonized Earth/Mars/Moon/Merzouga features, 1 km Earth data, validation reports). Without that folder it
  falls back to `../pipeline/data_ready/`; `DATA_READY_DIR=/path` overrides both.
- **Secrets:** keys live only in `app/.env` (git-ignored). `.env.example` shows the expected variables.

- **Backend and frontend run together.** Flask serves the page (`/`), the static files and the API.
- **Start-up time:** about 15 s, mostly reading the Mars file (1.8 million cells).
- **Settings** (environment variables):
  - `APP_PORT`: server port, default 5050.
  - `APP_DEBUG=1`: Flask debug mode.
  - `HARMONIZED_DATA_DIR`: use another data folder.
- **Data must exist first.** If it doesn't, run the pipeline in `../pipeline`:
  `run_pipeline.py`, then `run_planetary.py`, then `run_harmonize.py`.

## API

| Method | Route | Returns |
|---|---|---|
| GET | `/api/targets` | `{"mars": ["Jezero Crater", "Gale Crater"], "moon": ["Mare Tranquillitatis", "Apollo 15"]}` |
| GET | `/api/status` | Per body: loaded, rows, available and missing features, coverage |
| POST | `/api/report` | Body `{"planet", "location", "rover_mode", "max_slope", "use_ai"}`. Returns facts for both zones, the AI narrative and map PNGs (base64). |
| POST | `/api/similarity` | Body `{"planet": "mars", "location": "Jezero Crater"}`. Returns the placeholder answer plus the target information (cells within 50 km, mean feature profile). |

## Two Earth analog zones: Atacama (Chile) + Merzouga (Morocco)

Both zones go through the same pipeline: Earth pipeline, then common schema, then ~11 km harmonization (`pipeline/run_zones.py`).
They share the **same 0–1 scale**, so their scores can be compared directly. The Atacama stays the **default zone**: without a `zone` parameter, every endpoint behaves as before.

- **Zone selector** in the search form. Every search analyses **both** zones; the selector, the comparison buttons or a click on a zone map decide which zone drives the ranking, brief, radar, use cases, validation, ML and assistant.
- **Two Leaflet maps:** the original Atacama map, plus a **Merzouga-only map**. Both show similarity colours, numbered top regions and validation sites (▲). An "analysed zone" badge marks the active one.
- **"Earth analog zones compared" card:**
  - both best scores, side by side;
  - the closer analog and the point difference;
  - a feature table (target vs each zone's best region, physical values, ✓ = closer on the scoring scale).
- **Validation in Merzouga:** the Austrian Space Forum **MARS2013** Mars simulation camps (base "Weyprecht" 31.365° N 4.071° W; forward camp "Payer" 30.900° N 3.875° W).
  - Sources: Groemer et al. 2014, *Astrobiology* 14:360; IAC 2013 paper; ESA exploration portal.
  - For Jezero, Weyprecht ranks at the **83rd percentile**.
- **ML:** the models are still trained on Atacama, Mars and Moon (results unchanged); Merzouga is projected with the same fitted models.
- **AI assistant:** every tool accepts `zone`, and a new `compare_zones` tool compares the two zones.

**API**
- `GET /api/zones`
- `POST /api/similarity` with `"zone": "atacama" | "merzouga"`
- `GET /api/ml?...&zone=merzouga`

**Results** (rover filter at 15°):

| Target | Atacama | Merzouga |
|---|---|---|
| Jezero | 86.8 | 81.2 |
| Gale | 87.1 | 81.7 |
| Apollo 15 | 69.7 | 62.8 |
| Mare Tranquillitatis | 63.3 | 57.5 |

The Atacama is the closer analog, because its nights are colder and its terrain rougher.

**Known limits**
- **Albedo** (NASA POWER, 1°) has only 4 values over Merzouga, which creates a visible step at 4° W in the Merzouga ranking. A finer albedo source (e.g. MODIS MCD43A3, 500 m) would remove it.
- At ~3.7 km, the features cannot see dune shapes (Erg Chebbi).

## Mission planner (use case)

> *An agency is preparing a rover for Jezero. Where should it test it on Earth?*
> The tool answers in one click, with evidence.

- **4 one-click scenarios:**

  | Scenario | Target | Slope limit |
  |---|---|---|
  | Perseverance-class rover test | Jezero | ≤ 15° |
  | Curiosity-class drive & drill | Gale | ≤ 15° |
  | Astronaut EVA + lunar rover training | Apollo 15 | ≤ 10° |
  | Lander site rehearsal | Mare Tranquillitatis | ≤ 8° |

- **Rover-accessible filter** (toggle + slider, 5–30°). A region (~11 km) is proposed only if at least 50 % of its land 1 km cells have a mean slope at or below the limit.
  - It uses the **Earth processed data** (1 km means of 30 m NASADEM slopes).
  - It **never changes scores**; it only restricts which regions are proposed.
  - The exact point also respects the limit.
  - Non-drivable regions are shown in grey on the map.
- **Mission brief:**
  - the question;
  - the answer (exact coordinates, score, confidence, drivable share, slope and elevation of the point);
  - evidence (closest matches, rank, NASA datasets used);
  - limits to plan for;
  - links to open the point in **NASA Worldview** or Google Maps, and a **Copy brief** button (plain text for an email or report).
- **API:** `POST /api/similarity` also accepts `"rover_mode": true` and `"max_slope": 5–30`.

## Machine-learning models (section after the maps)

Two **unsupervised** scikit-learn models, independent of the similarity score, so the jury can see whether different methods agree.

**Training rules**
- Harmonized **normalized** data only.
- A **balanced sample** of 3,000 cells per body, so Mars (1.8 M cells) does not dominate.
- Fixed random seed.
- Trained once at server start (~5 s).
- **No labels:** the NASA validation sites are never used.

| Model | Method | Features | Result |
|---|---|---|---|
| **A · Planetary environment space** | PCA, 2 components | slope, roughness, relief, day/night temperature, albedo | 2-D map keeps **80 %** of the variance. The Atacama is **1.8× closer to Mars than to the Moon** (centroid distance 0.50 vs 0.89). |
| **B · Terrain types** | K-means; k chosen by **silhouette** (k = 3, 0.61) | slope, roughness, relief | 3 types shared by all bodies: flat plains, gentle/rolling, rugged |

**Why some features are left out of the terrain types**
- **Temperatures:** with them, the clusters simply separate the bodies, because Atacama nights are much warmer (Model A already shows this).
- **Albedo:** each body uses a different instrument, which lowered the silhouette to 0.39.

**Agreement with the similarity ranking:** share of top-10 regions that have the target's terrain type.

| Target | Top-10 regions of the target's type |
|---|---|
| Jezero | 9 / 10 |
| Apollo 15 | 10 / 10 |
| Mare Tranquillitatis | 10 / 10 |
| Gale | 0 / 10 |

Gale's area is only 39 % rugged terrain, and the Atacama has 2.5 % of that type. The page shows this as a limit.

**Interactive features**
- Scatter coloured by body or by terrain type.
- Click an Atacama point to update the radar and the map.
- "Show on the Atacama map" overlays one terrain type on the Leaflet map.
- The AI assistant has a `get_ml_insights` tool.

**Code and API:** `services/ml_models.py`, `routes/ml_routes.py`, and `GET /api/ml?planet=&location=&rover_mode=&max_slope=`.

## Validation against NASA analog sites (bottom of the page)

After each analysis, we check where Atacama sites that NASA or NASA-funded teams **already studied as Mars analogs** fall in our ranking.
- **The model is not changed** and the sites are **never an input** to the score.
- `services/validation.py` only reads results that were already computed.
- The sites and their sources are in `backend/data/validation_sites.json`.

| Site | Program | Coordinates (source) |
|---|---|---|
| Licancabur summit lake | NASA Ames / SETI High Lakes Project | 22.834° S, 67.884° W (Wikipedia; NASA NTRS 20030110696) |
| Yungay hyperarid site | NASA Ames ARADS rover drilling tests | 24.10° S, 70.01° W (PANGAEA 10.1594/PANGAEA.929564) |
| Salar de Pajonales | SETI / NASA Astrobiology Institute | 25.144° S, 68.82° W (Wikipedia; Frontiers 2022) |

**Metrics for each site**
- **Score and percentile** of the closest ~11 km cell ("better than X % of Atacama cells"; a random site averages 50 %).
- **Nearest top-10 region** and its distance.
- **Verdict:** ≥ 80 % strong agreement, ≥ 60 % agreement, 40–60 % neutral, below that low rank.

**Results (rover filter at 15°)**

| Target | Licancabur | Yungay | Salar de Pajonales |
|---|---|---|---|
| Gale Crater | **99th percentile** | 26 | 19 |
| Jezero Crater | 5 | 28 | **75th percentile** |

**Interpretation, shown honestly on the page**
- Each site matches a different kind of target: Licancabur, a rugged volcanic crater, matches Gale; Pajonales, a salt-flat basin, matches Jezero.
- Yungay was chosen for **dryness**, which the cross-planet features do not compare. That is a limit of the method.
- María Elena South was not included: no published coordinates were found.

The NASA sites appear as ▲ on the Atacama map. The AI assistant has a `get_validation` tool.

## AI Mission Assistant

The **"Ask the mission assistant"** button (bottom right) opens a chat. You can ask, for example:
- "Why is site #1 better than #3?"
- "Can my rover drive at 24.1 S, 66.6 W?"
- "Explain this score like I'm 10"

It answers in English or French.

**How it works**
- **LLM:** Groq (`openai/gpt-oss-120b`, change it with the `GROQ_MODEL` variable) with **tool calling**.
- **The LLM computes nothing itself.** It calls tools that run the project's own analysis (`services/analysis.py`, the same code as the dashboard):

  | Tool | What it returns |
  |---|---|
  | `run_similarity` | Score, top 10 regions, exact points, features used |
  | `get_region_details` | Physical values per feature and each feature's share of the distance |
  | `compare_regions` | Why one rank beats another |
  | `get_cell_at` | Score and drivability of any point in the area |
  | `get_method_and_limits` | Algorithm, weights, data roles, known limits |
  | `get_dataset_info` | NASA datasets, resolution and coverage per body |

- **Dashboard state:** the browser sends the current target, rover filter and selected region, so "site #1" is the region the user sees.
- **System prompt rules:** every number must come from a tool, and the relevant limits are always stated.
- Each answer shows which tools were used.

**Setup**
- `pip install -r requirements.txt` (includes `groq`).
- Put the key in **`app/.env`**: `GROQ_API_KEY=...`. That file is git-ignored and readable only by its owner; the key is never sent to the browser.
- Without a key, or without internet, the assistant shows "unavailable" and the rest of the app keeps working.

**API**
- `GET /api/assistant/status`
- `POST /api/assistant` with `{"question", "history"?, "context"?}`
- Code: `backend/services/assistant.py` and `backend/routes/assistant_routes.py`.

## Problems this study can solve (bottom of the page)

Seven questions are listed before any search. After each **Find Earth Analogs**, each one gets an answer
computed for the selected target, using physical values only (the explanation role of the data).

| # | Question | Mars target | Moon target |
|---|---|---|---|
| 1 | Where to test a rover in the Atacama? | ✅ top 3 regions + exact point | ✅ |
| 2 | Can a rover drive here? | ✅ drivable share, slope of the point, target terrain | ✅ |
| 3 | What temperatures must the hardware survive? | ✅ target vs test-site range in °C | ✅ |
| 4 | Is the ground dust, sand or rock? | 🟡 class from TES thermal inertia (< 100 dust, < 350 sand, else rock) | ⛔ no lunar thermal-inertia map yet |
| 5 | Where could water ice survive on the Moon? | ⛔ not applicable | 🟡 daytime maximum vs the ~110 K stability limit |
| 6 | Where to build a base? | ✅ slope, thermal swing, GRS iron | 🟡 no lunar iron map yet |
| 7 | Why does the Atacama resemble Mars? | ✅ score + closest and most different features | ✅ |

The logic lives in `static/js/app.js` (`USE_CASES`, `useCaseAnswers`). Badges: ✅ answered, 🟡 partial, ⛔ not applicable or no data.

## Interactive maps

| Map | Library | Basemap (official NASA tiles, no API key) |
|---|---|---|
| Atacama similarity map | Leaflet 1.9.4 | NASA GIBS *Blue Marble shaded relief* |
| Mars target | Leaflet, `L.CRS.EPSG4326` | NASA Trek *Viking MDIM 2.1 colour mosaic* / *MOLA colour relief* (switchable) |
| Moon target | Leaflet, `L.CRS.EPSG4326` | NASA Trek *LRO WAC global mosaic* |
| Radar chart | Chart.js 4.4.1 | — |

- **Atacama map:** one square per ~11 km cell. The colour is the **rank** of its score among Atacama cells (red = most similar, blue = least), because scores are often packed in a narrow band. The legend shows the real score range.
- **Click a square** to see target vs that cell on the radar. Clicking a ranked region (or its number) updates every card.
- **Target map:** the circle shows the 50 km area averaged into the target profile, drawn with the body's own radius.
- **Radar:** axes use the normalized scale (the same one as the score); tooltips show physical values.

Leaflet, Chart.js and the tiles load from the internet, so the demo needs a connection. Without one, the rest of the dashboard still works.

## Possible next steps

- **Validation:** check that Atacama sites already used for Mars rover tests rank well.
- **Weight sliders** in the interface (the engine already reads weights from config).
- **Finer refinement** with NASADEM 30 m (local slope and roughness).
# twinsite
