# Implementation audit

[← TwinSite](../README.md) · [Resource atlas](catalog.md) · [Every file](inventory.md)

Audited against `d485f28292946d0d4f7484619b419f407938c2d6` on 2026-11-15. This document distinguishes executable paths and committed data from upstream descriptions and future ambitions. It is a documentation audit, not a certification of scientific validity. See [verification notes](readme/VERIFICATION.md) for checks actually run.

## Component map

| Component | Implemented responsibilities | Evidence |
| :--- | :--- | :--- |
| Application factory | Home/dashboard routes, static assets, five API blueprints, data/model preload, JSON 404 | [app.py](../backend/app.py) |
| Configuration | Three data roles, nine-feature schema, quality bits, weights, uncertainty, targets, custom-region limits, zones, server and Groq settings | [config.py](../backend/utils/config.py) |
| Similarity API | Targets, zone availability/bounds, dataset status, input validation and scoring request | [routes](../backend/routes/similarity_routes.py) |
| Globe API | Physical layer catalog/PNG and target-region coverage precheck | [routes](../backend/routes/twin_routes.py) |
| ML API | Query validation and pattern-analysis response | [routes](../backend/routes/ml_routes.py) |
| Assistant API | Configuration status, question length checks, conversation/context, unavailable response | [routes](../backend/routes/assistant_routes.py) |
| Report API | Validated report request and facts/narrative/map response | [routes](../backend/routes/report_routes.py) |
| Data loader | Cached typed CSV reads, physical/normalized/processed zone roles, load summaries, spherical target-window extraction | [data_loader.py](../backend/services/data_loader.py) |
| Analysis | Preset/custom target parsing, slope/zone validation, cached shared run, target metadata and post-hoc validation attachment | [analysis.py](../backend/services/analysis.py) |
| Similarity engine | Target means, usable-feature selection, effective weights, complete-feature mask, scoring/confidence, spatial ranking, physical explanations and map payloads | [similarity_engine.py](../backend/services/similarity_engine.py) |
| Refinement | Cached accessible-land fraction; within-region water/slope filter and temperature-based point selection | [refinement.py](../backend/services/refinement.py) |
| Display layers | Physical grid indexing, percentile color ranges, PNG colorization, coverage, custom-region precheck | [layers.py](../backend/services/layers.py) |
| Unsupervised models | PCA, candidate K-means fits/silhouettes, ordered terrain names, fixed background sample, target/zone projection and score agreement | [ml_models.py](../backend/services/ml_models.py) |
| Published-site validation | Five reference locations, nearest scored cell ≤30 km, percentile/verdict, nearest top region, summary; no score mutation | [validation.py](../backend/services/validation.py) · [site JSON](../backend/data/validation_sites.json) |
| Assistant | One Groq client, nine tool schemas and functions, dashboard state, filtered history, bounded tool loop and provider error handling | [assistant.py](../backend/services/assistant.py) |
| Report | Facts from all available zones, optional Groq JSON narrative, deterministic fallback, local PNG maps | [report.py](../backend/services/report.py) |
| Home UI | Full-screen entry, planetary/terrain photography, call to action | [home.html](../templates/home.html) · [home.css](../static/css/home.css) |
| Dashboard shell | Four hash pages, shared controls, scenarios, mission bar, report entry points, assistant panel | [index.html](../templates/index.html) · [style.css](../static/css/style.css) |
| Dashboard behavior | Fetch/status/targets, score breakdown, ranking, maps, radar, mission brief, copy/link actions, application cards, both-zone searches, zone comparison, chat, validation, scatter interaction, starfield, navigation, print report | [app.js](../static/js/app.js) |
| Twin globes | Cesium viewers, ellipsoid setup, base/overlay controls, generated layer legends, opacity, automatic/manual 2D/3D, target selection, synchronized Earth marks, match list, canvas captures | [twinmap.js](../static/js/twinmap.js) |
| Historical interface | Three-file prior frontend snapshot; not loaded by the current Flask page routes | [legacy/v1](../legacy/v1/) |
| Scientific artifacts | Processed/harmonized CSVs, normalized counterparts, metadata, grids, quicklooks, normalization and validation reports, POWER JSONs | [full data inventory](inventory.md#data) |

<a id="science"></a>

## Scientific implementation details

The nominal feature weights are slope `0.15`, roughness `0.15`, relief `0.15`, day temperature `0.20`, night temperature `0.20`, albedo `0.15`, thermal inertia `0.15` and mineral index `0.10`. Available weights are normalized by their effective sum for distance. Elevation is excluded by reference-surface definition. Target uncertainty is the fraction of flagged target cells; Earth uncertainty is a per-cell boolean. Temperature estimated/fixed-time flags and albedo-proxy flags affect the weights. Gap-filled/coarse-source flags are recorded but are not additional score penalties in this implementation.

Confidence uses the **full nominal planned feature weight** as denominator, so missing Earth thermal inertia and iron reduce it even when all six active comparison features are complete. The engine requires four available shared features, and only Earth rows complete across all selected features receive a score. `require_all_features=True` guards against missing-data similarity inflation.

Ranking selects up to ten regions separated by at least 25 km. Rover filtering uses the fraction of non-water processed cells whose mean slope is within the requested limit. It affects eligibility, not scores. Refinement uses physical day/night temperature mismatch inside a region, after water/slope exclusion; it is not a second cross-planet terrain score. The returned coordinates are grid-cell centers at about 1 km resolution, not surveyed field coordinates.

PCA uses slope, roughness, relief, day/night temperature and albedo. Training samples `min(3000, complete_rows)` per body (Earth/Atacama, Mars, Moon). K-means applies weights summing to the same total per body; PCA does not use those weights. K-means excludes temperature/albedo, tries 3–6 clusters and selects by silhouette. Labels are ordered by mean normalized terrain centroid. Merzouga is an out-of-training projection. Neither model is trained on the five validation sites.

Validation percentiles use the share of scored zone cells with a **strictly lower** score. A tied-score population need not have median percentile 50. Reference sites beyond 30 km of a scored cell are unevaluated; nearby out-of-bounds sites may use an edge cell and are flagged. Verdict thresholds are ≥80 strong, ≥60 agreement, ≥40 neutral, otherwise low rank. This is a post-hoc plausibility comparison, not ground-truth validation of the whole system.

## Accuracy corrections made in the documentation

| Earlier wording / risk | Accurate description |
| :--- | :--- |
| Engine described as a placeholder / next step | `ENGINE_STATUS = "ready"`; weighted scoring, ranking and explanations are implemented. |
| Atacama-only description | Atacama and Merzouga are both configured and analyzed by the frontend. |
| `cd app` required; sibling pipeline is sole source | Run from repository root; bundled `data_ready` is the default. Sibling pipeline is only a fallback path. |
| Download/pipeline scripts treated as available | Not in the committed tree. The shipped artifacts describe upstream processing. |
| “3,000 balanced cells per body” for both models | Up to 3,000 complete cells; K-means balances weights, PCA samples without weighted fitting. |
| Universal square region described as analysis window | Globe shows an enclosing square; great-circle extraction is circular with radius 25/50/100 km. Returned `area_km2` is the enclosing square area. |
| Custom regions work identically in every assistant tool | Engine/ML/report support encoded custom locations; LLM tool schema still enumerates presets. |
| Every API has consistent errors | Similarity/ML have explicit 400/503 handling; globe endpoints have narrower handlers and can expose unhandled unavailable-data cases. |
| API status implies a provider is working | Assistant status only checks whether the key string is nonempty; the template placeholder also counts as configured. |
| Fully automated PDF endpoint | JSON facts/narrative/maps plus browser print-to-PDF. |
| A report always includes both globes and every chart | Captures/plots depend on what the browser successfully rendered; unavailable data/maps may be omitted. |
| All seven application problems solved | Several cards are heuristic/partial, target-dependent or unsupported for a body. |
| NASA validation “next step” | Five-site post-hoc checks exist; stronger independent validation remains future work. |
| Sample scores as universal results | Historical numbers depend on dataset/target/filter. No new benchmark is fabricated. |
| `.env` applies to all configuration | Paths/server settings are evaluated before the minimal `.env` loader; export those first. |
| `.env` is owner-readable by code | Git ignores it, but this code does not enforce filesystem permissions. |
| “Offline dashboard” without qualification | Local computations need no tiles; uncached browser libraries/fonts/tiles and AI require network. |
| “3D terrain” | Cesium renders ellipsoids with imagery/data overlays; no terrain elevation provider is configured. |

## Known limits that remain in application code

This branch documents these findings without changing runtime behavior:

- Globe precheck accepts three comparable features; scoring requires four. A positive precheck can still produce an analysis error.
- The assistant's location enum lists only presets. Tool text also contains older Atacama-specific wording and coarse defaults; the README does not promise full arbitrary-region chat support.
- Physical lunar temperatures mix measured bands and fallback estimates. The cold-trap card is a simple temperature heuristic, not proof of stable ice.
- The dataset catalog names upstream NDVI, aerosol and moisture sources, but these are not compared by the current engine.
- Fine field access, permits, local hazards, routes, boulders, dunes and rover mechanics are outside the score. Surface matches are not full planetary replicas.
- No production deployment, authentication, provider abstraction, pipeline rebuild scripts, or test suite existed in the audited base tree.
- Root/processed reports and harmonized reports describe distinct stages. Use the harmonized report for current scoring-grid coverage.

<a id="future"></a>

## Future boundary

The earlier planning conversation identifies **13 specialized agents**, additional scientific APIs and improved data verification as next steps. It does not supply implemented agent roles or source code. This README therefore preserves those ambitions without inventing names, architecture or completed integrations.

Other ambitions are grounded in existing source comments and missing-data records: user-adjustable weights, finer NASADEM refinement, missing thermal/mineral features, higher-resolution albedo, visual similarity and more zones. Additional AI providers and production-ready infrastructure remain unimplemented. Promote a row only after its code/data are committed and verified.
