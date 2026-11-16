# Bundled source cache: published Zagora–Gale pair

The exact source bytes behind the published measured pair
(`backend/twinsite/processing/published/g2_feature_pair.json`), 17.6 MB:

- `raw/SRTMGL1/…/N30W006.SRTMGL1.hgt.zip`: NASA SRTM GL1 elevation tile (LP DAAC, public domain).
- `raw/MOLA_MEGDR/…`: MGS MOLA MEGDR byte ranges and labels (NASA PDS, public domain).
- `cleaned/*.json`: TwinSite cleaned grids derived from those files.

Every file is addressed by its SHA-256. At container start, `ops/container/start.sh` installs them into
`TWINSITE_SOURCE_DATA_DIR` with `ops/provision_source_cache.py`, which verifies each hash before and
after copying. This lets a fresh host (Render, Docker, Hugging Face) run measured missions and the Data
Explorer grid without a separate download step.
