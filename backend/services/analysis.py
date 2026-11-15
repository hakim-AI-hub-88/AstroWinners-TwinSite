#############################################################################
# ANALYSIS SERVICE (shared by the API route and the AI assistant)
#
# Why this file exists:
#   One function runs a complete similarity analysis for a target, loading each
#   dataset in its own role. The dashboard (POST /api/similarity) and the
#   Mission Assistant's tools both call it, so the assistant always explains
#   exactly the numbers the user sees - never a second, divergent computation.
#
# Input : planet, location, rover_mode, max_slope (already validated)
# Output: the similarity_engine result dict + "target" and "earth_candidates"
# Raises: FileNotFoundError / ValueError when the datasets are missing
#
# Results are cached (same inputs -> same answer; data never changes at runtime).
#############################################################################
from __future__ import annotations

import re
from functools import lru_cache

from services import cleaning as cleaning_mod
from services import data_loader, similarity_engine, validation
from utils import config


class AnalysisInputError(ValueError):
    """Unknown planet / location or invalid slope limit."""


#############################################
# MISSION OPTIONS (accepted by every mission entry point)
#   cleaning   raw | standard (default) | strict | robust   (services/cleaning.py)
#   data_mode  bundled (default: data_ready only) | auto (bundled + live NASA
#              acquisition of the target point, services/live_data.py)
#############################################
DATA_MODES = ("bundled", "auto")
DEFAULT_DATA_MODE = "bundled"


def validate_options(cleaning=None, data_mode=None) -> tuple[str, str]:
    """Validate the optional mission options; defaults keep the historical behaviour."""
    try:
        c = cleaning_mod.validate_profile(cleaning)
    except cleaning_mod.CleaningError as exc:
        raise AnalysisInputError(str(exc)) from None
    m = str(data_mode or DEFAULT_DATA_MODE).strip().lower()
    if m not in DATA_MODES:
        raise AnalysisInputError(f"Unknown data_mode '{data_mode}'. Choose one of {list(DATA_MODES)}.")
    return c, m


def validate_zone(zone) -> str:
    zone = str(zone or config.DEFAULT_ZONE).lower()
    if zone not in config.EARTH_ZONES:
        raise AnalysisInputError(f"Unknown Earth zone '{zone}'. Choose one of {list(config.EARTH_ZONES)}.")
    return zone


#############################################
# USER-SELECTED REGIONS (TWINSITE interactive globe)
#   Besides the catalogue targets, a location can be a region picked on the
#   Moon / Mars globe, encoded in its name so that every module (dashboard,
#   pattern analysis, assistant, report) works with it unchanged:
#       "Selected region @ 34.940, 21.970 / 50 km"
#############################################
CUSTOM_RE = re.compile(r"^Selected region @ (-?\d+(?:\.\d+)?), (-?\d+(?:\.\d+)?) / (\d+) km$")


def custom_location(lat: float, lon: float, radius_km: int) -> str:
    return f"Selected region @ {lat:.3f}, {lon:.3f} / {int(radius_km)} km"


def target_def(planet: str, location: str) -> dict | None:
    """Catalogue target, or the definition parsed from a selected-region name (None if invalid)."""
    if location in config.TARGETS.get(planet, {}):
        return config.TARGETS[planet][location]
    m = CUSTOM_RE.match(str(location or ""))
    if not m:
        return None
    lat, lon, r = float(m.group(1)), float(m.group(2)), int(m.group(3))
    c = config.CUSTOM_TARGET
    if not (-90 <= lat <= 90 and -180 <= lon <= 180) or r not in c["radius_km_choices"]:
        return None
    return {"lat": lat, "lon": lon, "window_km": r, "note": c["note"], "custom": True}


