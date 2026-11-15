# C0 post-merge recovery — 2026-11-15

This checkpoint supersedes the historical report retained below. **HOLD; not
ready for VM deployment.** Main remains `774c709`; C1–C5 are merged. Existing
uncommitted C0 work is preserved. No new commit was possible.

## Environment and preservation

Workspace writes succeeded. A single disposable `.git` write probe and localhost
bind/listen probe each failed with EPERM. DNS for www.nasa.gov failed with
getaddrinfo errno 8; outbound HTTPS could not be established. Restricted operations
were not retried. No authenticated request or paid AI inference was used.
All five lane worktrees and stash `615c329` remain intact; no reset or cleanup.
Previous verification logs were copied into a timestamped sibling archive before
running verification. Current blocked logs explicitly distinguish historical runs.

## Exact failures and fixes

1. **c0:** the published pair had already switched to official SRTM, but those
   bytes existed only under `.runtime/official-data`. The worker looked under
   `.runtime/data` and raised `Source bytes missing or wrong size`, publicly
   redacted as INVALID_MISSION. Installed the hash-verified official asset in the
   canonical cache without overwriting existing bytes. All five published assets
   now verify. The acquisition script now installs verified official bytes into
   the configured worker cache before rebuilding the published pair.
2. **c5_http_restart_e2e:** catalog ignored `limit`; `limit=0` returned 200.
   The handler now requires an integer from 1 through 100 and applies the limit.
   Regression coverage checks 0, 101, -5, x and a one-row result. The handler tests
   pass; the HTTP/restart suite itself remains blocked by socket permissions.
3. **c5_measured_provenance:** failed C0 generation left stale mirror evidence.
   Successful worker execution regenerated current NASA-linked evidence. C5 also
   compared native HGT slope/relief with C1's block-mean features, lacked roughness
   and MOLA decoders, and compared uppercase PDS product IDs case-sensitively to
   lowercase URLs. C5 now independently decodes raw HGT and label-defined MOLA
   subsets, verifies subset offsets, uses WGS84/Mars geodesy, derives integer
   blocks from the declared analysis scale, and computes Horn slope, 3x3 population
   SD and aggregate relief. MOLA count bins independently check observation support.
   Product-ID matching is case-insensitive. Existing slope/relief tolerances are
   unchanged; new roughness tolerance is max(0.01 m, 0.1%). No C1/C2 feature values
   or production scientific algorithms were changed.
4. Verification now honors TWINSITE_SOURCE_DATA_DIR for C5, archives old logs,
   and refuses to check stale evidence if C0 failed. C5 exits nonzero for BLOCKED
   recomputation as well as FAIL. The UI no longer describes the current dataset
   as an unverified ESA mirror.

## Scientific evidence

The saved acquisition report records AUTHENTICATED_PRODUCT_DOWNLOAD and
`official_verified: true`. Official ZIP SHA-256:
`2493d4ce40b0405ee1926365533faf3b04d8c84a765fc5add763e1c0ebd13c82`.
Both decoded HGT rasters hash to
`68783aff82b31ac94b828741cc2cf467d541de3433449b36183435a272034ac6`;
zero differing samples. ZIP hashes changed because archive bytes differ.
The source snapshot changed from
`8e99d2afad638414febd3c9a8f4721ae2421ab48a2982695ad291702baf5b835` to
`c3715a06a69fc4a0f1854b69962f62890cc96c32853943785803033773e3c356`.
Earth evidence/provenance IDs changed; all six numerical values are unchanged.

| Feature | Earth published / independent (rounded) | Mars published / independent (rounded) |
| --- | --- | --- |
| Slope, degrees | 0.5838 / 0.5838 | 1.5093 / 1.5093 |
| Roughness, metres | 17.9224 / 17.9224 | 42.8370 / 42.8370 |
| Relief, metres | 313.811 / 313.811 | 925.562 / 925.562 |

