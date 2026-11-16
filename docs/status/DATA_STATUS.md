# C1 TWIN-DATA status: lane/data

Checkpoint: 2026-11-15 ~04:10 UTC. Owner: C1 (NASA data acquisition and cleaning).

**G2 data deliverable: DELIVERED, pending review.** There is one real Earth/Mars feature pair, both at the same physical analysis scale:

- **Earth:** SRTMGL1 v003 over the Draa valley near Zagora, Morocco.
- **Mars:** MGS MOLA MEGDR over Gale crater (Aeolis Palus).

The scoring engine (C2) can use the pair without AI. Independent review (C5) and the C0 merge have not happened. The Earth bytes come from a public mirror, because no Earthdata credential is available (see BLOCKERS).

## Published file for C2 / C0

`backend/twinsite/processing/published/g2_feature_pair.json`

- 34 KB; regenerating it is deterministic. Two offline runs gave the same file SHA-256 (current file SHA-256 `44d13f4f9747ca04…`).
- `observations[]` follows `contracts/v1/evidence_observation.schema.json`.
- `assets[]` follows `asset_manifest.schema.json`.
- `sites[].quality_verdict` follows `quality_verdict.schema.json`.
- All three validate under Draft 2020-12 with `contracts.validation.validate`, which the test suite runs.
- `comparison_pairs[]` maps each `feature_id` to its Earth and Mars `evidence_id`.
- `source_snapshot_sha256` follows the contract rule: canonical JSON of `{asset_id, sha256}` sorted by `asset_id`.
- Values: `data_status: "measured"`, `evidence_kind: "derived_measurement"`. No synthetic values.

| site_id | feature_id | value | unit | p10–p90 (spatial) | valid_coverage | qa | evidence_id |
| --- | --- | --- | --- | --- | --- | --- | --- |
| earth-zagora-draa | slope_deg | 0.5838 | degree | 0.1461–1.4995 | 1.000 | ACCEPT | ev-earth-zagora-draa-slope_deg-3f2bb6430161e48f |
| earth-zagora-draa | roughness_m | 17.9224 | m | 4.2433–43.5138 | 1.000 | ACCEPT | ev-earth-zagora-draa-roughness_m-b5fcf29c053122a0 |
| earth-zagora-draa | local_relief_m | 313.811 | m | n/a | 1.000 | ACCEPT | ev-earth-zagora-draa-local_relief_m-437aea82fe8acc62 |
| mars-gale-aeolis | slope_deg | 1.5093 | degree | 0.2656–4.278 | 0.741 | ACCEPT | ev-mars-gale-aeolis-slope_deg-164109cd32a9b22a |
| mars-gale-aeolis | roughness_m | 42.837 | m | 8.5413–114.6707 | 0.741 | ACCEPT | ev-mars-gale-aeolis-roughness_m-14c3e59c911b8558 |
| mars-gale-aeolis | local_relief_m | 925.562 | m | n/a | 0.741 | ACCEPT | ev-mars-gale-aeolis-local_relief_m-f76821d077242461 |

- Analysis scale: **1852.3 m** for both bodies. That is 4×4 MOLA cells, and 60×69 SRTM posts block-averaged.
- `source_snapshot_id`: `c1-g2-8e99d2afad638414`
- `source_snapshot_sha256`: `8e99d2afad638414febd3c9a8f4721ae2421ab48a2982695ad291702baf5b835`
- Feature IDs and units match the mission fixture vocabulary: `slope_deg` in degree, `roughness_m` in m.
- `dry_fraction` is **not produced**. No integrated source supports it, and it is never fabricated.

### Record shape (one observation, abridged)

