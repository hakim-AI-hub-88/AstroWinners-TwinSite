# Complete repository inventory

[← TwinSite](../README.md) · [Resource atlas](catalog.md) · [Implementation audit](implementation.md)

Every tracked path in the audited base commit `d485f28292946d0d4f7484619b419f407938c2d6` is linked below. Generated documentation added by this redesign is listed separately. Dataset grids and image assets are artifacts, not additional runtime integrations.

## Application and configuration

| File | Role |
| :--- | :--- |
| [.env.example](../.env.example) | Optional Groq configuration template |
| [.gitignore](../.gitignore) | Local secret/cache/environment exclusions |
| [README.md](../README.md) | Primary mission dossier |
| [backend/README.md](../backend/README.md) | Backend documentation entry point |
| [backend/app.py](../backend/app.py) | Flask factory, page routes and preload |
| [backend/data/validation_sites.json](../backend/data/validation_sites.json) | Five published reference sites and sources |
| [backend/routes/__init__.py](../backend/routes/__init__.py) | Python package marker |
| [backend/routes/assistant_routes.py](../backend/routes/assistant_routes.py) | Flask endpoint blueprint · see API atlas |
| [backend/routes/ml_routes.py](../backend/routes/ml_routes.py) | Flask endpoint blueprint · see API atlas |
| [backend/routes/report_routes.py](../backend/routes/report_routes.py) | Flask endpoint blueprint · see API atlas |
| [backend/routes/similarity_routes.py](../backend/routes/similarity_routes.py) | Flask endpoint blueprint · see API atlas |
| [backend/routes/twin_routes.py](../backend/routes/twin_routes.py) | Flask endpoint blueprint · see API atlas |
| [backend/services/__init__.py](../backend/services/__init__.py) | Python package marker |
| [backend/services/analysis.py](../backend/services/analysis.py) | Runtime service · see component audit |
| [backend/services/assistant.py](../backend/services/assistant.py) | Runtime service · see component audit |
| [backend/services/data_loader.py](../backend/services/data_loader.py) | Runtime service · see component audit |
| [backend/services/layers.py](../backend/services/layers.py) | Runtime service · see component audit |
| [backend/services/ml_models.py](../backend/services/ml_models.py) | Runtime service · see component audit |
| [backend/services/refinement.py](../backend/services/refinement.py) | Runtime service · see component audit |
| [backend/services/report.py](../backend/services/report.py) | Runtime service · see component audit |
| [backend/services/similarity_engine.py](../backend/services/similarity_engine.py) | Runtime service · see component audit |
| [backend/services/validation.py](../backend/services/validation.py) | Runtime service · see component audit |
| [backend/utils/__init__.py](../backend/utils/__init__.py) | Python package marker |
| [backend/utils/config.py](../backend/utils/config.py) | Paths, schema, scoring, targets, zones and AI settings |
| [requirements.txt](../requirements.txt) | Python dependency declarations |
| [static/css/home.css](../static/css/home.css) | Home styling |
| [static/css/style.css](../static/css/style.css) | Dashboard styling |
| [static/js/app.js](../static/js/app.js) | Dashboard, maps, charts, assistant and reports |
| [static/js/twinmap.js](../static/js/twinmap.js) | Cesium twin-globe controller |
| [templates/home.html](../templates/home.html) | Home page template |
| [templates/index.html](../templates/index.html) | Four-page dashboard template |

## Data