Common analysis scale: 1852.3 m; SRTM 60x69 posts, MOLA 4x4 cells.
Coverage: Earth 1.0; Mars 0.740741. Interpolated MOLA cells remain flagged.
C5 reports 19 PASS, zero FAIL, zero BLOCKED on current measured evidence.
This is offline checksum/lineage/arithmetic verification, not a fresh independent
NASA re-download. The earlier C5 report independently verified MOLA topography
and its label but left count-asset refetch blocked. Do not infer complete new
origin verification from this offline run.

The real C2 engine and synthetic safeguards remain intact. Release is still BLOCK:
C5_INDEPENDENT_REVIEW_REQUIRED, NO_QUALIFIED_CANDIDATE, and
UNREGISTERED_FEATURE:dry_fraction. Missing measurements and unknown access/cost/
duration remain explicit. No field-ready portfolio is claimed.

## Verification

`make verify`: **13 PASS, 0 FAIL, 3 BLOCKED**. Make exits 2 because the verification
runner exits 1 for incomplete checks. No failed test was disabled.

| Suite | Result |
| --- | --- |
| Schemas / types | PASS / PASS |
| Integration | 20 tests PASS |
| Science | 33 tests PASS |
| Data | 26 tests PASS |
| C0 | 10 tests PASS |
| QA negative / analytical controls | 18 tests PASS |
| Store / worker | 10 tests PASS |
| Frontend typecheck / build / tests | PASS / PASS / 19 tests PASS |
| Secret scan | PASS, zero findings |
| C5 measured provenance | PASS, 19 checks |
| Backend HTTP | BLOCKED: local socket permissions |
| C5 HTTP/restart end-to-end | BLOCKED: local socket permissions |
| Browser smoke | BLOCKED: no local server permitted |

Total 136 unit/in-process/frontend tests pass. New analytical controls verify
subscale cancellation, plane slope/roughness/relief, void masking, shot support,
PDS decoding, and rejection of wrong subset ranges and vertical datum.
`git diff --check` passed. Latest summary: `.runtime/c0/verification/summary.json`.

## Files changed during recovery

- backend/twinsite/api/server.py
- backend/tests/integration/test_c0.py
- tests/acceptance/provenance_check.py
- tests/acceptance/terrain_reference.py (new)
- tests/acceptance/test_terrain_reference.py (new)
- scripts/integration/verify_official_srtm.py
- ops/verify_current.py
- frontend/src/pages/Workspace.tsx
- docs/release/C0_API_EXTENSIONS.md
- docs/release/C0_INTEGRATION_REPORT.md
- ops/vm/README.md

Other pre-existing C0 changes remain uncommitted and were reviewed without being
reset. Runtime evidence/cache changes remain ignored. No credentials or runtime
artifacts were staged; Git was read-only, so no staging or commit was attempted.

## Acceptance and deployment

- **G1: HOLD.** In-process paths pass; current live HTTP/restart/browser acceptance
  cannot be completed in this session.
- **G2: HOLD.** Independent offline evidence checks pass, but independent origin
  verification/release review is incomplete. Scientific release remains blocked.
- **G3: PARTIAL / HOLD.** Explorer limit bug fixed; live browser verification and
  provisional response review remain pending; alternatives still return 501.
- **VM deployment: NOT READY.** Commit, unrestricted live checks, independent
  review and an actual VM configuration/deployment check remain outstanding.

The prior exposed Earthdata token is compromised. It was neither reproduced nor
used. Cached analysis needs no token; any future authenticated download requires
a replacement provisioned server-side. No secrets belong in a repository, image,
frontend, log or report.

---

# Historical pre-merge checkpoint (superseded)

# C0 final integration checkpoint — 2026-11-15

Status: working offline integration; scientific release HOLD. No deployment.

## Commits and workspace

