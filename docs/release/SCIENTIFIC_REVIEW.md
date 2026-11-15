# Scientific release review — Zagora (SRTMGL1) vs Gale (MOLA MEGDR), 2026-11-15

**Decision: release stays BLOCK.** The six terrain measurements are reproduced from verified source bytes. Mission suitability is not
established, and the engine's outcome ("no feasible portfolio") is the scientifically correct result for
the evidence and parameters available. Nothing in this review relaxes a test, a tolerance or a gate.

## 1. What is verified: terrain measurements (with stated limits)

| Check | Earth: SRTMGL1 v003, N30W006 | Mars: MOLA MEGDR meg128 (megt/megc 00n090hb) |
| --- | --- | --- |
| Source identity | LP DAAC Earthdata Cloud. CMR granule `G2821052091-LPCLOUD`, collection `C2763266360-LPCLOUD`, DOI 10.5067/MEaSUREs/SRTM/SRTMGL1.003 | NASA PDS Geosciences Node (`pds-geosciences.wustl.edu`) |
| Origin bytes | Authenticated official download (ZIP SHA-256 `2493d4ce…`). Its decoded raster is identical to the earlier mirror (0 differing samples) | **Independently re-downloaded today** with `scripts/integration/verify_mola_origin.py`: both labels in full, and both image subsets through HTTP Range reads of the recorded rows. 4/4 SHA-256 match. No credentials used |
| Reference recomputation | Stdlib-only reference (`tests/acceptance/terrain_reference.py`, no production imports) re-implements the declared method from raw HGT at 1852.3 m. Agrees | Same reference decodes the label-defined MOLA subset with Mars geodesy. Agrees |
| Values (slope °, roughness m, relief m) | 0.5838 / 17.9224 / 313.811 | 1.5093 / 42.837 / 925.562 |
| Coverage | 1.0 (no voids) | 0.741: blocks with at least one direct MOLA shot. Interpolated cells are retained and flagged |
| Provenance checker | 19 PASS, 0 FAIL, 0 BLOCKED on current evidence | Same |

**Limits of the recomputation:** the reference was written during the C0 recovery, not by an
independent C5 reviewer. It re-implements the *same* declared method: block means, Horn slope, 3×3 SD.
It confirms decoding and arithmetic but not the choice of method. It still needs C5 sign-off.

**Limitation:** an independent re-download of the SRTM tile is **BLOCKED**. It needs Earthdata
authentication, and the only token available was exposed earlier, so it must not be reused. Earth origin
therefore rests on one authenticated download plus CMR metadata, cross-checked against a mirror.

## 2. Geospatial comparability

- **Scale:** both bodies use a common 1852.3 m analysis scale. Earth uses 60×69 SRTM posts per block, Mars uses 4×4 MOLA cells. Slope uses the Horn method on block means, and roughness is the 3×3 population SD, computed identically on both bodies. ✔
- **Datums:** EGM96 geoid (Earth) and the GMM3 areoid (Mars). Slope, roughness and relief are differential quantities. Absolute elevation is correctly refused across bodies. ✔
- **Area of interest: not comparable (new finding).** The two areas match in degrees, not in area:
  - Earth covers about 28.8 × 33.4 km, which is 270 analysis blocks (208 interior).
  - Mars covers about 17.7 × 17.8 km, which is 81 blocks (49 interior).
  - That is a 3.3× difference in area. Max−min relief depends on extent, and the slope and roughness distributions rest on very different sample sizes.
  - This was not flagged before. The measured sidecar now adds the blocking issue `AOI_EXTENT_MISMATCH:3.33x(...)`, a stronger guard. Nothing was rescaled or recomputed.
  - Fixing it needs C1 to produce matched *metric* areas of interest.
- **Source surface:** SRTM is a C-band radar surface (includes canopy and structures; minor in the arid Draa). MOLA gridding is producer-interpolated where there are no shots (only 25.7% of cells are shot-supported), and the direction of the resulting roughness bias is unknown. Both are flagged on every observation.

## 3. Uncertainty and coverage semantics

- The p10–p90 intervals describe **spatial variability**, not instrument error. This is stated in the evidence, the API metadata and the UI.
- Instrument error is **not propagated**. SRTM's absolute vertical error is <16 m (90%). The error from MOLA's interpolated grid is unquantified.
- The `[lower, upper]` utilities in the result are **missing-evidence bounds**, not confidence intervals.
- "Coverage" carries two meanings, and both are labelled:
  - Observation-supported fraction of the measurement (Mars 0.741).
  - The engine's evidence coverage, meaning the share of weighted features observed (0.8 for Zagora, because `dry_fraction` is missing).

## 4. Why no portfolio is feasible (each item is a real gap, none invented)

| Blocker | Nature | What would resolve it, and who decides |
| --- | --- | --- |
| `C5_INDEPENDENT_REVIEW_REQUIRED` | Process gate. `review_ids` is empty | A named reviewer attests the evidence. Not done by this session |
| `UNREGISTERED_FEATURE:dry_fraction` | The preset asks for a feature with no registered measurement or source | **Mission planner:** either drop `dry_fraction` or supply a measured, registered source. It must not be removed just to clear the gate |
| `NO_QUALIFIED_CANDIDATE` | The only Earth site has `access: unknown`, and the preset sets `allow_unknown_access: false` | Real access, permit, cost and duration data from the field team |
| `AOI_EXTENT_MISMATCH:3.33x` | Areas of interest are not geospatially comparable | C1 rebuilds both sites with matched metric areas |
| Single Earth candidate | Complementary portfolios need at least 2 Earth sites | More Earth analogue sites processed through C1 |

**Mission parameters are scenario assumptions, not measurements.** `measured.py` fixes these values:

- Weights: 0.45 slope, 0.35 roughness, 0.2 dry_fraction.
- Tolerances: 20°, 6 m, 0.5.
- `min_coverage`: 0.65.

The 6 m roughness tolerance alone gives roughness a similarity of 0 for a 24.9 m difference, so the ranking depends heavily on it. These values are labelled as assumptions in the result, report and UI. A release requires values supplied by the mission planner. The UI preset must not be presented as a mission recommendation.

## 5. Gate status

- **G1 (live system): ACCEPTED.** See LIVE_ACCEPTANCE.md.
- **G2 (real science): measurements REPRODUCED from verified bytes; release BLOCK.**
  - Mars source bytes are independently re-downloaded from NASA PDS; values are reproduced by the stdlib reference (C5 sign-off pending).
  - Earth source bytes come from one official authenticated download; values are reproduced by the same reference. An independent Earth re-download is pending a new token.
  - Comparability, mission parameters, access, `dry_fraction` and reviewer attestation are open.
- **G3 (explorer/portfolio/reports): PARTIAL.** The read-only explorer, comparison, reports and evidence downloads are live. Alternative portfolios (`501`), arbitrary areas of interest and additional sites are not implemented.

## 6. Required before any RELEASE

1. Revoke the exposed Earthdata token, provision a new one (`scripts/integration/provision_earthdata.py`), then re-download and compare the SRTM tile.
2. C1: rebuild both sites with matched metric areas of interest, and add at least one more Earth candidate.
3. Mission planner: supply weights, tolerances and `min_coverage`; decide on `dry_fraction`; supply access, cost and duration.
4. Named independent reviewer: attest the evidence, which records `review_ids`. Only then can C0 consider RELEASE.