def validate(planet: str, location: str, rover_mode: bool, max_slope) -> tuple[str, str, bool, float]:
    planet = str(planet or "").lower()
    if planet not in config.TARGETS:
        raise AnalysisInputError(f"Unknown planet '{planet}'. Choose one of {list(config.TARGETS)}.")
    if target_def(planet, location) is None:
        raise AnalysisInputError(f"Unknown location '{location}' for {planet}. Choose one of {list(config.TARGETS[planet])} "
                                 "or a region selected on the globe.")
    lo, hi = config.ROVER["slope_limits"]
    try:
        max_slope = float(config.ROVER["default_max_slope_deg"] if max_slope is None else max_slope)
    except (TypeError, ValueError):
        raise AnalysisInputError("max_slope must be a number") from None
    if not lo <= max_slope <= hi:
        raise AnalysisInputError(f"max_slope must be between {lo} and {hi} degrees")
    return planet, location, bool(rover_mode), max_slope


@lru_cache(maxsize=64)
def run(planet: str, location: str, rover_mode: bool = False, max_slope: float = 15.0,
        zone: str = config.DEFAULT_ZONE, cleaning: str = cleaning_mod.DEFAULT_PROFILE) -> dict:
    """Full analysis for one target in one Earth zone (default: Atacama). Read-only result (cached).

    `cleaning` (services/cleaning.py) is applied to the two scoring frames only: the target window and
    the Earth zone (normalized). "standard" leaves them untouched, so the result is exactly the
    historical one plus the `options` and `cleaning_report` keys. Physical (explanation) and processed
    (refinement) frames are never cleaned here.
    """
    cleaning = cleaning_mod.validate_profile(cleaning)
    body_df = data_loader.LOADERS[planet]()               # role 1: normalized (scoring)
    earth_df = data_loader.load_zone(zone, "normalized")
    body_phys = data_loader.load_physical(planet)          # role 2: physical (explanation)
    earth_phys = data_loader.load_zone(zone, "physical")
    earth_proc = data_loader.load_zone(zone, "processed")  # role 3: 1 km (refinement)

    t = target_def(planet, location)
    radius = config.BODY_RADIUS_M[planet]
    window = data_loader.extract_target_window(body_df, t["lat"], t["lon"], t["window_km"], radius)
    window_phys = data_loader.extract_target_window(body_phys, t["lat"], t["lon"], t["window_km"], radius)
    window, target_report = cleaning_mod.apply(window, cleaning, config.FEATURES, "normalized")
    earth_df, earth_report = cleaning_mod.apply(earth_df, cleaning, config.FEATURES, "normalized")
    result = similarity_engine.compute(similarity_engine.SimilarityRequest(
        body=planet, location=location, target_window=window, earth=earth_df,
        target_window_physical=window_phys, earth_physical=earth_phys, earth_processed=earth_proc,
        rover_mode=rover_mode, max_slope=max_slope,
        uncertainty_penalty=cleaning_mod.PROFILES[cleaning]["engine"]["uncertainty_penalty"]))

    result["target"] = {
        "planet": planet, "location": location, "lat": t["lat"], "lon": t["lon"],
        "window_km": t["window_km"], "note": t["note"], "custom": bool(t.get("custom")),
        "cells_in_window": int(len(window)),
        "profile": data_loader.target_profile(window),
        "profile_physical": data_loader.target_profile(window_phys),
    }
    result["earth_candidates"] = int(len(earth_df))
    z = config.EARTH_ZONES[zone]
    result["zone"] = {"id": zone, "name": z["name"], "full_name": z["full_name"], "country": z["country"],
                      "bbox": z["bbox"]}
    # Post-hoc check against known NASA analog sites (reads the result, never changes it)
    result["validation"] = validation.evaluate(result)
    result["options"] = {"cleaning": cleaning}
    result["cleaning_report"] = {
        "profile": cleaning, "name": cleaning_mod.PROFILES[cleaning]["name"],
        "summary": cleaning_mod.PROFILES[cleaning]["summary"],
        "uncertainty_penalty": (config.SIMILARITY["uncertainty_penalty"]
                                if cleaning_mod.PROFILES[cleaning]["engine"]["uncertainty_penalty"] is None
                                else cleaning_mod.PROFILES[cleaning]["engine"]["uncertainty_penalty"]),
        "target": target_report, "earth": earth_report,
    }
    return result
