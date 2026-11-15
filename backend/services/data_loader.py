#############################################################################
# DATA LOADING MODULE
#
# Why this file exists:
#   Load the harmonized planetary datasets (Earth, Mars, Moon) produced by the
#   data pipeline and prepare them for similarity analysis. It is the ONLY
#   place that touches the data files, so the rest of the app never deals
#   with paths, compression or dtypes.
#
# What it provides:
#   load_earth_data() / load_mars_data() / load_moon_data()
#       -> pandas.DataFrame with columns:
#          latitude, longitude, <9 features normalized 0-1>, quality_flags
#   dataset_status()        -> summary used by GET /api/status
#   extract_target_window() -> cells around a planetary target (input of
#                              the future similarity engine)
#
# Design choices:
#   - Files are read once and cached in memory (functools.lru_cache): Mars
#     has ~1.8 million rows, re-reading it per request would be far too slow.
#   - float32 instead of float64 halves memory (~90 MB for Mars).
#   - Files are read in place: no copy of the data is made.
#
# Future extension:
#   - switch to Parquet for faster start-up
#   - add a new body: one entry in config.DATASET_FILES + one loader
#############################################################################
from __future__ import annotations

import logging
import math
from functools import lru_cache

import numpy as np
import pandas as pd

from utils import config

log = logging.getLogger(__name__)


#############################################
# LOW-LEVEL LOADER (shared by the 3 bodies and both harmonized roles)
# Input : body name ("earth" | "mars" | "moon"), physical=False -> normalized file
#                                                physical=True  -> physical-unit file
# Output: DataFrame (cached after the first call)
# Raises: FileNotFoundError with a helpful message if the pipeline was not run
#############################################
@lru_cache(maxsize=None)
def _load(body: str, physical: bool = False) -> pd.DataFrame:
    files = config.PHYSICAL_FILES if physical else config.DATASET_FILES
    path = config.HARMONIZED_DATA_DIR / files[body]
    return _read_schema_csv(path, body)


def _read_schema_csv(path, body: str) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run the data pipeline first "
            "(pipeline/: run_pipeline.py -> run_planetary.py -> run_harmonize.py)."
        )
    dtypes = {c: "float32" for c in config.COORDINATE_COLUMNS + config.FEATURES}
    dtypes[config.QUALITY_COLUMN] = "int32"
    df = pd.read_csv(path, dtype=dtypes)   # .gz is decompressed automatically
    missing = set(dtypes) - set(df.columns)
    if missing:
        raise ValueError(f"{path.name}: missing columns {sorted(missing)}")
    log.info("Loaded %s: %d rows from %s", body, len(df), path.name)
    return df


#############################################
# PUBLIC LOADERS (one per body, as required by the API layer)
# Output: DataFrame - do NOT modify it in place (it is the shared cache);
#         use .copy() if a caller needs to change values.
#############################################
def load_earth_data() -> pd.DataFrame:
    """Atacama Desert cells (~11 km), normalized features."""
    return _load("earth")


def load_mars_data() -> pd.DataFrame:
    """Global Mars cells (~11 km), normalized features."""
    return _load("mars")


def load_moon_data() -> pd.DataFrame:
    """Global Moon cells (~11 km), normalized features."""
    return _load("moon")


LOADERS = {"earth": load_earth_data, "mars": load_mars_data, "moon": load_moon_data}


#############################################
# ROLE 2 - PHYSICAL (harmonized, NOT normalized) DATA
# Used only to explain results in real units (K, degrees, m). Never for scoring.
#############################################
def load_physical(body: str) -> pd.DataFrame:
    return _load(body, physical=True)


#############################################
# ROLE 3 - EARTH PROCESSED DATA (~1 km, physical units)
# Used only to refine a top region into an exact location. Never for scoring.
#############################################
@lru_cache(maxsize=1)
def load_earth_processed() -> pd.DataFrame:
    return _read_schema_csv(config.EARTH_PROCESSED_FILE, "earth (processed 1 km)")


#############################################
# EARTH ZONES (Atacama = default, Merzouga = second zone)
# Input : zone id from config.EARTH_ZONES, role = "normalized" | "physical" | "processed"
# Output: DataFrame with the common schema (same columns for every zone)
# The Atacama returns exactly the same cached DataFrames as before.
#############################################
def load_zone(zone: str, role: str) -> pd.DataFrame:
    if zone not in config.EARTH_ZONES:
        raise ValueError(f"Unknown Earth zone '{zone}'. Choose one of {list(config.EARTH_ZONES)}.")
    if zone == config.DEFAULT_ZONE:
        return {"normalized": load_earth_data, "physical": lambda: load_physical("earth"),
                "processed": load_earth_processed}[role]()
    return _load_zone_file(zone, role)