```json
{"schema_version":"1.0","evidence_id":"ev-mars-gale-aeolis-slope_deg-164109cd32a9b22a",
 "feature_id":"slope_deg","site_id":"mars-gale-aeolis","body":"Mars",
 "geometry":{"type":"bbox","coordinates":[137.25,-4.75,137.55,-4.45],"crs":"IAU_2000:49900"},
 "value":1.5093,"unit":"degree","source_product":"MGS-M-MOLA-5-MEGDR-L3-V1.0",
 "source_granule_id":"MEGT00N090HB.IMG",
 "source_url":"https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/megt00n090hb.img",
 "source_checksum":"2bc27bff…2c62","source_asset_ids":["…4 MOLA assets…"],
 "observation_period":{"start":"1997-09-15T19:10:00Z","end":"2001-06-30T11:10:40Z"},
 "spatial_resolution_m":463.058,"analysis_scale_m":1852.3,
 "quality_flags":["MOLA_INTERPOLATED_CELLS_RETAINED","MOLA_SHOT_SUPPORTED_FRACTION=0.257","OBSERVATION_SUPPORTED_BLOCK_FRACTION=0.741"],
 "valid_coverage_fraction":0.740741,
 "uncertainty":{"kind":"interval","low":0.2656,"high":4.278,"standard_deviation":null,"basis":"10th-90th percentile … (spatial variability, not instrument error) …"},
 "processing_version":"twinsite-data/1.0.0; terrain/1.0.0 (block-mean, Horn-1981 slope, 3x3 SD roughness)",
 "provenance_id":"prov-mars-gale-aeolis-ed154434f5666ddf","evidence_kind":"derived_measurement",
 "data_status":"measured","missing_reason":null,"qa_status":"ACCEPT"}
```

Full provenance for each site is in `sites[].provenance`. It includes:

- adapter description
- CMR/PDS catalog evidence
- transcript keys
- preserved acquisition errors
- transformations
- validation metrics and issues
- datums
- the radius model
- feature definitions and statistics
- an explicit sample calculation

## Sources: acquisition and verification

### Earth: SRTMGL1 v003, tile N30W006

**Discovery (CMR, public):**
- Query: `GET https://cmr.earthdata.nasa.gov/search/granules.umm_json?short_name=SRTMGL1&version=003&readable_granule_name=N30W006.SRTMGL1.hgt&page_size=5`
- Result: 1 hit.
- Granule `G2821052091-LPCLOUD`, collection `C2763266360-LPCLOUD`.
- DOI 10.5067/MEaSUREs/SRTM/SRTMGL1.003.
- Temporal extent 2000-02-11T00:00:00Z to 2000-02-21T23:59:59Z.
- Size per CMR: 10.1048 MB.

**Authoritative download:**
- URL: `https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/N30W006.SRTMGL1.hgt/N30W006.SRTMGL1.hgt.zip`
- Result: HTTP **302 → `https://urs.earthdata.nasa.gov/oauth/authorize`**. `EARTHDATA_TOKEN` is absent, recorded as `CREDENTIAL_MISSING`.

**Documented alternate (public mirror):**
- URL: `https://step.esa.int/auxdata/dem/SRTMGL1/N30W006.SRTMGL1.hgt.zip` (ESA STEP SNAP auxdata redistribution, same file names).
- Transcript of attempts:
  1. Connection reset at 3,276,800 bytes after 315 s.
  2. Read timeout.
  3. Read timeout.
  4. DNS failure `[Errno 8] nodename nor servname provided`.
  5. DNS failure, same error.
  6. HTTP 206 resume completed.
- Final size: 9,369,604 bytes.
- SHA-256: `a9c6dd5d6e41a8d8e8f4f51d905acdfa99a72384c66d5617799abfd5a333947f`, asset `srtmgl1-n30w006-a9c6dd5d6e41`.
- The resumed concatenation is verified by the zip member CRC-32 at decode.

**Format:** zip containing a 3601×3601 grid of big-endian int16 in metres, void = −32768. Point-registered 1″ posts. WGS84 horizontal (EPSG:4326), EGM96 geoid heights.

**AOI:** −5.95 to −5.65 E, 30.20 to 30.50 N. That is 1081×1081 posts, 1,168,561 in total, with **0 voids**. Elevation ranges from 667 to 1088 m.

**QA:** `ACCEPT`, with these issues:
- `MIRROR_NOT_VERIFIED_AGAINST_LPDAAC` (warning)
- `SURFACE_IS_RADAR_PHASE_CENTRE` (info): C-band heights include canopy and structures.

**Native spacing at 30.35° N:** 26.7 m (E-W) × 30.8 m (N-S). Distances use WGS84 ellipsoid local radii.