Actual heads verified: C1 c942bb7, C2 5330b4b, C3 0383322, C4 af0c0e5,
C5 8a4ac74. All contributions are assembled in the main workspace, plus C0
integration fixes. **No commits merged**: .git is read-only in this session;
main remains 9b8570c. All five lane branches and worktrees are preserved.
Lane-specific backend/data/science tests and handoff status notes are accepted
ownership exceptions. No frozen contract/schema/generated type was changed.

## Credentials and official NASA evidence

The supplied credential was provisioned using non-echoing interactive input,
not a shell argument. `.env` is Git-ignored and verified mode 0600. Source,
test fixtures, reports and browser assets do not contain the credential.
Acquisition prefers EARTHDATA_TOKEN from process environment, then an explicitly
protected environment file; no macOS credential Keychain dependency.

An official acquisition was attempted using C1's SRTM adapter. Both
cmr.earthdata.nasa.gov and data.lpdaac.earthdatacloud.nasa.gov failed DNS lookup
(gaierror errno 8), producing URLError and no verified HTTP response.
**NASA acceptance/rejection of the token is unknown.** No official SRTM product
was downloaded; its size/hash/content comparison is therefore BLOCKED.

The previous mirror remains explicit: ESA STEP, 9,369,604 bytes,
SHA-256 a9c6dd5d6e41a8d8e8f4f51d905acdfa99a72384c66d5617799abfd5a333947f.
All five existing raw assets were verified against their recorded sizes/hashes.
Matching filenames are not treated as proof of equivalence. Original quality
flags and source lineage remain intact.

Acquisition fixes: authenticated requests bypass mirror caches; no silent mirror
fallback with a credential; separate staging paths for official/mirror bytes;
TLS verification remains on; cross-origin redirects strip authorization;
non-HTTPS redirects fail; product member identity and decoded size are checked.
`scripts/integration/verify_official_srtm.py` performs official acquisition,
full HGT byte/hash/sample comparison, preserves old provenance and rebuilds the
published pair on success. It must still be exercised with network access.

## Scientific engine and measured workflow

C3 now calls C2 analyze_mission, identifying twinsite-science/0.1.0. Production
ARES fallback is removed. Synthetic fixtures retain labels and release BLOCK.
Existing arithmetic compatibility tests compare all frozen numeric fields;
C2's explicit algorithm version and added limitations are asserted separately.

POST /v1/missions/measured resolves dataset_id zagora-gale-v1 server-side.
The resolved request fingerprints the published dataset. Worker validation checks
source sizes/hashes, lineage and exact request identity before strict C2 analysis.
Client-provided measurements and relabelled synthetic inputs are rejected.
Units/spatial support are checked; missing dry_fraction is not invented.
Access, costs and duration remain unknown. All six observations/five assets
remain in the evidence sidecar. C5 independent review is mandatory; release BLOCK
is unconditional until a separately reviewed release implementation exists.

The actual handler -> durable queue -> C2 worker -> persisted result/evidence/
HTML report path completes and survives Store/App reopening, with idempotent
replay and P00–P90 events. It is **not a real HTTP end-to-end test**: sockets are
forbidden here. Result status: no_feasible_portfolio; job status:
completed_with_limits. Unknown access and unregistered/missing dry_fraction are
not silently waived. No scientifically released or field-ready portfolio exists.

## Frontend / Data Explorer

Added a dedicated measured Zagora–Gale button using server resolution. Results,
evidence, comparisons and reports use the existing live APIs. Read-only catalog,
records, metadata and compare endpoints expose the two published sites. Tables
preserve evidence IDs, units, scale, coverage and flags. Side-by-side comparison
includes per-feature bars and numerical differences when units/scales match.
Raw views show asset metadata, not raster pixels. Cleaned/derived views expose
published terrain summaries, not full cleaned raster arrays.

Still unsupported: arbitrary-location acquisition, alternative-portfolio reruns
(501), uploads (501), mission-list endpoint. Existing offline demo views remain
prominently labelled; they are not evidence of live operation. See C0_API_EXTENSIONS.md.

## Verification against the current checkout