@lru_cache(maxsize=None)
def _load_zone_file(zone: str, role: str) -> pd.DataFrame:
    z = config.EARTH_ZONES[zone]
    path = z["processed"] if role == "processed" else config.HARMONIZED_DATA_DIR / z[role]
    return _read_schema_csv(path, f"{zone} ({role})")


def zone_available(zone: str) -> bool:
    try:
        load_zone(zone, "normalized")
        return True
    except (FileNotFoundError, ValueError):
        return False


def load_all() -> dict[str, pd.DataFrame]:
    """Load every dataset once at server start-up (normalized, physical, processed)."""
    data = {body: loader() for body, loader in LOADERS.items()}
    for body in LOADERS:
        load_physical(body)
    load_earth_processed()
    for zone in config.EARTH_ZONES:                 # extra zones: optional, never block start-up
        if zone == config.DEFAULT_ZONE:
            continue
        try:
            for role in ("normalized", "physical", "processed"):
                load_zone(zone, role)
        except (FileNotFoundError, ValueError) as exc:
            log.warning("Earth zone %s not loaded: %s", zone, exc)
    return data


#############################################
# STATUS SUMMARY (for GET /api/status)
# Output per body: loaded flag, row count, features with data,
#                  features without any data (not downloaded yet)
#############################################
def dataset_status() -> dict:
    status = {}
    for body, loader in LOADERS.items():
        try:
            df = loader()
        except (FileNotFoundError, ValueError) as exc:
            status[body] = {"loaded": False, "error": str(exc)}
            continue
        coverage = df[config.FEATURES].notna().mean().round(4)
        status[body] = {
            "loaded": True,
            "rows": int(len(df)),
            "available_features": [f for f in config.FEATURES if coverage[f] > 0],
            "missing_features": [f for f in config.FEATURES if coverage[f] == 0],
            "feature_coverage": {f: float(coverage[f]) for f in config.FEATURES},
        }
    for zone, z in config.EARTH_ZONES.items():
        if zone == config.DEFAULT_ZONE:
            continue
        try:
            df = load_zone(zone, "normalized")
        except (FileNotFoundError, ValueError) as exc:
            status[zone] = {"loaded": False, "error": str(exc)}
            continue
        coverage = df[config.FEATURES].notna().mean().round(4)
        status[zone] = {"loaded": True, "rows": int(len(df)), "zone": z["full_name"],
                        "available_features": [f for f in config.FEATURES if coverage[f] > 0],
                        "missing_features": [f for f in config.FEATURES if coverage[f] == 0],
                        "feature_coverage": {f: float(coverage[f]) for f in config.FEATURES}}
    return status


#############################################
# TARGET WINDOW EXTRACTION (preparation for the similarity engine)
# Input : body DataFrame, target lat/lon (deg), radius (km), body radius (m)
# Output: DataFrame of the cells whose centre lies within `radius_km`
#         (great-circle distance), with an extra "distance_km" column.
# Why   : a single 11 km cell is noisy; the engine will compare Earth cells
#         with the AVERAGE profile of the area around the target.
#############################################
def extract_target_window(df: pd.DataFrame, lat: float, lon: float, radius_km: float,
                          body_radius_m: float) -> pd.DataFrame:
    deg = math.degrees(radius_km * 1000 / body_radius_m)            # radius in degrees of latitude
    band = df[(df["latitude"] - lat).abs() <= deg]                  # cheap pre-filter
    phi1, phi2 = np.radians(lat), np.radians(band["latitude"].to_numpy())
    dlon = np.radians(band["longitude"].to_numpy() - lon)
    cos_angle = np.sin(phi1) * np.sin(phi2) + np.cos(phi1) * np.cos(phi2) * np.cos(dlon)
    dist_km = np.arccos(np.clip(cos_angle, -1, 1)) * body_radius_m / 1000
    window = band.loc[dist_km <= radius_km].copy()
    window["distance_km"] = dist_km[dist_km <= radius_km]
    return window


def target_profile(window: pd.DataFrame) -> dict:
    """Mean normalized value of each feature in a target window (None if no data)."""
    means = window[config.FEATURES].mean()
    return {f: (None if pd.isna(means[f]) else round(float(means[f]), 4)) for f in config.FEATURES}
