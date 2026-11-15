#############################################################################
# HIGH-RESOLUTION REFINEMENT  (phase 2)
#
# Why this file exists:
#   The similarity engine ranks ~11 km regions. A field team needs a point.
#   This module searches INSIDE one top region using the Earth PROCESSED data
#   (~1 km cells, physical units) and returns an exact recommended location.
#
# Data role: EARTH PROCESSED data only (never used for scoring).
#
# Method (deliberately simple and explainable):
#   1. Keep the 1 km cells inside the region.
#   2. Drop open water / salt lagoons and cells steeper than max_slope_deg
#      (a rover or field team must be able to work there).
#   3. Among the rest, pick the cell whose day + night surface temperatures are
#      closest (in kelvin) to the target's physical temperatures.
#   Terrain is NOT re-compared at 1 km: those slopes come from 30 m data and are
#   not on the same scale as the 3.7 km planetary slopes (scientific bias).
#
# Input : region centre (lat, lon), cell size (deg), target physical profile,
#         Earth processed DataFrame
# Output: dict with lat/lon of the recommended point, its values, and how many
#         candidates were considered; None if nothing qualifies.
#
# Future extension: refine further with NASADEM 30 m (local slope, roughness).
#############################################################################
from __future__ import annotations

import numpy as np
import pandas as pd

from utils import config


#############################################
# ROVER ACCESSIBILITY OF EVERY REGION (mission planner filter)
# Input : harmonized Earth cells (for their centres), cell size (deg),
#         Earth processed 1 km data, slope limit (deg)
# Output: Series aligned with `earth.index`: share (0-1) of the region's land
#         1 km cells whose mean slope <= max_slope (NaN if no land data)
# Note  : 1 km slopes are means of 30 m slopes, a reasonable proxy for what a
#         rover drives on; they are NOT compared with planetary slopes.
#############################################
_ACCESS_CACHE: dict[tuple, pd.Series] = {}


def accessibility_by_cell(earth: pd.DataFrame, cell_deg: float, processed: pd.DataFrame,
                          max_slope: float) -> pd.Series:
    # Earth data never changes while the server runs -> cache per slope limit.
    key = (id(earth), id(processed), round(cell_deg, 6), round(float(max_slope), 2))
    if key not in _ACCESS_CACHE:
        _ACCESS_CACHE[key] = _accessibility(earth, cell_deg, processed, max_slope)
    return _ACCESS_CACHE[key]


def _accessibility(earth: pd.DataFrame, cell_deg: float, processed: pd.DataFrame, max_slope: float) -> pd.Series:
    lat_top = float(earth["latitude"].max()) + cell_deg / 2
    lon_left = float(earth["longitude"].min()) - cell_deg / 2

    def keys(lat, lon):
        r = np.floor((lat_top - lat.to_numpy(dtype=float)) / cell_deg + 1e-9).astype(int)
        c = np.floor((lon.to_numpy(dtype=float) - lon_left) / cell_deg + 1e-9).astype(int)
        return r * 100_000 + c

    land = ((processed[config.QUALITY_COLUMN] & config.FLAG_BITS["WATER"]) == 0) & processed["slope"].notna()
    df = pd.DataFrame({"key": keys(processed["latitude"], processed["longitude"]),
                       "land": land.to_numpy(), "ok": (land & (processed["slope"] <= max_slope)).to_numpy()})
    agg = df.groupby("key")[["land", "ok"]].sum()
    frac = (agg["ok"] / agg["land"].where(agg["land"] > 0)).rename("accessible")
    return pd.Series(keys(earth["latitude"], earth["longitude"]), index=earth.index).map(frac)


def refine(lat: float, lon: float, cell_deg: float, target_phys: dict, processed: pd.DataFrame,
           max_slope: float | None = None) -> dict | None:
    cfg = dict(config.REFINEMENT)
    if max_slope is not None:
        cfg["max_slope_deg"] = max_slope
    half = cell_deg / 2
    sub = processed[(processed["latitude"].between(lat - half, lat + half))
                    & (processed["longitude"].between(lon - half, lon + half))]
    n_total = len(sub)
    if cfg["exclude_water"]:
        sub = sub[(sub[config.QUALITY_COLUMN] & config.FLAG_BITS["WATER"]) == 0]
    sub = sub[sub["slope"] <= cfg["max_slope_deg"]]
    if sub.empty:
        return None

    mismatch = np.zeros(len(sub))
    used = []
    for f in ("temperature_day", "temperature_night"):
        t = target_phys.get(f)
        if t is not None and np.isfinite(t):
            mismatch += np.abs(sub[f].to_numpy(dtype=float) - t)
            used.append(f)
    mismatch = np.where(np.isfinite(mismatch), mismatch, np.inf)
    i = int(np.argmin(mismatch)) if used else int(np.argmin(sub["slope"].to_numpy()))
    best = sub.iloc[i]

    def v(f, d=2):
        x = best[f]
        return None if pd.isna(x) else round(float(x), d)

    return {
        "lat": round(float(best["latitude"]), 4), "lon": round(float(best["longitude"]), 4),
        "resolution_km": 1.0,
        "elevation_m": v("elevation", 0), "slope_deg": v("slope", 1),
        "temperature_day_K": v("temperature_day", 1), "temperature_night_K": v("temperature_night", 1),
        "temperature_mismatch_K": round(float(mismatch[i]), 1) if used and np.isfinite(mismatch[i]) else None,
        "candidates": int(len(sub)), "cells_in_region": int(n_total),
        "criteria": (f"no water, slope <= {cfg['max_slope_deg']:g} deg, closest "
                     + (" + ".join(u.replace('temperature_', '') + " temperature" for u in used) or "lowest slope")
                     + " to the target"),
    }