| File | Role |
| :--- | :--- |
| [data_ready/README.md](../data_ready/README.md) | Upstream product catalog, schema and flags |
| [data_ready/earth/processed/earth_features.csv](../data_ready/earth/processed/earth_features.csv) | Physical-unit features · processed grid |
| [data_ready/earth/processed/earth_features_normalized.csv](../data_ready/earth/processed/earth_features_normalized.csv) | Normalized features · processed grid |
| [data_ready/earth/processed/earth_layers.json](../data_ready/earth/processed/earth_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/earth/processed/earth_layers.npz](../data_ready/earth/processed/earth_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/earth/processed/earth_quicklook.png](../data_ready/earth/processed/earth_quicklook.png) | Bundled quicklook visualization |
| [data_ready/earth/raw/power_albedo_climatology.json](../data_ready/earth/raw/power_albedo_climatology.json) | Bundled NASA POWER climatology response |
| [data_ready/feature_normalization.json](../data_ready/feature_normalization.json) | Scaling metadata for this processing stage |
| [data_ready/harmonized/earth_features_harmonized.csv.gz](../data_ready/harmonized/earth_features_harmonized.csv.gz) | Physical-unit features · harmonized scoring grid |
| [data_ready/harmonized/earth_features_harmonized_normalized.csv.gz](../data_ready/harmonized/earth_features_harmonized_normalized.csv.gz) | Normalized features · harmonized scoring grid |
| [data_ready/harmonized/earth_harmonized_layers.json](../data_ready/harmonized/earth_harmonized_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/harmonized/earth_harmonized_layers.npz](../data_ready/harmonized/earth_harmonized_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/harmonized/earth_harmonized_quicklook.png](../data_ready/harmonized/earth_harmonized_quicklook.png) | Bundled quicklook visualization |
| [data_ready/harmonized/feature_normalization.json](../data_ready/harmonized/feature_normalization.json) | Scaling metadata for this processing stage |
| [data_ready/harmonized/mars_features_harmonized.csv.gz](../data_ready/harmonized/mars_features_harmonized.csv.gz) | Physical-unit features · harmonized scoring grid |
| [data_ready/harmonized/mars_features_harmonized_normalized.csv.gz](../data_ready/harmonized/mars_features_harmonized_normalized.csv.gz) | Normalized features · harmonized scoring grid |
| [data_ready/harmonized/mars_harmonized_layers.json](../data_ready/harmonized/mars_harmonized_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/harmonized/mars_harmonized_layers.npz](../data_ready/harmonized/mars_harmonized_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/harmonized/mars_harmonized_quicklook.png](../data_ready/harmonized/mars_harmonized_quicklook.png) | Bundled quicklook visualization |
| [data_ready/harmonized/merzouga_features_harmonized.csv.gz](../data_ready/harmonized/merzouga_features_harmonized.csv.gz) | Physical-unit features · harmonized scoring grid |
| [data_ready/harmonized/merzouga_features_harmonized_normalized.csv.gz](../data_ready/harmonized/merzouga_features_harmonized_normalized.csv.gz) | Normalized features · harmonized scoring grid |
| [data_ready/harmonized/merzouga_harmonized_layers.json](../data_ready/harmonized/merzouga_harmonized_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/harmonized/merzouga_harmonized_layers.npz](../data_ready/harmonized/merzouga_harmonized_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/harmonized/merzouga_harmonized_quicklook.png](../data_ready/harmonized/merzouga_harmonized_quicklook.png) | Bundled quicklook visualization |
| [data_ready/harmonized/moon_features_harmonized.csv.gz](../data_ready/harmonized/moon_features_harmonized.csv.gz) | Physical-unit features · harmonized scoring grid |
| [data_ready/harmonized/moon_features_harmonized_normalized.csv.gz](../data_ready/harmonized/moon_features_harmonized_normalized.csv.gz) | Normalized features · harmonized scoring grid |
| [data_ready/harmonized/moon_harmonized_layers.json](../data_ready/harmonized/moon_harmonized_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/harmonized/moon_harmonized_layers.npz](../data_ready/harmonized/moon_harmonized_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/harmonized/moon_harmonized_quicklook.png](../data_ready/harmonized/moon_harmonized_quicklook.png) | Bundled quicklook visualization |
| [data_ready/harmonized/validation_report.json](../data_ready/harmonized/validation_report.json) | Feature coverage, provenance and processing checks |
| [data_ready/harmonized/validation_report.md](../data_ready/harmonized/validation_report.md) | Feature coverage, provenance and processing checks |
| [data_ready/harmonized/zones_report.json](../data_ready/harmonized/zones_report.json) | Extra Earth-zone preprocessing report |
| [data_ready/harmonized/zones_report.md](../data_ready/harmonized/zones_report.md) | Extra Earth-zone preprocessing report |
| [data_ready/mars/processed/mars_features.csv](../data_ready/mars/processed/mars_features.csv) | Physical-unit features · processed grid |
| [data_ready/mars/processed/mars_features_normalized.csv](../data_ready/mars/processed/mars_features_normalized.csv) | Normalized features · processed grid |
| [data_ready/mars/processed/mars_layers.json](../data_ready/mars/processed/mars_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/mars/processed/mars_layers.npz](../data_ready/mars/processed/mars_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/mars/processed/mars_quicklook.png](../data_ready/mars/processed/mars_quicklook.png) | Bundled quicklook visualization |
| [data_ready/merzouga/processed/merzouga_features.csv](../data_ready/merzouga/processed/merzouga_features.csv) | Physical-unit features · processed grid |
| [data_ready/merzouga/processed/merzouga_features_normalized.csv](../data_ready/merzouga/processed/merzouga_features_normalized.csv) | Normalized features · processed grid |
| [data_ready/merzouga/processed/merzouga_layers.json](../data_ready/merzouga/processed/merzouga_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/merzouga/processed/merzouga_layers.npz](../data_ready/merzouga/processed/merzouga_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/merzouga/processed/merzouga_quicklook.png](../data_ready/merzouga/processed/merzouga_quicklook.png) | Bundled quicklook visualization |
| [data_ready/merzouga/raw/power_albedo_climatology.json](../data_ready/merzouga/raw/power_albedo_climatology.json) | Bundled NASA POWER climatology response |
| [data_ready/model_checks.json](../data_ready/model_checks.json) | Recorded thermal-model reference checks |
| [data_ready/moon/processed/moon_features.csv](../data_ready/moon/processed/moon_features.csv) | Physical-unit features · processed grid |
| [data_ready/moon/processed/moon_features_normalized.csv](../data_ready/moon/processed/moon_features_normalized.csv) | Normalized features · processed grid |
| [data_ready/moon/processed/moon_layers.json](../data_ready/moon/processed/moon_layers.json) | Layer sources, grid resolution and processing metadata |
| [data_ready/moon/processed/moon_layers.npz](../data_ready/moon/processed/moon_layers.npz) | Bundled gridded arrays for inspection |
| [data_ready/moon/processed/moon_quicklook.png](../data_ready/moon/processed/moon_quicklook.png) | Bundled quicklook visualization |
| [data_ready/validation_report.json](../data_ready/validation_report.json) | Feature coverage, provenance and processing checks |
| [data_ready/validation_report.md](../data_ready/validation_report.md) | Feature coverage, provenance and processing checks |

