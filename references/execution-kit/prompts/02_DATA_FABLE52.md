# PROMPT — Claude account A / Fable 5.2: TWIN-DATA

You own the most difficult science-data acquisition and preprocessing lane for TwinSite. Read execution kit shared contract and the source inventories in `TwinSite_Engineering_Handoff/historical_data_reference/`, plus `ARES/research/api_inventory.csv` and the NASA data validation notes. Work only in `/backend/twinsite/sources`, `/backend/twinsite/processing`, `/backend/twinsite/vision` and YOUR tests. Do not modify frontend/API/science owned by other assistants.

HARD OBJECTIVE: integrate at least one real Earth topography product (SRTMGL1 or approved equivalent) and at least one real Mars MOLA or lunar LOLA reference product, with bounded AOIs. NASA POWER is a valuable second Earth dataset. MOD11A2 and Diviner only if QA/decode support can be validated. Never fabricate values to fill coverage gaps.

Implement a provider registry and source adapter interfaces `discover(aoi,time,product)`, `acquire(granules,byte_budget)`, `decode(asset)`, `validate(decoded)`, `clean(decoded,approved_rules)`, `features(clean,scale)`. Capture original bytes, checksum, URL/product version, license, geometry, native units, sensor QA, dates, transformations. Use immutable raw -> cleaned -> derived storage; use GDAL/Rasterio/pyproj as appropriate. Source-specific masks and scale factors. Write tests for missing fill, invalid CRS, truncated bytes, wrong vertical datum, time mismatch, coarser target resolution and out-of-footprint query.

Keep rigorous separation between Earth DEM vs Mars/Lunar geodesy. Export feature records using `contracts/SHARED_CONTRACT.md` and ARES production JSON schema. A raster should never be transmitted as a giant LLM prompt; save artifact reference and summarized numeric features.

For each source give actual acquisition transcript (no keys), product/granule ID, file/hash, unit table, quality flags, valid coverage, and one verified sample feature calculation. Preserve errors as evidence and implement deterministic fallback to cached, real source data where permitted. Public API returning 200 is NOT sufficient to call it integrated.

DELIVERABLE at G2: one objectively real NASA Earth/planetary feature pair usable by the no-AI scoring engine, with standalone tests and `DATA_STATUS.md`. Prioritize this above adding more adapters. If a product is inaccessible, report why and implement a documented alternate, without claiming success.
