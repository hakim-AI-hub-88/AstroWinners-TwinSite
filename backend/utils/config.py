#############################################################################
# CONFIGURATION MODULE
#
# Why this file exists:
#   Every setting of the web application lives here: where the harmonized
#   datasets are, which planetary targets can be selected, which features
#   exist, and how the server starts. Other modules import from here instead
#   of hard-coding paths or names, so changing a setting happens in ONE place.
#
# Data source:
#   The app READS the outputs of the data pipeline (pipeline/data_ready/
#   harmonized/). Nothing is copied: the pipeline stays the single source of
#   truth. Override the folder with the HARMONIZED_DATA_DIR environment var.
#
# Future extension:
#   - add a target  -> append to TARGETS (name + lat/lon)
#   - add a feature -> append to FEATURES once the pipeline produces it
#############################################################################
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# PATHS
# app/backend/utils/config.py -> parents[2] = app/ ; parents[3] = hackathon/
# ---------------------------------------------------------------------------
APP_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = APP_ROOT / "templates"
STATIC_DIR = APP_ROOT / "static"

# Data folder: app/data_ready (copy shipped with the app, so app/ is self-contained),
# falling back to the pipeline output ../pipeline/data_ready. Override: DATA_READY_DIR.
DATA_READY_DIR = Path(os.environ.get(
    "DATA_READY_DIR",
    APP_ROOT / "data_ready" if (APP_ROOT / "data_ready").is_dir() else APP_ROOT.parent / "pipeline" / "data_ready",
)).resolve()

HARMONIZED_DATA_DIR = Path(
    os.environ.get("HARMONIZED_DATA_DIR", DATA_READY_DIR / "harmonized")
).resolve()

#############################################
# DATASET ROLES  (never mix them)
#   1. HARMONIZED + NORMALIZED (0-1) -> similarity calculation ONLY
#   2. HARMONIZED (physical units)   -> explanations / charts ONLY
#   3. EARTH PROCESSED (~1 km)       -> high-resolution refinement ONLY
#############################################
DATASET_FILES = {            # role 1
    "earth": "earth_features_harmonized_normalized.csv.gz",
    "mars": "mars_features_harmonized_normalized.csv.gz",
    "moon": "moon_features_harmonized_normalized.csv.gz",
}
PHYSICAL_FILES = {           # role 2
    "earth": "earth_features_harmonized.csv.gz",
    "mars": "mars_features_harmonized.csv.gz",
    "moon": "moon_features_harmonized.csv.gz",
}
EARTH_PROCESSED_FILE = Path(  # role 3 (0.01 deg Atacama grid from the planetary pipeline)
    os.environ.get("EARTH_PROCESSED_FILE",
                   DATA_READY_DIR / "earth" / "processed" / "earth_features.csv")
).resolve()

# ---------------------------------------------------------------------------
# COMMON FEATURE SCHEMA (identical columns in the three files)
# Values are normalized 0-1 with percentiles shared by Earth, Mars and Moon.
# ---------------------------------------------------------------------------
COORDINATE_COLUMNS = ["latitude", "longitude"]
FEATURES = [
    "elevation", "slope", "roughness", "relief",
    "temperature_day", "temperature_night",
    "albedo", "thermal_inertia", "mineral_index",
]
QUALITY_COLUMN = "quality_flags"

FEATURE_UNITS = {
    "elevation": "m", "slope": "°", "roughness": "m", "relief": "m",
    "temperature_day": "K", "temperature_night": "K", "albedo": "", "thermal_inertia": "TIU",
    "mineral_index": "wt% Fe",
}

# quality_flags bits written by the pipeline (see pipeline/planetary_pipeline/schema.py)
FLAG_BITS = {"TEMP_DAY_ESTIMATED": 1, "TEMP_NIGHT_ESTIMATED": 2, "TEMP_FIXED_LOCAL_TIME": 4,
             "GAP_FILLED": 8, "ALBEDO_PROXY": 16, "COARSE_SOURCE": 32, "WATER": 64}

#############################################
# SIMILARITY ENGINE SETTINGS
#   weights            relative importance (renormalised over usable features).
#                      Terrain has 3 correlated features, so each gets less weight.
#                      thermal_inertia / mineral_index are used automatically as
#                      soon as Earth has data for them (missing today).
#   excluded           elevation: each body uses a different reference surface
#                      (Earth geoid, Mars areoid, Moon sphere) -> not comparable.
#   uncertainty_bits   flags that make a feature value less trustworthy;
#                      its weight is multiplied by (1 - uncertainty_penalty).
#############################################
SIMILARITY = {
    "weights": {"slope": 0.15, "roughness": 0.15, "relief": 0.15, "temperature_day": 0.2,
                "temperature_night": 0.2, "albedo": 0.15, "thermal_inertia": 0.15, "mineral_index": 0.1},
    "excluded": {"elevation": "different reference surface on each body (geoid / areoid / sphere)"},
    "uncertainty_bits": {"temperature_day": ["TEMP_DAY_ESTIMATED", "TEMP_FIXED_LOCAL_TIME"],
                         "temperature_night": ["TEMP_NIGHT_ESTIMATED", "TEMP_FIXED_LOCAL_TIME"],
                         "albedo": ["ALBEDO_PROXY"]},
    "uncertainty_penalty": 0.3,
    "min_shared_features": 4,
    # A cell missing a feature would look MORE similar (fewer differences are summed).
    # So by default only cells with every used feature are scored and ranked.
    "require_all_features": True,
    "top_n": 10,
    "min_separation_km": 25,       # ranked regions must be at least this far apart
}