**Sample calculation**, centre block (lat 30.3418, lon −5.8064), 3×3 block-mean window in metres:

```
[[727.552, 727.951, 726.200],
 [724.209, 723.294, 746.827],
 [749.855, 776.642, 769.216]]
```

- dx = 1842.95 m, dy = 1847.64 m
- dz/dx = 63.245 / (8·1842.95) = 0.004290
- dz/dy = −162.701 / (8·1847.64) = −0.011007
- slope = atan(0.011813) = **0.6768°**

I re-derived this by hand and it matches the file.

### Mars: MGS MOLA MEGDR 128 ppd, tile MEGT00N090HB

**Source:** public PDS Geosciences Node, `https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/`. No credential needed.

**Labels, fetched whole and parsed at run time:**

| File | Size | SHA-256 |
| --- | --- | --- |
| `megt00n090hb.lbl` | 4820 B | `c85891df…3d36` |
| `megc00n090hb.lbl` | 3088 B | `7c373fcf…adc4` |

Facts read from the labels:
- `MEDIAN_TOPOGRAPHY`, MSB int16, METER, height = planetary radius − areoid (GMM3 mgm1025, degree/order 50)
- `COUNTS_PER_BIN`, uint8
- simple cylindrical, 128 ppd, planetocentric east-positive coordinates
- sphere radius 3396.0 km
- `PRODUCT_VERSION_ID` 2.0
- mapping time span 1997-09-15 to 2001-06-30

**Data:** 38 HTTP 206 Range requests per file, one per AOI row, all logged.

| Asset | Source file | Bytes | Byte ranges | SHA-256 |
| --- | --- | --- | --- | --- |
| Topography subset | `megt00n090hb.img` | 2888 | 13144896..13997451 | `2bc27bff39c9513a8696969abe72d4c2643c337b71b222c63e343d825e9c2c62` |
| Count subset | `megc00n090hb.img` | 1444 | 6572448..6998725 | `0e47c5bf42c15080899875b8b52daf559ec78f91d856bf56b41dd0fd71b8258c` |

Each subset is the exact server bytes of its ranges, concatenated in order. The ranges are listed in the manifest.

**AOI:** 137.25 to 137.55 E, −4.75 to −4.45 N. That is 38×38 cells, 1444 in total. Topography ranges from −4532 to −2996 m above the areoid.

**Shot support:** 371 of 1444 cells (**25.7%**) contain at least one MOLA shot. The rest are producer-interpolated. They are kept and flagged, never altered.

**QA:** `ACCEPT`, with these issues:
- `MOLA_INTERPOLATED_CELLS` (warning)
- `GRID_SPACING_IS_NOT_SHOT_FOOTPRINT` (info)

**Reference point:** at MSL Bradbury Landing (approximately 137.4417 E, −4.5895):
- The product cell holds −4503 m, but it has **0 shots**, so the value is interpolated.
- The nearest shot-supported cell, 2 cells east, holds −4517 m.

No external elevation is asserted in the file. Reviewers should compare against their own citation.

**Sample calculation**, centre block (lat −4.59375, lon 137.390625):
- 3×3 window of 4×4 block means: [[−4461.125, −4471.562, −4482.75], [−4471.562, −4484.812, −4492.5], [−4469.125, −4476.375, −4482.0]]
- dx = 1846.28 m, dy = 1852.23 m
- slope = **0.3034°**

### Why the common analysis scale is 1852.3 m

`valid_coverage_fraction` reports the **fraction of analysis blocks that contain at least one real MOLA shot**. It does not report non-fill cells, which would be 1.0 because the MEGDR interpolates every gap.

The scale is the smallest multiple of the MOLA cell at which that fraction reaches the 0.65 minimum:

| Block size | Scale | Fraction of blocks with a shot |
| --- | --- | --- |
| 1×1 | 463 m | 0.257 |
| 2×2 | 926 m | 0.463 |
| 3×3 | 1389 m | 0.597 |
| 4×4 | 1852 m | **0.741** |

SRTM is aggregated to the same scale. The trade-off: at 1852 m the Mars grid is only 9×9 blocks, so slope statistics come from 49 interior cells.

## Feature definitions (`terrain/1.0.0`)