## Application imagery

| File | Role |
| :--- | :--- |
| [static/img/home/credits.json](../static/img/home/credits.json) | Image attribution and source URLs |
| [static/img/home/earth.jpg](../static/img/home/earth.jpg) | Application photograph · see collection credit record |
| [static/img/home/mars.jpg](../static/img/home/mars.jpg) | Application photograph · see collection credit record |
| [static/img/home/moon.jpg](../static/img/home/moon.jpg) | Application photograph · see collection credit record |
| [static/img/home/terrain.jpg](../static/img/home/terrain.jpg) | Application photograph · see collection credit record |
| [static/img/missions/analogs.jpg](../static/img/missions/analogs.jpg) | Application photograph · see collection credit record |
| [static/img/missions/base.jpg](../static/img/missions/base.jpg) | Application photograph · see collection credit record |
| [static/img/missions/credits.json](../static/img/missions/credits.json) | Image attribution and source URLs |
| [static/img/missions/ice.jpg](../static/img/missions/ice.jpg) | Application photograph · see collection credit record |
| [static/img/missions/outreach.jpg](../static/img/missions/outreach.jpg) | Application photograph · see collection credit record |
| [static/img/missions/soil.jpg](../static/img/missions/soil.jpg) | Application photograph · see collection credit record |
| [static/img/missions/thermal.jpg](../static/img/missions/thermal.jpg) | Application photograph · see collection credit record |
| [static/img/missions/traverse.jpg](../static/img/missions/traverse.jpg) | Application photograph · see collection credit record |

## Historical interface

| File | Role |
| :--- | :--- |
| [legacy/v1/app.js](../legacy/v1/app.js) | Historical frontend snapshot; not served by current routes |
| [legacy/v1/index.html](../legacy/v1/index.html) | Historical frontend snapshot; not served by current routes |
| [legacy/v1/style.css](../legacy/v1/style.css) | Historical frontend snapshot; not served by current routes |

## Documentation added by the redesign

| File | Role |
| :--- | :--- |
| [catalog.md](catalog.md) | API, data, AI, reports and external references |
| [implementation.md](implementation.md) | Code-backed feature and limitation audit |
| [inventory.md](inventory.md) | This complete base-snapshot manifest |
| [readme/README.md](readme/README.md) | Visual system, accessibility, GitHub limits and asset maintenance |
| [readme/VERIFICATION.md](readme/VERIFICATION.md) | Actual verification results |
| [readme/build_assets.py](readme/build_assets.py) | Original illustration and animation generator |
| [readme/assets/architecture.svg](readme/assets/architecture.svg) | Committed README visual asset |
| [readme/assets/telemetry.svg](readme/assets/telemetry.svg) | Committed README visual asset |
| [readme/assets/twinsite-cover.jpg](readme/assets/twinsite-cover.jpg) | Committed README cover artwork |
| [readme/assets/nav-data.svg](readme/assets/nav-data.svg) | Committed README visual asset |
| [readme/assets/nav-intelligence.svg](readme/assets/nav-intelligence.svg) | Committed README visual asset |
| [readme/assets/nav-mission.svg](readme/assets/nav-mission.svg) | Committed README visual asset |
| [readme/assets/nav-reports.svg](readme/assets/nav-reports.svg) | Committed README visual asset |
| [readme/assets/section-01.svg](readme/assets/section-01.svg) | Committed README visual asset |
| [readme/assets/section-02.svg](readme/assets/section-02.svg) | Committed README visual asset |
| [readme/assets/section-03.svg](readme/assets/section-03.svg) | Committed README visual asset |
| [readme/assets/section-04.svg](readme/assets/section-04.svg) | Committed README visual asset |
| [readme/assets/section-05.svg](readme/assets/section-05.svg) | Committed README visual asset |
| [readme/assets/signal-static.png](readme/assets/signal-static.png) | Committed README visual asset |
| [readme/assets/signal.gif](readme/assets/signal.gif) | Committed README visual asset |

**Base inventory: 99 files.** The base commit contains no `LICENSE`, pipeline scripts, CI configuration, agent orchestrator, deployment manifest or automated test suite.