#############################################
# HIGH-RESOLUTION REFINEMENT (phase 2, Earth processed data, ~1 km)
# Inside each top 11 km region: drop water and steep cells, then pick the 1 km
# cell whose day/night temperatures are closest to the target's (physical K).
# Terrain is NOT re-compared here: 1 km slopes come from 30 m data and are not
# on the same scale as the planetary 3.7 km slopes.
#############################################
REFINEMENT = {"max_slope_deg": 15.0, "exclude_water": True}

#############################################
# MISSION PLANNER - ROVER-ACCESSIBLE FILTER
# A region (~11 km) is "rover-accessible" when at least `min_accessible_fraction`
# of its land 1 km cells have a mean slope <= max_slope_deg (Earth processed data).
# The filter never changes scores: it only decides which regions may be proposed.
# max_slope_deg can be changed by the user between slope_limits.
#############################################
ROVER = {"default_max_slope_deg": 15.0, "slope_limits": (5.0, 30.0), "min_accessible_fraction": 0.5}

# Body radii (m): needed to turn "km around a target" into degrees.
BODY_RADIUS_M = {"earth": 6_371_007.0, "mars": 3_396_000.0, "moon": 1_737_400.0}

# ---------------------------------------------------------------------------
# PLANETARY TARGETS
# Coordinates: planetocentric latitude, east-positive longitude (-180..180),
# the convention used by the harmonized files.
# window_km: radius of the area averaged to build the target "profile".
# ---------------------------------------------------------------------------
TARGETS = {
    "mars": {
        "Jezero Crater": {"lat": 18.38, "lon": 77.58, "window_km": 50,
                          "note": "Perseverance landing site - ancient delta and lake"},
        "Gale Crater": {"lat": -5.40, "lon": 137.80, "window_km": 50,
                        "note": "Curiosity landing site - layered sediments of Mount Sharp"},
    },
    "moon": {
        "Mare Tranquillitatis": {"lat": 8.50, "lon": 31.40, "window_km": 50,
                                 "note": "Apollo 11 region - dark basaltic plains"},
        "Apollo 15": {"lat": 26.13, "lon": 3.63, "window_km": 50,
                      "note": "Hadley Rille - mare / highland boundary"},
    },
}

# ---------------------------------------------------------------------------
# USER-SELECTED REGIONS (interactive Moon / Mars globe, services/analysis.py)
#   A region = a circle of `radius` km around the clicked point (drawn as the
#   enclosing square). It can be analysed only when the data covers it.
# ---------------------------------------------------------------------------
CUSTOM_TARGET = {
    "radius_km_choices": [25, 50, 100],
    "default_radius_km": 50,
    "min_cells": 3,                 # harmonized cells needed inside the region
    "min_comparable_features": 3,   # features shared with the Earth zones (elevation excluded)
    "min_feature_coverage": 0.5,    # a feature counts when >= 50 % of the region's cells have it
    "note": "Region selected on the interactive globe",
}

# ---------------------------------------------------------------------------
# SERVER
# Port 5050 avoids a clash with the other Flask app of the project (flak/, port 5000).
# ---------------------------------------------------------------------------
HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", 5050))
DEBUG = os.environ.get("APP_DEBUG", "0") == "1"


#############################################################################
# AI MISSION ASSISTANT (Groq LLM with tool calling)
#
# Secrets: the API key is read from the environment, or from app/.env
# (KEY=VALUE lines, git-ignored). It never reaches the browser.
# The assistant only explains: every number comes from the analysis tools.
#############################################################################
def _load_dotenv(path: Path) -> None:
    """Minimal .env reader: sets variables that are not already defined."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(APP_ROOT / ".env")

ASSISTANT = {
    "api_key_env": "GROQ_API_KEY",
    "model": os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),   # tool-calling model on Groq
    "temperature": 0.2,                 # low: factual explanations
    "max_tool_rounds": 6,               # tool-call iterations per question
    "max_history_messages": 10,         # previous user/assistant turns kept (sent by the browser)
    "max_question_chars": 1500,
    "max_tool_result_chars": 12000,     # keep tool outputs compact
    "timeout_s": 60,
}


#############################################################################
# EARTH ANALOG ZONES
#   The Atacama stays the default zone (all existing behaviour unchanged).
#   Merzouga - Erg Chebbi (Morocco) was preprocessed by the same pipeline
#   (pipeline/run_pipeline.py --config config_merzouga.yaml + run_zones.py)
#   and normalized on the same common 0-1 scale, so scores are comparable.
#   Each zone has the three data roles: normalized (score), physical
#   (explanation), processed 1 km (rover filter + exact point).
#############################################################################
_PIPELINE_READY = DATA_READY_DIR      # same folder as above (name kept)

EARTH_ZONES = {
    "atacama": {
        "name": "Atacama", "full_name": "Atacama Desert (Chile)", "country": "Chile",
        "normalized": DATASET_FILES["earth"], "physical": PHYSICAL_FILES["earth"],
        "processed": EARTH_PROCESSED_FILE,
        "bbox": {"lat_min": -25.0, "lat_max": -22.0, "lon_min": -70.0, "lon_max": -66.0},
    },
    "merzouga": {
        "name": "Merzouga", "full_name": "Merzouga - Erg Chebbi (Morocco)", "country": "Morocco",
        "normalized": "merzouga_features_harmonized_normalized.csv.gz",
        "physical": "merzouga_features_harmonized.csv.gz",
        "processed": Path(os.environ.get("MERZOUGA_PROCESSED_FILE",
                                         _PIPELINE_READY / "merzouga" / "processed" / "merzouga_features.csv")).resolve(),
        "bbox": {"lat_min": 30.0, "lat_max": 32.0, "lon_min": -5.0, "lon_max": -3.0},
    },
}
DEFAULT_ZONE = "atacama"
