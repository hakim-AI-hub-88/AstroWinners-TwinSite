#############################################################################
# DATA LAYERS + REGION CHECK (TWINSITE interactive globes)
#
# Why this file exists:
#   1. layer_png(body, feature): turns the harmonized PHYSICAL data of one body
#      (or one Earth zone) into a colour PNG (equirectangular) that the 3D/2D
#      globes drape over the planet: temperature, albedo, slope, elevation...
#      Display only (explanation role) - never used for scoring.
#   2. region_info(planet, lat, lon, radius): is there enough data in a region
#      picked on the Moon / Mars globe to analyse it? Which features, which
#      values? Used before "Analyse this region".
#############################################################################
from __future__ import annotations

import io
import math
from functools import lru_cache

import numpy as np

from services import analysis, data_loader
from utils import config

# feature -> (label, units, colour stops)
INFERNO = ["#000004", "#57106e", "#bc3754", "#f98e09", "#fcffa4"]
VIRIDIS = ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"]
PLASMA = ["#0d0887", "#7e03a8", "#cc4778", "#f89540", "#f0f921"]
TERRAIN = ["#2c2c78", "#3c8cb4", "#78be78", "#e6d28c", "#a05a3c", "#ffffff"]
GREY = ["#0a0a0a", "#5a5a5a", "#f0f0f0"]
COVERAGE = ["#f97316", "#facc15", "#4ade80"]
FEATURE_STYLE = {
    "temperature_day": ("Day temperature", "K", INFERNO),
    "temperature_night": ("Night temperature", "K", INFERNO),
    "albedo": ("Albedo (brightness)", "", GREY),
    "elevation": ("Elevation", "m", TERRAIN),
    "slope": ("Slope", "°", VIRIDIS),
    "relief": ("Local relief", "m", VIRIDIS),
    "thermal_inertia": ("Thermal inertia", "TIU", PLASMA),
    "mineral_index": ("Iron (Fe)", "wt%", PLASMA),
}
BODIES = {"mars": "mars", "moon": "moon"}          # global bodies (+ Earth zones from config.EARTH_ZONES)


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _physical(body: str):
    if body in BODIES:
        return data_loader.load_physical(body)
    if body in config.EARTH_ZONES:
        return data_loader.load_zone(body, "physical")
    raise KeyError(body)


def _comparable() -> list[str]:
    """Features that can be compared with the Earth zones (elevation is excluded from scoring)."""
    excluded = set(config.SIMILARITY.get("excluded", []))
    earth = data_loader.load_zone(config.DEFAULT_ZONE, "physical")
    return [f for f in config.FEATURES if f not in excluded and f in earth and earth[f].notna().mean() > 0.5]


#############################################
# GRID: (lat, lon) table -> 2-D array (north up, west left)
#############################################
@lru_cache(maxsize=8)
def _grid_index(body: str):
    df = _physical(body)
    lat = df["latitude"].to_numpy(float)
    lon = df["longitude"].to_numpy(float)
    ulat = np.unique(np.round(lat, 4))
    res = float(np.min(np.diff(ulat))) if len(ulat) > 1 else 0.1
    if body in BODIES:
        west, east, south, north = -180.0, 180.0, -90.0, 90.0
    else:
        west, east = lon.min() - res / 2, lon.max() + res / 2
        south, north = lat.min() - res / 2, lat.max() + res / 2
    ncol = int(round((east - west) / res))
    nrow = int(round((north - south) / res))
    col = np.clip(np.floor((lon - west) / res).astype(int), 0, ncol - 1)
    row = np.clip(np.floor((north - lat) / res).astype(int), 0, nrow - 1)
    return row, col, nrow, ncol, (round(west, 6), round(south, 6), round(east, 6), round(north, 6)), res


def _grid(body: str, values: np.ndarray) -> np.ndarray:
    row, col, nrow, ncol, _, _ = _grid_index(body)
    g = np.full((nrow, ncol), np.nan, dtype="float32")
    g[row, col] = values
    return g


def _colorize(g: np.ndarray, stops: list[str], lo: float, hi: float, alpha: int = 215) -> bytes:
    from PIL import Image
    cols = np.array([_hex(c) for c in stops], dtype="float32")
    t = np.clip((g - lo) / (hi - lo if hi > lo else 1), 0, 1)
    x = np.nan_to_num(t, nan=0) * (len(stops) - 1)
    i = np.minimum(x.astype(int), len(stops) - 2)
    f = (x - i)[..., None]
    rgb = cols[i] + (cols[i + 1] - cols[i]) * f
    a = np.where(np.isfinite(g), alpha, 0).astype("uint8")
    img = Image.fromarray(np.dstack([rgb.astype("uint8"), a]), "RGBA")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


