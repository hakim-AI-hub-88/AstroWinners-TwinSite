# TwinSite shared contract — v1, frozen at G0

Owner: C0 (TWIN-INT). API prefix: `/v1`. Wire `schema_version: "1.0"` is deliberately retained from ARES; the path version and payload version are distinct. JSON Schema Draft 2020-12 is authoritative. Generated `types.ts` supplies structural TypeScript types; `contracts.validation.validate` supplies Python validation. Bounds and cross-field invariants must also be validated at runtime.

## Compatibility and source authority

`v1/mission_request.schema.json`, `mission_result.schema.json`, and `production.schema.json` are byte-for-byte copies of the original ARES ZIP. Original SQL and HTTP documentation are retained in `legacy/`; SQL is a reference, not a deployed migration. Current TwinSite handoff contracts take precedence for optional AI consent and quality verdicts. Historical `production.QualityVerdict` is NOT the current `quality_verdict.schema.json`; do not interchange them.

The new HTTP job and event schemas are explicitly separate from historical ARES transport. No lane implementation existed at this freeze. ARES is only the local reference profile; it is not conformant to TwinSite's job/event/evidence profile. No reference code is modified. Owners must implement their adapters; C0 needs owner consent before changing lane code.

All consumers load fixtures from `contracts/examples/index.json`. Every numerical request/result example is SYNTHETIC. Example hashes demonstrate reproducibility, never NASA validation. `references/SNAPSHOT.json` pins all three input ZIPs. Do not use `ARES 2/` in place of the pinned archive without review; that directory may represent a different revision.

## G1 HTTP contract

| Method and path | Success and body | Required failures |
| --- | --- | --- |
| `GET /v1/health` | 200; `{status:"ready", schema_version:"1.0", ai_enabled:false, uploads_enabled:false}`; 503 if required local storage unavailable | No credential values or provider diagnostics |
| `POST /v1/missions` | 202 `mission_accepted`; request `mission_request`; required `Idempotency-Key` of 1–128 chars | 400 missing key; 409 same key/different input; 413 >1,000,000 bytes; 415 wrong media; 422 validation; 429 queue full |
| `GET /v1/missions/{run_id}` | 200 `mission_status` | 404 unknown |
| `GET /v1/missions/{run_id}/events?after=N` | 200 `events` array, at most 200, ascending `sequence > N`; empty array at end | 400 non-integer/negative cursor; 404 unknown |
| `GET /v1/missions/{run_id}/result` | 200 unchanged `mission_result` | 409 not committed/failed; 404 unknown |
| `GET /v1/missions/{run_id}/evidence` | 200 `release_evidence` sidecar committed atomically with result | 409 not committed; 404 unknown |
| `GET /v1/missions/{run_id}/report` | 200 escaped HTML, `text/html; charset=utf-8`; visibly synthetic or insufficient when applicable | 409 not committed; 404 unknown |

JSON responses use UTF-8 and no NaN/Infinity; failure bodies use `error.schema.json`. HTML report remains HTML for backward compatibility; PDF is a later separately advertised artifact. Route IDs are server-generated opaque `run_id`; scientific `result.mission_id` is the original request's scenario ID. `id == run_id` in acceptance/status responses is the compatibility alias; they must never disagree. Identical idempotency retries return the same acceptance payload, including `status: queued`; poll the status URL for actual current state.

Canonical original input hash: SHA-256 of UTF-8 `json.dumps(input, sort_keys=True, separators=(",", ":"), allow_nan=False)`. Do not hash frontend re-serialized rounded values. `cleaned_sha256` retains ARES semantics. Jobs are created only by explicit user POST; GET and page load never start a run. Initial limits: one active mission, bounded queue of 20, maximum three worker attempts, fenced/atomic commit. Workers expose actual committed events, not estimated AI percentages.

## Lifecycle and reference mapping

Public mission status: `queued | acquiring | decoding | cleaning | validating | characterizing | analyzing | optimizing | reviewing | publishing | completed | completed_with_limits | failed | cancelled`.

Events retain the ARES production `ProgressEvent` fields with stable phase IDs `P00, P10, P20, P30, P40, P50, P60, P70, P80, P90`. Their task `state` enum is `queued | running | retry_wait | succeeded | failed | cancelled | quarantined`; it is NOT the mission status enum. `mission_id` in an event means server run ID. Sequence is strictly increasing within each run, positive in emitted events; no fake progress when totals are unknown. Preserve `attempt_id`, `task_id`, `trace_id` and artifact links. Public summaries must be redacted and must not contain keys, private paths, signed URLs or raw uploaded text.

