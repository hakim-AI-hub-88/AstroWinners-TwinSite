# C0 integration API additions

Frozen contracts/v1 schemas and generated types are unchanged. This documents
additive API orchestration and provisional explorer response shapes.

POST /v1/missions/measured requires Idempotency-Key and exactly:
`{"schema_version":"1.0","dataset_id":"zagora-gale-v1"}`.
It resolves the published C1 pair, builds a schema-valid mission_request, and
hashes the resolved request. The mission id fingerprints the full published pair,
so a changed dataset fails an already queued job rather than silently changing
its scientific input. The worker rechecks the current resolved request, raw sizes,
SHA-256 hashes, lineage, and C2 units/spatial support. Old queued snapshots are not
retained: rerun after a dataset update. Result/evidence/report remain immutable.
Client-provided measured requests on /v1/missions return 422. Arbitrary locations
have no integrated acquisition workflow. The dedicated frontend preset uses the
published pair; general custom region requests remain unsupported.

The preset retains dry_fraction as missing. Access, cost, days remain unknown;
no feasible portfolio is expected under the conservative access gate. Weights
and tolerances are explicit scenario assumptions. C2 analysis is strict. C5
offline recomputation now agrees for all six features; independent release review
is still required, so scientific release is always BLOCK.

Explorer response shapes match frontend/src/lib/types.ts:
- catalog: {items: DatasetSummary[]}; two published sites only; integer limit 1–100
  (default 100), invalid values return 422.
- records: {stage, columns, rows, total, sampled, next_cursor, note}; max 100 rows.
  Raw rows are asset metadata, not raster pixels. Cleaned and derived views expose
  the same published terrain feature summaries, with their quality flags.
- metadata: DatasetMetadata with source URLs, evidence ids, transformations, product
  version, provider data-policy link, `extent` (approximate metric AOI size, spherical
  mean radius, display only), `distributions` (per-feature n/min/p10/median/mean/p90/max/sd
  across analysis blocks) and native/analysis resolution.
- grid (`GET /v1/data/{dataset_id}/grid`): the cleaned native elevation grid, read from
  `TWINSITE_SOURCE_DATA_DIR` by its pinned `cleaned_object_key` and verified against
  `cleaned_sha256` on every request (missing → 404, checksum mismatch → 409
  SOURCE_INTEGRITY_FAILED). Grids over 72 cells per side are block-averaged *for display
  only* (k×k mean, null if any sample is null); the response states the factor, trimmed edge
  rows and that this is not the 1852.3 m analysis grid. No demo fallback exists for grids.
- compare: frozen data_compare_request input; {columns, rows:[{key,left,right}]}.
  Feature IDs align the two sites. Units/scales are displayed; UI graphs require
  equal units and analysis scale. No arbitrary SQL, expressions or filesystem paths.

Portfolios are available in mission results. Alternative-portfolio reruns and
private uploads still return 501. No list-missions endpoint exists. None of these
limitations authorizes synthetic substitution without the existing DEMO banner.