#############################################
# PUBLIC: layer catalogue + PNG
#############################################
@lru_cache(maxsize=8)
def catalogue(body: str) -> list[dict]:
    df = _physical(body)
    rect = list(_grid_index(body)[4])
    out = []
    for f, (label, units, stops) in FEATURE_STYLE.items():
        if f not in df or df[f].notna().mean() < 0.02:
            continue
        v = df[f].to_numpy(float)
        v = v[np.isfinite(v)]
        lo, hi = (float(np.percentile(v, 2)), float(np.percentile(v, 98))) if len(v) else (0.0, 1.0)
        out.append({"id": f, "label": label, "units": units, "min": round(lo, 3), "max": round(hi, 3),
                    "colors": stops, "coverage_pct": round(100 * float(df[f].notna().mean()), 1),
                    "url": f"/api/layer/{body}/{f}.png", "rectangle": rect})
    out.append({"id": "coverage", "label": "Data coverage (features available for matching)", "units": "features",
                "min": 0, "max": len(_comparable()), "colors": COVERAGE,
                "url": f"/api/layer/{body}/coverage.png", "rectangle": rect})
    return out


@lru_cache(maxsize=64)
def layer_png(body: str, feature: str) -> bytes:
    df = _physical(body)
    if feature == "coverage":
        comp = [f for f in _comparable() if f in df]
        n = df[comp].notna().sum(axis=1).to_numpy("float32")
        n[n == 0] = np.nan
        return _colorize(_grid(body, n), COVERAGE, 1, max(len(comp), 2), alpha=150)
    if feature not in FEATURE_STYLE or feature not in df:
        raise KeyError(feature)
    meta = next(x for x in catalogue(body) if x["id"] == feature)
    return _colorize(_grid(body, df[feature].to_numpy("float32")), FEATURE_STYLE[feature][2], meta["min"], meta["max"])


#############################################
# PUBLIC: can this selected region be analysed?
#############################################
def region_info(planet: str, lat: float, lon: float, radius_km: int) -> dict:
    c = config.CUSTOM_TARGET
    if planet not in BODIES:
        raise analysis.AnalysisInputError("planet must be 'mars' or 'moon'")
    if radius_km not in c["radius_km_choices"]:
        raise analysis.AnalysisInputError(f"radius must be one of {c['radius_km_choices']} km")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise analysis.AnalysisInputError("latitude / longitude out of range")
    phys = data_loader.load_physical(planet)
    window = data_loader.extract_target_window(phys, lat, lon, radius_km, config.BODY_RADIUS_M[planet])
    comp = _comparable()
    cov = {f: (round(float(window[f].notna().mean()), 3) if len(window) and f in window else 0.0) for f in config.FEATURES}
    usable = [f for f in comp if cov.get(f, 0) >= c["min_feature_coverage"]]
    profile = {f: (None if not len(window) or window[f].isna().all() else round(float(window[f].mean()), 3))
               for f in config.FEATURES}
    ok = len(window) >= c["min_cells"] and len(usable) >= c["min_comparable_features"]
    reason = None
    if len(window) < c["min_cells"]:
        reason = "No harmonized cells in this region."
    elif not ok:
        missing = [f for f in comp if f not in usable]
        reason = f"Only {len(usable)} comparable features here (missing: {', '.join(missing)})."
    # nearest catalogue target (helps the user)
    R = config.BODY_RADIUS_M[planet] / 1000
    near = None
    for name, t in config.TARGETS[planet].items():
        p1, p2 = math.radians(lat), math.radians(t["lat"])
        d = math.acos(max(-1, min(1, math.sin(p1) * math.sin(p2) + math.cos(p1) * math.cos(p2) * math.cos(math.radians(lon - t["lon"]))))) * R
        if near is None or d < near["distance_km"]:
            near = {"name": name, "distance_km": round(d)}
    return {
        "planet": planet, "lat": round(lat, 3), "lon": round(lon, 3), "radius_km": radius_km,
        "area_km2": round((2 * radius_km) ** 2), "cells": int(len(window)),
        "features_available": usable, "features_comparable": comp, "coverage": cov,
        "profile_physical": profile, "analysable": bool(ok), "reason": reason,
        "location": analysis.custom_location(lat, lon, radius_km), "nearest_catalogue_target": near,
    }