`make verify` now verifies current C0 files, not a stale composite of lane heads.

| Check | Result |
| --- | --- |
| Frozen schemas / examples | PASS: 18 schemas, 17 shared examples |
| Generated types / schema freeze tests | PASS |
| C0 existing integration tests | 20 PASS |
| C2 numerical / negative-control tests | 33 PASS |
| C1 data tests | 26 PASS |
| C3 store/worker tests | 10 PASS |
| C0 new measured/security/explorer integration | 9 PASS |
| C5 provenance checker negative controls | 14 PASS |
| Frontend unit/route tests | 19 PASS |
| Frontend typecheck and production build | PASS; existing large MapLibre chunk warning |
| Secret scan of distributable source + built browser assets | PASS: zero findings |
| HTTP/backend API, C5 HTTP/restart/SIGKILL e2e, browser smoke | BLOCKED: socket bind PermissionError |
| C5 checker on actual measured evidence | 13 checks PASS, 9 FAIL, 4 BLOCKED |
| Official NASA acquisition | BLOCKED: DNS/connection failure, no authenticated response |

Total: **131 unit/in-process tests PASS**. The six HTTP backend tests were
attempted earlier and errored on socket binding; final verification reports
these as BLOCKED. Two initial worker assertions were updated for the C2 interface
(version/limitations and fail-closed error code); numerical expectations and
scientific gates were not relaxed. C5's measured checker is unchanged.

C5 measured findings remain unresolved:
- 4 NON_NASA_HOST failures (one Earth asset, three Earth observations).
- 2 INDEPENDENT_RECOMPUTE_DISAGREES failures: native-grid slope/relief checks
  compared with C1's 1852.3 m aggregated features. A same-scale independent
  recomputation is needed, not wider tolerances or changed C1 values.
- 3 GRANULE_ID_NOT_TRACEABLE failures for uppercase MOLA granule IDs vs lowercase
  URL/object keys; requires product-label/identity review.
- 1 missing independent roughness statistic and 3 unsupported MOLA recomputations.
No failures have been converted into scientific acceptance.

## Gate acceptance

- G0: contracts/types/local integration checks pass; Git integration incomplete.
- G1: NOT FULLY ACCEPTED. In-process measured and synthetic worker paths pass;
  latest-code live HTTP/browser/restart verification remains blocked.
- G2: BLOCKED. Official Earth source comparison and independent C5 scientific
  review are not complete. Measured does not mean scientifically validated.
- G3: PARTIAL / NOT ACCEPTED. Explorer tables/comparison implemented and built;
  live browser verification and full raster browsing remain incomplete.

## VM readiness

Prepared ops/vm systemd units, loopback nginx serving/proxy config, and runbook.
Secrets are separately provisioned, persistent SQLite/artifacts/source caches are
outside source, services restart on failure, leases provide worker recovery,
logging avoids request payloads/headers/query strings, and paid AI is absent.
No approved host or deployment credentials were supplied; nothing was deployed.
Linux configuration has not been runtime-tested.

## Immediate continuation

1. In a terminal/session allowed to write Git, run:
   `.venv/bin/python scripts/integration/complete_c0_merges.py` from this workspace.
   It verifies reviewed heads, creates a source backup and preserved stash,
   merges all five exact commits, then restores C0 edits. It does not reset,
   clean, discard worktrees, stage secrets or commit the final C0 edits.
2. With network access, run
   `.venv/bin/python scripts/integration/verify_official_srtm.py`.
   On successful rebuild, use its official source-cache path, update the
   source-status UI text, and rerun all checks against the new dataset.
3. Run `make verify` with socket permissions, then browser smoke. C5 must reconcile
   same-scale independent SRTM/MOLA calculations and approve evidence separately.
4. Review/commit C0 source changes, then approve a VM host before deployment.

Detailed local results: .runtime/c0/verification/summary.json and suite logs;
.runtime/c0/official-srtm-verification.json; measured request/result/evidence JSON.