| Historical reference | TwinSite adapter requirement |
| --- | --- |
| acceptance `{id,status_url}` | Add equal `run_id`, `schema_version`, queued acceptance status |
| job `state: running` | Use actual phase to determine public mission status |
| job `state: succeeded` | `completed` or `completed_with_limits`, determined by release evidence |
| job `input_hash` | `input_sha256` |
| events `at`, legacy phase strings, `completed` | Real timestamp, stable phase ID, measured units and attempt/task linkage; do not invent missing history |
| numerical result | Preserve exact schema; add separate evidence route |

The historical endpoint accepts a caller's `data_status` and lacks production release enforcement. NEVER expose it as a scientific or public TwinSite service. The integration smoke submits only the frozen synthetic fixture. `make reference-dev` is a local historical diagnostic, not a production fallback.

## Evidence sidecar and publication gate

Keep result compatibility by storing new fields in `release_evidence`, not by adding undeclared fields to the closed legacy result object. `standalone_portfolios`, `combined_portfolios` and `comparison_pairs` remain in the result. `rejected_candidates`, `strict_gate_status`, `evidence_coverage`, `weights_version`, `source_snapshot_id`, `assumptions` and `unknowns` are in the sidecar. The UI must consume both before presenting any measured-science claim. Missing sidecar => evidence unavailable, never implicit approval.

Each observation follows `evidence_observation.schema.json`: feature/site/body, explicit geometry and CRS, value or null, unit, source product/granule/URL/SHA-256, source assets, observation period, spatial resolution and analysis scale, quality flags and verdict, valid coverage, uncertainty, processing version, provenance ID, evidence kind and data status. No self-rated confidence. Null needs a reason. Assumptions/model estimates cannot satisfy required measured features. Input `data_status: measured` is untrusted: C3 must resolve measurements from approved C1 assets, not accept client assertions as science.

`source_snapshot_sha256` hashes the canonical JSON array of `{asset_id,sha256}` sorted by asset ID. `source_snapshot_id` names the immutable snapshot; changing weights does not change it. Asset `object_key` is private and relative to a controlled artifact root; public APIs must expose only approved public records and must never publish private user upload manifests through this contract. No source URL may contain a credential, capability or signed query.

In measured runs, request observation `source_id` and result contribution `source_id`/`target_source_id` resolve to `evidence_id`, not merely a generic provider name. Every contribution must match the observation's value, unit, feature, body and location. Required target observations and every eligible site's required features must be attested independently from request requirements. Missing required measurement, invalid units/CRS, failed owner QA, orphan evidence, changed source bytes or critical review issue => BLOCK. Lower coverage is not zero; a blocked run does not publish qualified recommendations. A synthetic fixture always has `release_action: BLOCK` for scientific release, even if its diagnostic job completes.

`contracts.validation.measured_release_issues` verifies integration lineage and checksums. C1/C2 remain responsible for product decoding, masks, scientific comparability, physical scale, units, uncertainty and scoring. A passing integration check is necessary but is not sufficient proof of scientific validity. C5 must provide negative controls and independent reviewer evidence before G2 is marked complete.

## Reserved later endpoints (not implemented or G1 claims)

| Route | Boundary |
| --- | --- |
| `POST /v1/missions/{run_id}/portfolios/alternatives` | `alternatives_request` → new `mission_accepted`; same cached snapshot, explicit exclusion sets; no repeated NASA download |
| `GET /v1/data/catalog` | Public curated datasets only, cursor pagination, limit 1–100 |
| `GET /v1/data/{dataset_id}/records` | `stage=raw|cleaned|derived`, cursor and limit 1–100; allowlisted columns only |
| `GET /v1/data/{dataset_id}/metadata` | Source/version/license/time/QA/geometry/transform lineage |
| `POST /v1/data/compare` | `data_compare_request`; server-controlled comparison of approved records; no SQL or expression strings |
| `POST /v1/uploads` | Disabled until C3/C5 verify per-mission capability isolation, retention/deletion and consent |

G3 catalog/records/metadata/compare response schemas require C0 review before implementation; paths and safety boundaries are reserved, not complete endpoints. Unimplemented features return explicit 501/disabled UI rather than simulated data. Queries never reach arbitrary SQL. Uploads and AI are disabled by default; no login/settings UI. AI cannot change measurements, weights, eligibility or portfolios.

## Freeze and change procedure

Run `make schemas`, `make types`, `make test` and API smoke against the owner implementation. `FREEZE.json` records hashes for every schema, example, types file and this document. C1–C5 report changes with DONE / FILES / TESTS / BLOCKERS / NEXT GATE. Only C0 reviews/merges into main. Do not silently refresh hashes to bless drift; contract changes require affected owners' review. Breaking changes need a new wire schema version and explicit adapter/migration, not a reinterpretation of v1.
