# TwinSite presentation sources and attribution

Evidence snapshot: 15 November 2026. The deck has 14 main slides and four optional appendix slides. NASA Space Apps Challenge 2026 is event context, not NASA endorsement. No public deployment URL is claimed.

## Scientific imagery

- **Earth, Anti-Atlas Mountains, Morocco:** NASA Earth Observatory / Earth Sciences and Image Analysis Laboratory, NASA Johnson Space Center. STS108-711-25. [Source and caption](https://science.nasa.gov/earth/earth-observatory/anti-atlas-mountains-morocco-2178/). The supplied photo contains geographic annotations. It illustrates regional geological context and does not depict the exact Zagora analysis boundary. Used as a cropped background on slides 1 and 3.
- **Moon, Tycho central peak:** NASA/GSFC/Arizona State University, Lunar Reconnaissance Orbiter. [NASA Moonscapes gallery](https://science.nasa.gov/moon/image-galleries/moonscapes/). Asset `22_Tycho_Crater_terrestrial.png`. Used on slides 2, 3 and 17 as context/background. Tycho is not the Taurus–Littrow measurement site.
- **Mars, Curiosity Looks Downslope From the Sulfate Unit, PIA26551:** NASA/JPL-Caltech/MSSS. Captured 7 February 2025. [Source and caption](https://science.nasa.gov/photojournal/curiosity-looks-downslope-from-the-sulfate-unit/). The source adjusted colors to approximate Earth lighting. Used on slides 1, 3 and 13 as a cropped context background, not as measurement evidence. NASA image service requested at up to 4096 pixels wide.
- General NASA media use guidance: [NASA Images and Media Usage Guidelines](https://www.nasa.gov/nasa-brand-center/images-and-media/). Credits appear in speaker notes and here. No NASA logo is used.

Repeated scientific photographs serve as background elements for continuity. No generated planetary imagery is used. Resizing and cropping do not alter the scientific numbers. The contextual images do not define the measurement AOIs.

## Authentic application captures

Screenshots came from the running TwinSite application on port 5180 at a requested 1600 × 1000 viewport. Application behavior was inspected in a real browser, without changing application code. Original captures and composed crops are in `assets/`. The landing capture was retaken after viewport sizing.

- Landing, mission workspace, Data Explorer catalog, side-by-side Zagora–Gale comparison.
- Measured analysis, agent records, P00–P90 activity, actual infeasible portfolio outcome.
- Scientific report, source and QA inspection, cleaned SRTM grid.
- Earth/Moon/Mars explorer captures were attempted. Partial lunar tile loading and a stale Mars capture make those two files unsuitable as evidence of a fully rendered planetary map. They are excluded from the presentation. Only verified functioning views are featured.
- The full Data Explorer capture can exceed viewport width because the page includes wide tables. Featured crops come from the standard viewport captures.
- Recorded run: `run-d7b84f7f350ac24de32b069e`. The recorded AI narrative includes flagged claims. The deck shows the deterministic result and describes the flags instead of quoting those claims as facts.

## Numerical evidence

`source/missions_run-d7b84f7f350ac24de32b069e_evidence.json` is a read-only copy of the live evidence API response. `source/g2_feature_pair.json` is the published pair artifact. The six values on slide 9 match both:

| Feature | Earth, Zagora | Mars, Gale | Unit |
|---|---:|---:|---|
| Mean slope | 0.5838 | 1.5093 | degree |
| Mean roughness | 17.9224 | 42.837 | m |
| Local relief | 313.811 | 925.562 | m |

Analysis scale: 1852.3 m. Earth source: SRTMGL1 v003, N30W006, [DOI 10.5067/MEaSUREs/SRTM/SRTMGL1.003](https://doi.org/10.5067/MEaSUREs/SRTM/SRTMGL1.003). Mars source: [MOLA MEGDR, NASA PDS Geosciences](https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/), meg128 topography/counts subsets and their labels. Asset identities and SHA-256 checksums remain in the evidence copy.

The current offline provenance verifier reproduced all six terrain summaries from cached source bytes, without a network refetch. Its check of arithmetic and encoding does not independently prove source origin or validate the method choice. Historical origin checks and their limits are documented in `docs/release/SCIENTIFIC_REVIEW.md`. Independent scientific reviewer attestation remains pending.

The pair uses different physical study extents: approximately 28.8 × 33.4 km on Earth and 17.7 × 17.8 km on Mars. The 3.33 ratio is from 270/81 analysis blocks. Those counts are not square kilometers. Extent-dependent statistics cannot establish equivalence across these AOIs. MOLA interpolated cells remain flagged. Spatial p10–p90 intervals are variability, not propagated instrument uncertainty. Missing-evidence utility bounds are not confidence intervals.

## New lunar evidence

The live catalog and `source/moon_feature_pair.json` include the Zagora–Taurus–Littrow pair. The lunar terrain source is LOLA LDEM_64. Diviner GCP provides lunar thermal context. The terrain scale is 1895.3 m, so its Earth summaries differ from the Mars-pair summaries. Seven current connector unit tests pass; this is engineering validation, not independent scientific validation. Thermal values have a different, coarser spatial support and do not enter the displayed terrain comparison. No matched Earth surface-temperature evidence is claimed.

## Implementation and verification references

Primary inspected code: `backend/twinsite/ai/agents.py`, `ai/router.py`, `jobs/worker.py`, `jobs/measured.py`, `science/engine.py`, `science/registry.py`, `portfolios/selection.py`, `processing/terrain.py`, `processing/moon_pair.py`, `sources/lola.py`, `sources/diviner.py`, `sources/sites.py`; corresponding frontend pages and components.

The live trace copy in `source/` records A01–A13. Seven AI roles executed, including one cached real call. Six roles were deterministic. A09 reports three numeric mismatches, and A12 leaves three flagged claims unsupported. AI review is advisory and cannot set the release gate.

`source/verification_summary.json` records 17 PASS automated checks and one BLOCKED browser-smoke item requiring separate browser verification. The older statement that every check passes and the command exits zero is not used. This presentation's browser capture and focused offline checks are additional evidence, not a new blanket certification of the application.

The README and root status files predate later work. The deck prioritizes current code, the live UI, live API responses and the latest published artifacts. Current code includes point-based measured discovery and recent lunar adapters, so these are not described as wholly absent. Their complete scientific validation is not claimed. The current coverage matrix is partial and evolving; the deck avoids stale domain-completeness counts.

## Deliberate scientific limits

Scientific release remains BLOCK. No qualifying measured multi-site portfolio, independently validated AI conclusion, complete 14-domain coverage, global discovery validation, deployment, mission adoption or field campaign success is asserted. AI-proposed scenarios and mission weights are assumptions. Costs and access require user-provided evidence. No credential values are included in the deck or presentation source.
