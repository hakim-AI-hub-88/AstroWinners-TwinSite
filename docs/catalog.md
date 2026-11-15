# Resource atlas

[← Mission dossier](../README.md) · [HTTP API](#api) · [Data](#data) · [AI & models](#intelligence) · [Reports](#reports) · [Research links](#links) · [Credits](#credits) · [Every file](inventory.md)

This is a navigable inventory of the code and bundled material at base commit [`d485f28`](https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite/commit/d485f28292946d0d4f7484619b419f407938c2d6). **Implemented** means a code path exists; **bundled** means a file is committed; **upstream reference** means provenance recorded by the project, not a downloader in this repository; **planned** means absent or explicitly missing. External service availability is not implied by a catalog entry.

<a id="api"></a>

## HTTP API · eleven routes, five blueprints

Flask serves these relative to the local application origin (default `http://127.0.0.1:5050`). Page routes `/` and `/app`, and Flask's static-file route, are separate from these eleven APIs. No API authentication scheme is implemented.

| Method | Endpoint | Inputs | Response / purpose | Source |
| :--- | :--- | :--- | :--- | :--- |
| GET | `/api/targets` | None | Target names grouped under `mars` and `moon` | [similarity routes](../backend/routes/similarity_routes.py) |
| GET | `/api/zones` | None | Zone IDs, names, countries, bounds, availability and default flag | [similarity routes](../backend/routes/similarity_routes.py) |
| GET | `/api/status` | None | Dataset load/coverage summaries, features, data directory, engine status | [similarity routes](../backend/routes/similarity_routes.py) |
| POST | `/api/similarity` | JSON target, zone, rover settings | Score, confidence, ranking, comparisons, explanations, map cells, method, target and validation | [similarity routes](../backend/routes/similarity_routes.py) |
| GET | `/api/ml` | Query target, zone, rover settings | PCA positions/variance, terrain classes, silhouettes and ranking agreement | [ML routes](../backend/routes/ml_routes.py) |
| GET | `/api/layers` | `body=mars\|moon\|atacama\|merzouga` | Available physical layers, legends, rectangles, PNG URLs and radius choices | [globe routes](../backend/routes/twin_routes.py) |
| GET | `/api/layer/<body>/<feature>.png` | Body/feature in path | Cached display PNG, `image/png`; coverage or cataloged feature | [globe routes](../backend/routes/twin_routes.py) |
| GET | `/api/region-info` | `planet`, `lat`, `lon`, `radius` | Coverage, physical profile, cells, nearest preset, precheck and reusable location string | [globe routes](../backend/routes/twin_routes.py) |
| GET | `/api/assistant/status` | None | `configured`, provider and model; configuration flag does not test provider connectivity | [assistant routes](../backend/routes/assistant_routes.py) |
| POST | `/api/assistant` | `question`, optional `history`, `context` | `answer`, `tools_used`, `model`, token count | [assistant routes](../backend/routes/assistant_routes.py) |
| POST | `/api/report` | Target, rover settings, optional `use_ai` | `facts`, `narrative`, base64 PNG `maps`; attempts all configured zones | [report routes](../backend/routes/report_routes.py) |


<details>
<summary><strong>Target and rover contract</strong></summary>

- `planet`: `mars` or `moon`.
- `location`: a preset name, or the exact `location` returned by `/api/region-info`, such as `Selected region @ 18.380, 77.580 / 50 km`.
- `zone`: `atacama` or `merzouga`; omitted means Atacama. The report endpoint does not select a single zone.
- `rover_mode`: use a JSON boolean for POST requests; ML queries recognize `1`, `true`, `yes` as true. API default is false; the dashboard starts checked.
- `max_slope`: 5–30 degrees, default 15.
- `radius`: 25, 50 or 100 **km radius**, default 50. Latitude −90..90 and longitude −180..180.

`/api/similarity` returns `status: "ready"` on a successful computed result. Too few comparable features can be a JSON error result at HTTP 200. Invalid targets/settings are 400; missing data generally yields 503 on similarity/ML routes. The layer catalog validates unknown bodies with 400; unknown PNG layers/bodies are handled with 404 where caught. Missing-data and unavailable-layer failures are not uniformly normalized across every globe route.

The custom-region precheck requires three cells and three comparable features with ≥50% coverage, using the default Earth's comparable feature list. The scoring engine requires four shared features. Always inspect the actual analysis response.

</details>

<details>
<summary><strong>Copy API examples</strong></summary>

```bash
# Compare the Moroccan zone with a Mars target.
curl -X POST http://127.0.0.1:5050/api/similarity \
  -H 'Content-Type: application/json' \
  -d '{"planet":"mars","location":"Jezero Crater","zone":"merzouga","rover_mode":true,"max_slope":15}'

# Check a circle before submitting the returned location string for analysis.
curl 'http://127.0.0.1:5050/api/region-info?planet=mars&lat=18.38&lon=77.58&radius=50'

# Discover valid layer URLs rather than assuming every body has every feature.
curl 'http://127.0.0.1:5050/api/layers?body=moon'

# Pattern analysis of an existing target.
curl 'http://127.0.0.1:5050/api/ml?planet=mars&location=Jezero%20Crater&zone=merzouga&rover_mode=true&max_slope=15'

# A report without a provider call; returns JSON, not a PDF file.
curl -X POST http://127.0.0.1:5050/api/report \
  -H 'Content-Type: application/json' \
  -d '{"planet":"mars","location":"Jezero Crater","rover_mode":true,"max_slope":15,"use_ai":false}'

# Assistant (requires the server's Groq key).
curl -X POST http://127.0.0.1:5050/api/assistant \
  -H 'Content-Type: application/json' \
  -d '{"question":"Why is site 1 a candidate?","context":{"planet":"mars","location":"Jezero Crater","zone":"atacama","rover_mode":true,"max_slope":15,"selected_rank":1}}'
```

Assistant questions must be nonempty and at most 1,500 characters. History accepts user/assistant content; the last ten entries are considered and content is truncated to 4,000 characters per entry. Missing/rejected credentials, provider limits and connectivity errors lead to an unavailable response (503 when handled). There is no persistent chat storage in this code.

</details>

<a id="data"></a>

## Data and services · four distinct roles

### 1. Bundled scientific products

The app reads local CSVs; it does not call Earthdata, PDS or POWER to refresh scientific features during analysis. Product names/resolutions below are recorded in the bundled [data README](../data_ready/README.md), [harmonized validation report](../data_ready/harmonized/validation_report.md), [zone report](../data_ready/harmonized/zones_report.md) and layer metadata. Downloaders, original raw archives and pipeline scripts are not included; the committed `raw/` folders contain POWER climatology JSONs only.

| Body | Product / source family | Recorded native scale | Implemented use / status |
| :--- | :--- | :--- | :--- |
| Earth zones | NASADEM_HGT v001 · NASA Earthdata / LP DAAC | ~30 m | Bundled derived elevation, slope, roughness and relief. Terrain is harmonized to ~3.7 km pixels before ~11 km region comparison. |
| Earth zones | MODIS MOD11A2 v061 · LP DAAC | 1 km, 8-day | Bundled day/night land surface temperatures; fixed observation times, not daily extrema. |
| Earth zones | NASA POWER `ALLSKY_SRF_ALB` | 1°, climatology | Bundled albedo; raw response JSONs are included. Coarse grid, including only four values over Merzouga. |
| Earth zones | MODIS MOD13Q1 v061 | 250 m, 16-day | Upstream vegetation reference; NDVI is not a feature of this repository's cross-planet similarity engine. |
| Earth zones | MCD19A2 v061 | 1 km, daily | Upstream aerosols/water-vapor reference; not a cross-planet scoring feature. Four days recorded for Merzouga. |
| Earth zones | SMAP SPL3SMP_E · NSIDC | 9 km, daily | Upstream soil-moisture reference; not in the nine-column feature schema used here. |
| Mars | MGS MOLA MEGDR `megt90n000eb` · PDS Geosciences | 16 pixels/degree, ~3.7 km | Bundled terrain features. |
| Mars | MGS TES bolometric albedo · PDS | 8 pixels/degree | Bundled albedo and upstream input to temperature estimates. |
| Mars | MGS TES thermal inertia · PDS | 8 pixels/degree; 60° N–50° S | Bundled inertia and input to modeled temperatures; Earth lacks matching inertia. |
| Mars | Odyssey GRS Fe / Si · PDS | 5° smoothed | Fe is bundled as `mineral_index`; Si is noted upstream but is not a schema feature. Original GRS downloads are not in this repository. |
| Mars | Mars Climate Database v6.2 · LMD/ESA | Jezero point, hourly | Reference for a bundled temperature-model check; not a NASA product, runtime API or scoring input. |
| Moon | LRO LOLA LDEM_16 · PDS Geosciences | 16 pixels/degree, ~1.9 km | Bundled terrain, harmonized via ~3.79 km pixels. |
| Moon | LROC WAC 643 nm reflectance · PDS LROC | 16 pixels/degree | Bundled albedo proxy, rescaled; uncertainty flag applied. |
| Moon | Diviner GCP | 0.5° × 0.25 h local time | Measured temperatures in downloaded 0–10° N and 80–90° S bands; estimates elsewhere. |
| Moon | Diviner GDR L3 regolith temperature | 32 pixels/degree, 60° S–60° N | 00:30 temperature fallback; other nighttime values include a constant estimate. |

<details>
<summary><strong>Missing sources and future integrations — not implemented data products</strong></summary>

| Candidate | Present state |
| :--- | :--- |
| ASTER GED AG100 v003 | Missing in bundled product catalog; proposed mineral/silica source. Silica is not interchangeable with Fe without a revised scientific definition. |
| GPM IMERG monthly | Missing; precipitation is absent from the current cross-planet score. |
| Diviner thermal inertia / H-parameter | Not downloaded; Moon thermal-inertia column is empty. |
| Lunar Prospector GRS Fe | Not downloaded; lunar iron column is empty. |
| Earth thermal inertia / Fe abundance | Missing; schema is ready but comparison waits for suitable Earth data. |
| MODIS MCD43A3 albedo | Suggested finer replacement for POWER; not integrated. |
| Additional weather/geology APIs | Roadmap ambition from the project brief; no named working connector is claimed. |

</details>

<details>
<summary><strong>Schema, flags and file roles</strong></summary>

| Field | Units | Role |
| :--- | :--- | :--- |
| `latitude`, `longitude` | Degrees | Cell center; east-positive longitude |
| `elevation` | m | Displayed, excluded from score because reference surfaces differ |
| `slope` | ° | Shared terrain feature |
| `roughness`, `relief` | m | Terrain variation; correlated features each receive smaller nominal weight |
| `temperature_day`, `temperature_night` | K | Shared thermal features; measurements/estimates flagged |
| `albedo` | Unitless | Shared brightness feature; different source definitions remain a limit |
| `thermal_inertia` | J m⁻² K⁻¹ s⁻½ | Configured but missing on Earth and Moon |
| `mineral_index` | Fe wt% | Configured but missing on Earth and Moon |
| `quality_flags` | Integer bitmask | Estimated day `1`, estimated night `2`, fixed time `4`, gap filled `8`, albedo proxy `16`, coarse source `32`, water `64` |

Normalized versions use a common percentile-based 0–1 scale. `*_features_harmonized_normalized.csv.gz` drives scoring and model inputs. Physical `*_features_harmonized.csv.gz` explains the result. Processed Earth CSVs drive refinement/filtering. NPZ grids, JSON metadata and PNG quicklooks are bundled inspection artifacts; the Flask data loader uses the CSVs. The processed normalized CSVs and root normalization report describe an earlier processing scale; current scoring uses the harmonized versions.

- [Harmonized directory](../data_ready/harmonized/) · [harmonized normalization](../data_ready/harmonized/feature_normalization.json)
- [Atacama processed files](../data_ready/earth/processed/) · [Merzouga processed files](../data_ready/merzouga/processed/)
- [Mars processed files](../data_ready/mars/processed/) · [Moon processed files](../data_ready/moon/processed/)
- [Atacama POWER response](../data_ready/earth/raw/power_albedo_climatology.json) · [Merzouga POWER response](../data_ready/merzouga/raw/power_albedo_climatology.json)
- [Root normalization](../data_ready/feature_normalization.json) · [complete linked file manifest](inventory.md)

</details>

### 2. Live external map services

These URLs appear in [twinmap.js](../static/js/twinmap.js) and [app.js](../static/js/app.js). They supply visual context, **not the numerical score**. No API key is configured for these tile requests.

| Provider | Layers / external link | Behavior |
| :--- | :--- | :--- |
| [NASA Trek](https://trek.nasa.gov/) | Moon LRO WAC; Mars Viking MDIM 2.1 color mosaic; Mars MOLA color relief | XYZ-style template URLs under `https://trek.nasa.gov/tiles`, geographic tiling |
| [NASA GIBS](https://earthdata.nasa.gov/gibs) | Blue Marble Shaded Relief / Bathymetry | WMTS tiles under `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best` |
| NASA GIBS | MODIS Terra daytime land surface temperature | Globe overlay fixed to **2024-01-15**; not current weather |
| [Esri World Imagery](https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer) | Satellite basemap | Cesium Earth globe |
| [Esri boundaries and places](https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer) | Place labels/borders | Overlay enabled by default |
| [NASA Worldview](https://worldview.earthdata.nasa.gov/) | Selected field point context | Outbound mission-brief link, not an ingestion API |
| [Google Maps](https://www.google.com/maps) | Selected coordinates | Outbound mission-brief link |

<details>
<summary><strong>Exact tile layer identifiers</strong></summary>

- Moon: `LRO_WAC_Mosaic_Global_303ppd_v02`
- Mars: `Mars_Viking_MDIM21_ClrMosaic_global_232m`, `Mars_MGS_MOLA_ClrShade_merge_global_463m`
- GIBS: `BlueMarble_ShadedRelief_Bathymetry`, `MODIS_Terra_Land_Surface_Temp_Day`
- Esri: `World_Imagery`, `Reference/World_Boundaries_and_Places`

The exact template suffixes, maximum zooms, tiling schemes and attribution strings are maintained in the linked JavaScript. Cesium uses ellipsoid terrain, not a downloaded 3D elevation mesh.

</details>

### 3. Locally generated layers

`GET /api/layers` exposes **day temperature, night temperature, albedo, elevation, slope, relief, thermal inertia and iron**, when at least 2% of a body's cells contain a value. It also adds a data-coverage layer. Roughness is a scored feature but is **not** a selectable PNG layer in the current `FEATURE_STYLE` catalog.

The [layer service](../backend/services/layers.py) converts physical grids into PNGs with 2nd–98th percentile display ranges, legends and georeferenced rectangles. Coverage counts available comparable features. Similarity overlays come from analyzed map cells and rank-based colors; a color is relative to that zone's score distribution, not a universal threshold.

### 4. Browser and Python dependencies

| Dependency | Recorded version / requirement | Purpose |
| :--- | :--- | :--- |
| [CesiumJS](https://cesium.com/platform/cesiumjs/) | CDN `1.140.0`, jsDelivr | Target and Earth globes, selection, 2D/3D and captures |
| [Leaflet](https://leafletjs.com/) | CDN `1.9.4`, cdnjs | Zone and target maps |
| [Chart.js](https://www.chartjs.org/) | CDN `4.4.1`, cdnjs | Radar/scatter plots and report images |
| [Google Fonts](https://fonts.google.com/) | Inter / Orbitron | Interface/report typography |
| Flask ≥3.0 | [requirements](../requirements.txt) | Page and API server |
| pandas ≥2.2 / NumPy ≥1.26 | [requirements](../requirements.txt) | CSV loading and numerical computation |
| scikit-learn ≥1.4 | [requirements](../requirements.txt) | PCA, K-means, silhouette |
| Pillow ≥10.1 | [requirements](../requirements.txt) | Layer and report PNGs |
| Groq Python SDK ≥1.0 | [requirements](../requirements.txt) | Optional LLM calls |

These are the repository's declarations, not claims that the versions are current releases. There is no dependency lockfile in the audited snapshot.

<a id="intelligence"></a>

## AI providers and models

| Component | Implemented behavior | Evidence |
| :--- | :--- | :--- |
| **Groq** | Only LLM provider. Key: `GROQ_API_KEY`; model override: `GROQ_MODEL`; default `openai/gpt-oss-120b` | [config](../backend/utils/config.py) · [client](../backend/services/assistant.py) · [key console](https://console.groq.com/keys) |
| Mission assistant | Tool-calling chat; temperature 0.2, up to six tool rounds then a final answer; 60-second client timeout, two SDK retries | [assistant](../backend/services/assistant.py) |
| Report narrative | Same Groq client/model; JSON narrative from computed facts; deterministic fallback on failure or `use_ai=false` | [report](../backend/services/report.py) |
| PCA | Six features → two components; normalized data, fixed seed | [models](../backend/services/ml_models.py) |
| K-means | Terrain-only features; `k=3..6`, best silhouette; fixed seed and balanced body weights | [models](../backend/services/ml_models.py) |
| Other LLM providers | **Not implemented.** The `openai/` model prefix does not configure OpenAI API credentials or a second provider. | [requirements](../requirements.txt) |
| 13-agent orchestration | **Future ambition.** Nine tools are not nine independent agents. | [roadmap](../README.md#horizon) |

<details open>
<summary><strong>All nine assistant tools</strong></summary>

| Tool | Function |
| :--- | :--- |
| `run_similarity` | Best score/confidence, top regions, exact points, used/skipped features and target profile |
| `get_region_details` | One rank's physical comparison, distance shares, explanation and refined point |
| `compare_regions` | Two ranks and their per-feature comparison |
| `get_cell_at` | Containing Earth cell's score, percentile, accessible fraction and physical values |
| `compare_zones` | Both zone summaries, best regions, validation summary and score difference |
| `get_method_and_limits` | Algorithm, weights, data roles, rover rule and caveats |
| `get_validation` | Published-site ranking checks and source labels |
| `get_ml_insights` | PCA/terrain-class summaries and agreement with ranking |
| `get_dataset_info` | Recorded source names, resolution, row count, missing features and coverage |

All nine are defined and mapped in [assistant.py](../backend/services/assistant.py). Most analysis tools reuse [analysis.py](../backend/services/analysis.py). The model is instructed to derive numbers from tool results, but the prose is not independently fact-checked by another agent. Tool outputs are truncated at 12,000 characters. The tool schemas enumerate four preset locations, so custom-region conversation support is limited even though the underlying analysis supports custom locations.

</details>

<a id="reports"></a>

## Report room

| Artifact | What it contains | Status |
| :--- | :--- | :--- |
| [Harmonized validation · Markdown](../data_ready/harmonized/validation_report.md) / [JSON](../data_ready/harmonized/validation_report.json) | Four-body/zone row counts, feature coverage, source descriptions, quality flags, harmonization scales | Bundled processing snapshot |
| [Extra-zone report · Markdown](../data_ready/harmonized/zones_report.md) / [JSON](../data_ready/harmonized/zones_report.json) | Merzouga processing, missing fields, physical stats, scale excursions | Bundled processing snapshot |
| [Processed-data validation · Markdown](../data_ready/validation_report.md) / [JSON](../data_ready/validation_report.json) | Earlier common-schema processing coverage and model checks | Bundled; distinguish from harmonized report |
| [Model checks](../data_ready/model_checks.json) | Jezero Mars temperature comparison and lunar temperature-source checks | Bundled; not current runtime ML metrics |
| [Root normalization](../data_ready/feature_normalization.json) / [harmonized normalization](../data_ready/harmonized/feature_normalization.json) | Scaling bounds/metadata for different processing stages | Bundled |
| [Reference sites](../backend/data/validation_sites.json) | Five named sites, coordinates, study purpose and source links | Runtime post-hoc validation inputs |
| [Mission report service](../backend/services/report.py) | Both-zone facts, narrative and local PNG maps | Generated per request; not a stored PDF |
| [Browser report assembly](../static/js/app.js) | Comparison tables, score attribution, radar, optional atlas, globe snapshots, applications, validation and print layout | Print / Save as PDF |
| [Layer metadata and quicklooks](inventory.md#data) | Per-body/zone JSON, NPZ and PNG companions | Bundled inspection artifacts |
| [Architecture diagram](../README.md#architecture) | SVG overview and expandable Mermaid flowchart | Documentation asset |
| [Implementation audit](implementation.md) | Component inventory, mismatches, limits and future boundary | Documentation audit |

<details>
<summary><strong>Read the report workflow</strong></summary>

1. `POST /api/report` validates the target/settings and attempts analysis for every configured zone.
2. `build_facts` selects facts and top-three region summaries per available zone.
3. `zone_map_png` draws ranked regions, validation markers and a refined point over scored cells using Pillow. These generated maps do not need remote tiles.
4. `narrative` asks Groq for an executive summary, findings, recommendations, risks and conclusion, or uses `_fallback`.
5. The browser combines the response with its current dashboard, charts and available globe captures, opens a printable document and provides a print button.

A failed zone/map can be omitted; charts/globe captures depend on their browser state. The report is not a guarantee that every visual is available offline. There is no committed mission PDF or automated report archive.

</details>

<a id="links"></a>

## Research, source portals and outbound links

The project embeds these research references in [validation_sites.json](../backend/data/validation_sites.json). They are provenance links, not new validations performed by this documentation update.

| Reference site | Program / coordinates | Linked evidence |
| :--- | :--- | :--- |
| Licancabur summit lake | NASA Ames / SETI High Lakes · −22.834, −67.884 | [NASA NTRS 20030110696](https://ntrs.nasa.gov/citations/20030110696) · [coordinate reference](https://en.wikipedia.org/wiki/Licancabur_Lake) |
| Yungay | NASA Ames ARADS · −24.10, −70.01 | [NASA drilling tests](https://astrobiology.nasa.gov/news/nasa-tests-life-detection-drill-in-the-atacama-desert/) · [PANGAEA](https://doi.pangaea.de/10.1594/PANGAEA.929564) |
| Salar de Pajonales | SETI / NASA Astrobiology Institute · −25.144, −68.82 | [Frontiers study](https://www.frontiersin.org/articles/10.3389/fspas.2021.797591/full) · [coordinate reference](https://en.wikipedia.org/wiki/Salar_de_Pajonales) |
| Weyprecht base camp | Austrian Space Forum MARS2013 · 31.365, −4.071 | [Groemer et al.](https://journals.sagepub.com/doi/10.1089/ast.2013.1062) · [IAC paper](https://iafastro.directory/iac/archive/browse/IAC-13/A3/3B/19513/) · [ESA portal](https://exploration.esa.int/j/50537) |
| Payer forward camp | Austrian Space Forum MARS2013 · 30.900, −3.875 | [Groemer et al.](https://journals.sagepub.com/doi/10.1089/ast.2013.1062) · [IAC paper](https://iafastro.directory/iac/archive/browse/IAC-13/A3/3B/19513/) · [ESA portal](https://exploration.esa.int/j/50537) |

**Source discovery:** [NASA Earthdata](https://www.earthdata.nasa.gov/) · [PDS Geosciences](https://pds-geosciences.wustl.edu/) · [NASA POWER](https://power.larc.nasa.gov/) · [NSIDC](https://nsidc.org/) · [NASA Trek](https://trek.nasa.gov/) · [NASA GIBS](https://earthdata.nasa.gov/gibs). These portals are navigation aids, not additional integrations.

**Project navigation:** [repository](https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite) · [issues](https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite/issues) · [pull requests](https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite/pulls) · [design reference profile](https://github.com/desagencydes-rgb).

<a id="credits"></a>

## Image credits and rights

The original app ships home imagery and seven mission-card photographs. Exact titles, credits and NASA identifiers are preserved in the two committed credit files; the README cover is a team-supplied illustrative banner, and the README diagrams are code-generated illustrations. Neither is scientific imagery or an application screenshot.

| Collection | Images | Credit record |
| :--- | :--- | :--- |
| Home | Earth / Blue Marble, Moon, Viking Mars, Ireson Hill terrain | [Home credits](../static/img/home/credits.json) |
| Mission cards | Perseverance & Ingenuity, Curiosity traverse, environmental testing, dunes, lunar south pole, artist's habitat concept, Salar de Atacama | [Mission credits](../static/img/missions/credits.json) |
| README cover | TwinSite banner artwork (astronaut, Earth, Moon, Mars). Illustrative: its feature icons and coordinates are decorative, not app output | [Cover file](readme/assets/twinsite-cover.jpg) |
| README diagrams | Telemetry strip, navigation cards, section dividers, system diagram, animated signal | [Rebuild source and design notes](readme/README.md) |

An existing NASA image credit is not a project license. No repository-wide LICENSE file is present in the audited base snapshot; this update does not invent one. Preserve individual NASA/NOAA/JPL/GSFC/USGS/MSSS/partner credits and check source terms when reusing images.

[↑ Atlas navigation](#resource-atlas) · [Return to TwinSite](../README.md)