1. **Aggregation:** non-overlapping block means. A block is valid only if all of its samples are valid; nothing is gap-filled.
2. **`slope_deg`:** AOI mean of Horn (1981) 3×3 slope.
3. **`roughness_m`:** AOI mean of the 3×3-neighbourhood elevation standard deviation.
4. **`local_relief_m`:** max − min of the block means.

Rules that apply to all features:
- A value is withheld (null, `evidence_kind: unavailable`, with `missing_reason`) if non-fill coverage is below 0.65.
- A scale finer than native resolution is refused with `TARGET_RESOLUTION_FINER_THAN_NATIVE`.

## Unit table

| Product | Stored | Native unit | Scale/offset | Fill | Vertical datum | Horizontal frame |
| --- | --- | --- | --- | --- | --- | --- |
| SRTMGL1 v003 | int16 BE | m | none | −32768 → null | EGM96 geoid | WGS84 / EPSG:4326, point-registered 1″ |
| MOLA MEGT | int16 MSB | m | none | none (interpolated) | Mars areoid GMM3 (mgm1025 d/o 50) | IAU2000 planetocentric, east-positive 0–360, R = 3396.0 km |
| MOLA MEGC | uint8 | shots/cell | none | n/a | n/a | same grid as MEGT |
| Features | — | degree, m | — | null + reason | per body (not cross-comparable for elevation) | — |

## Architecture (owned paths only)

**`backend/twinsite/sources/`:**
- `base.py`: adapter ABC with `discover / acquire / decode / validate / clean / features`, typed errors, AOI/CRS checks.
- `fetch.py`:
  - credential-free HTTP with Range resume;
  - JSONL transcripts (no auth headers, redirect queries stripped);
  - an immutable SHA-256-addressed raw store;
  - TLS verification using the macOS system root store.
- `srtm.py`, `mola.py`, `pds3.py`: the two adapters and the PDS3 label parser.
- `registry.py`: the two adapters are integrated. POWER, MOD11A2, LOLA, Diviner and COPDEM are explicitly `NOT_INTEGRATED`.

**`backend/twinsite/processing/`:**
- `terrain.py`, `dem_features.py`: feature maths; geodesy is injected per body.
- `export.py`: contract records.
- `g2_pair.py`: pipeline CLI.
- `published/`: the published file.

**Storage:** `TWINSITE_DATA_DIR`, defaulting to `<worktree>/.runtime/data/` (gitignored):
- `raw/<source>/<sha256>/…` (read-only)
- `transcripts/`
- `staging/`
- `cleaned/<sha>.json`
- `derived/<sha>.json`

Raw rasters are never committed or sent in prompts. Only references and summary numbers are exported.

**Fallback:** `--offline` uses only SHA-verified cached raw assets. If the cache is missing it raises `ACQUISITION_FAILED`; it never substitutes data.

Run:

```bash
PYTHONPATH=backend /Users/macbook/Projects/TwinSite/.venv/bin/python -m twinsite.processing.g2_pair            # network
PYTHONPATH=backend /Users/macbook/Projects/TwinSite/.venv/bin/python -m twinsite.processing.g2_pair --offline  # cache only
PYTHONPATH=backend:. /Users/macbook/Projects/TwinSite/.venv/bin/python -m unittest discover -s backend/tests/data -v
```

## TESTS

`backend/tests/data/test_c1_data.py`: **26 run, 26 passed, 0 skipped.** Coverage:

- **Missing fill:** voids stay null, any block touching a void is invalid, mostly-void tiles are withheld as INSUFFICIENT.
- **Invalid CRS:** EPSG:3857 rejected, Earth EPSG on Mars rejected, NaN rejected.
- **Body mismatch.**
- **Truncated bytes:** short HGT, wrong-resolution HGT, truncated zip, mutated stored raw (checksum gate), short MOLA subset.
- **Wrong vertical datum:** an ellipsoidal Decoded is rejected; a `PLANETARY_RADIUS` MOLA layer raises `VERTICAL_DATUM_MISMATCH`.
- **Time mismatch:** SRTM 2015 window; MOLA 2012 window.
- **Coarser target resolution:** aggregation works at 31, 90, 463 and 1000 m, and a known plane slope is recovered.
- **Finer than native:** 10 m refused.
- **Out-of-footprint:** latitude above 60N for SRTM, multi-tile AOIs, polar MOLA, cached subset not covering a new AOI.
- **Longitude conventions:** −180..180 and 0..360 handled consistently.
- **Interpolated cells:** flagged and kept unchanged; block-support fraction computed correctly.
- **Fetch safety:** credential, signed and token URLs refused; the registry refuses unintegrated sources.
- **Published file:** Draft 2020-12 schema validation of all observations, manifests and verdicts; lineage (checksum, URL, product and body match); snapshot hash; single shared analysis scale; raw cache bytes re-verified.

