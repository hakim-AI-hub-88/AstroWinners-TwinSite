# HTTP API and data contracts

Every MissionRequest requires mode, start_trigger=user_request, 1–3 scope.locations with at most one site-or-zone selection per body, and target_profiles for each requested planetary target. Earth anchors require compare_with containing Moon, Mars or both. Planetary-only anchors automatically compare with Earth and permit omitted compare_with or ["Earth"]. Earth candidates are filtered to a selected Earth footprint when present; otherwise the supplied Earth catalog is eligible. The server creates jobs only through explicit POST requests. The service validates cross-field body, target-location and unit rules in addition to the published JSON Schema.

## Runnable sample API

All responses use UTF-8 JSON except the HTML report and web assets. Local origin is `http://127.0.0.1:8080`. The sample request schema is `mission_request.schema.json`. Cross-field unit, weight, reference and finite-number checks also run in Python. JSON Schemas alone cannot express every scientific invariant.

| Method | Path | Request | Success | Failure |
|---|---|---|---|---|
| GET | `/v1/health` | None | 200 readiness | Process unavailable |
| GET | `/v1/example?case=mars` | None | 200 synthetic draft; case is earth, moon or mars; selection is site or zone. Earth draft requires user site and target choices | 500 missing fixture |
| POST | `/v1/missions` | Full MissionRequest and Idempotency-Key header | 202 ID/status URL | 409 key conflict, 413 size, 415 media, 422 validation, 429 capacity |
| GET | `/v1/missions/{id}` | None | 200 state, attempt and input hash | 404 unknown |
| GET | `/v1/missions/{id}/events?after=N` | Last sequence cursor | 200 up to 200 ordered events | 400 invalid cursor, 404 unknown |
| GET | `/v1/missions/{id}/result` | None | 200 committed result | 409 pending/failed, 404 unknown |
| GET | `/v1/missions/{id}/report` | None | 200 escaped HTML report | 409 pending/failed, 404 unknown |

The client obtains another portfolio by appending the previous selected site set to `mission.exclude_portfolios` and submitting a new mission. The sample recomputes the small deterministic calculation. Production caches upstream features by snapshot and invalidates only the optimization descendants.

## Planned production endpoints

Authenticated APIs additionally provide upload initiation/finalization, dataset mappings and previews, artifact metadata/download, source refresh requests, mission cancellation, alternatives by prior mission ID, server-sent events, and operator health. These routes are specifications for implementation. Their authorization scope follows the owner/tenant of the parent mission or dataset.

## Semantic invariants

- Every request and result has a schema version. Version 1.0 is the sample contract.
- A result's `input_sha256` hashes canonical original input. `cleaned_sha256` hashes the normalized validated version.
- Weights are finite and nonnegative, with at least one positive value. The engine normalizes their sum.
- Missing measurements use null plus a reason where available. A declared sentinel can be converted with a recorded rule.
- Observation units equal the feature's canonical unit. Conversion belongs to a product-aware transform before scoring.
- Costs share a scenario unit and base date in production. The fixture uses synthetic budget units.
- Earth coordinate arrays use longitude then latitude. Planetary records use explicit body-specific CRS metadata.
- Agent actions reference known task IDs and finding IDs. The scheduler validates the action and repair budget.
- Critical findings block publication. Reports carry unresolved lower-severity findings and limits.

## Contract files

`mission_request.schema.json` and `mission_result.schema.json` describe runnable inputs/outputs. `production.schema.json` defines reusable AssetManifest, FeatureObservation, QualityVerdict, AgentFinding, ReleaseDecision and ProgressEvent records. `production.sql` supplies a starting Postgres schema with immutable artifact identities and fenced task fields. It requires migration and tenant authorization integration for deployment.

## Target-specific result fields

`comparison_pairs` contains `["Earth","Moon"]`, `["Earth","Mars"]`, or both. `target_profiles` preserves resolved reference locations and evidence. Single-reference contribution keys use `Body/feature`; multi-reference keys use JSON tuple strings; each contribution identifies `source_id`, `target_source_id` and `target_value`. `sites` and all portfolio lists describe Earth candidates only. `excluded_outside_scope` includes non-Earth candidate records and records outside an explicit Earth anchor. An empty eligible set returns `no_feasible_portfolio` with an explanation. Input target profiles are supplied evidence in this sample, not a live lookup. See the four JSON examples in implementation/examples.

## Zone and portfolio additions (algorithm 0.4.0)

A selection can set `kind: "zone"` to include multiple locations; omitted kind remains `site`. Earth candidates must lie in the selected Earth footprint. Each selected planetary zone can contain multiple reference profiles with distinct location IDs and bounded reference boxes. Exactly selected single-site profiles retain the prior matching rule. Total reference profiles are capped at 12 in the sample.

`mission.portfolio_mode` is `standalone`, `combined` or `both` (default). Combined requires `max_sites >= 2`. Results include `portfolio_mode`, typed portfolio items, and separate `standalone_portfolios` / `combined_portfolios` arrays. The overall and category lists are each capped at ten. Contribution records expose `target_body`, `target_location_id` and `feature_id`; keys use JSON tuple strings for multi-location target bodies. `GET /v1/example?case=earth&selection=zone` supplies a draft requiring explicit target choices.
