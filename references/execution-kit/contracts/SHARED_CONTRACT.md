# TwinSite shared contracts — freeze before parallel implementation

Compatibility priority: reuse `ARES/contracts/mission_request.schema.json`, `mission_result.schema.json`, `production.schema.json`, `production.sql` and `api_contract.md` in the original ZIP. Do not silently rewrite cross-field semantics; version breaking changes and notify all teams.

## Routes — proposed production mapping

- `GET /v1/health` — liveness/readiness; no paid services required.
- `POST /v1/missions` — explicit run; validate input + idempotency key; return 202 with `run_id` and status URL.
- `GET /v1/missions/{run_id}` — immutable mission metadata and current status.
- `GET /v1/missions/{run_id}/events?after=<cursor>` — ordered phase/task progress events.
- `GET /v1/missions/{run_id}/result` — scored candidates, warnings, portfolios, evidence refs.
- `GET /v1/missions/{run_id}/report` — HTML/PDF reference and export metadata.
- `POST /v1/missions/{run_id}/portfolios/alternatives` — optimized alternatives from cached features, not another NASA download.
- `GET /v1/data/catalog` — curated public dataset listing (pagination/filtering).
- `GET /v1/data/{dataset_id}/records?stage=raw|cleaned|derived&limit=&cursor=` — read-only preview and provenance.
- `POST /v1/data/compare` — compare selected records/columns across approved datasets; server-controlled, bounded joins/filters; no arbitrary SQL.
- `GET /v1/data/{dataset_id}/metadata` — unit, QA rules, source license, time, geometry, product ID, transformation lineage.
- `POST /v1/uploads` — optional private user data, accept only after clear use/retention consent; capability-token per mission, never index in public catalog.

## Mission status and phases

`queued | acquiring | decoding | cleaning | validating | characterizing | analyzing | optimizing | reviewing | publishing | completed | completed_with_limits | failed | cancelled`.

Stable phase IDs: `P00 Register`, `P10 Acquire`, `P20 Decode`, `P30 Clean`, `P40 Quality`, `P50 Characterize`, `P60 Analyze`, `P70 Synthesize/Portfolio`, `P80 Review`, `P90 Publish`.

## Feature observation essential fields

`feature_id`, `site_id`, `body`, `geometry/footprint`, `value|null`, `unit`, `source_product`, `source_granule_id`, `source_url`, `source_checksum`, `observation_period`, `spatial_resolution_m`, `analysis_scale_m`, `quality_flags`, `valid_coverage_fraction`, `uncertainty`, `processing_version`, `provenance_id`, `evidence_kind`.

`evidence_kind in {direct_measurement, derived_measurement, user_assumption, model_estimate, unavailable}`. Numerical `confidence` must never be agent self-rating; report QA/coverage/sensitivity separately.

## Portfolios

Return `standalone_portfolios`, `combined_portfolios`, `rejected_candidates`, `comparison_pairs`, `strict_gate_status`, `evidence_coverage`, `weights_version`, `source_snapshot_id`, `assumptions`, `unknowns`. Keep source references to each contribution.

## No-account privacy design

No login, no RBAC, no settings page, no admin database console in public UI. Public source data are browsable via read-only API. Uploaded data remain private to an unguessable, per-mission capability token and are deleted under a documented retention policy. If capability-token security cannot be completed reliably by deadline, **disable private uploads** instead of exposing them publicly.

## Hard UI rules

Black/graphite backgrounds, warm ivory typography, low-saturation burnt-orange accent; scientific, legible, restrained. No blue neon, 3D boxes, gimmicky gauges, AI-placeholder percentages, fake health cards. Precise units, uncertainty/unknowns, time frame, evidence source and quality status must be visible on analytic views. Earth 2D must work before Earth 3D; Moon/Mars map layers must explicitly use body-aware coordinate conventions. A visual placeholder must be labeled not scientifically implemented.