MOLA tests use the real labels (`backend/tests/data/fixtures/*.lbl`, SHA-256 identical to the raw assets) with synthetic data bytes. Synthetic bytes exist only inside tests.

C0's `scripts/integration/tests` cannot be imported in this worktree (`ModuleNotFoundError: ares`). `references/extracted/` is gitignored and absent here. This is unrelated to C1 and nothing in C1 touches it.

## BLOCKERS

1. **`EARTHDATA_TOKEN` absent.** LP DAAC returns 302 to `urs.earthdata.nasa.gov`, so the authoritative SRTMGL1 bytes cannot be fetched or checksum-compared. The mirror zip is 9,369,604 B against the CMR-listed 10.1048 MB. That suggests a different zip packaging; whether the inner `.hgt` is identical is **unverified**.
   - Fix: set `EARTHDATA_TOKEN` in an uncommitted `.env` and rerun `g2_pair` without `--offline`. The adapter prefers LP DAAC automatically when a token exists.
2. **Network instability during acquisition:** connection resets, read timeouts and transient DNS `[Errno 8]` (all in the transcript). The pair completed anyway; the offline cache now makes reruns deterministic.
3. **Python TLS trust (resolved):** the venv CA bundle lacked "SSL.com TLS RSA Root CA 2022", which the PDS host chains to (`CERTIFICATE_VERIFY_FAILED`). Fixed by loading the macOS system root keychain; verification is never disabled. `TWINSITE_CA_BUNDLE` can override.
4. **No GDAL/Rasterio/pyproj/numpy** in the environment, and PyPI is unreliable. Decoders are standard library and label-driven, which suits raw HGT and PDS3 IMG. COG/HDF-EOS products (MOD11A2, HLS) would need those libraries.

## CONTRACT REQUESTS FOR C0

1. **Coverage semantics:** `valid_coverage_fraction` is undefined between "non-fill product cells" and "observation-supported". C1 reports observation-supported at the analysis scale and puts the rest in `quality_flags`. Please confirm, or add a separate field such as `observation_support_fraction`.
2. **`uncertainty` semantics:** C1 currently fills `kind: interval` with the **spatial p10–p90 variability** inside the AOI, labelled as such in `basis`. Instrument error is not propagated. Please decide whether the contract needs a distinct `spatial_variability` field so C2 does not treat it as measurement error.
3. **Mirror provenance:** please decide whether a public-mirror asset (with `MIRROR_NOT_VERIFIED_AGAINST_LPDAAC`) may be `ACCEPT` for release, or must be QUALIFIED until verified against LP DAAC.

## Not done (deliberate scope on submission day)

- NASA POWER: the endpoint answers HTTP 200, but no adapter or QA was built.
- MOD11A2: requires Earthdata Login and QC-bit validation.
- LOLA, Diviner: not built.
- Multi-tile SRTM mosaics: not built.
- `backend/twinsite/vision/`: untouched.

## NEXT GATE

- **C2:** load `published/g2_feature_pair.json`, take `comparison_pairs`, and score `slope_deg` and `roughness_m` from the listed `evidence_id`s. Values, units, bodies and site IDs must match exactly for C0's contribution check.
- **C0:** review and merge `lane/data`. The snapshot hash and lineage fields are already shaped for `measured_release_issues`.
- **C5:** run independent negative controls and review.
- **User/C0:** provide `EARTHDATA_TOKEN` (env only) to upgrade the Earth asset from the mirror to the authoritative LP DAAC bytes.
