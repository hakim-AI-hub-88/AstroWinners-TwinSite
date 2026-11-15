#############################################################################
# DATA CLEANING PROFILES
#
# Why this file exists:
#   The harmonized datasets carry a `quality_flags` bitmask that says which
#   values were estimated, proxied or gap-filled (config.FLAG_BITS, documented
#   in data_ready/harmonized/validation_report.md). This module turns those
#   flags (plus physical range checks and robust statistics) into explicit,
#   reproducible cleaning profiles that the user can choose for a mission or
#   for a dataset download.
#
# Profiles (id -> behaviour):
#   raw       no cleaning; the published values exactly. In the similarity
#             engine the flags are also ignored (no down-weighting).
#   standard  DEFAULT. The frame is returned unchanged (same object): the
#             engine down-weights flagged values and does not score cells that
#             miss a feature. Reproduces the historical scores exactly.
#   strict    masks values whose flag says "estimated" or "proxy", drops cells
#             flagged as water or gap-filled, and masks values outside the
#             physical range of the feature.
#   robust    strict + per-feature median/MAD outlier rejection
#             (|robust z| > 3.5, Iglewicz & Hoaglin 1993).
#
# Contract (docs/INTEGRATION_SPEC.md):
#   apply(df, profile, features=None, scale="normalized") -> (clean_df, report)
#   report = {profile, rows_in, rows_out, rows_complete, steps:[{step, label,
#             removed, masked, detail}], per_feature:{f:{removed, nulls}}}
#     removed = rows dropped by the step, masked = values set to NaN.
#
# Design rules:
#   - Pure pandas / numpy, deterministic, never modifies the input frame
#     (the loaders return shared caches).
#   - Flags concern ONE feature (estimated day temperature, proxy albedo...),
#     so they mask that feature's value, never the whole row; only cell-level
#     flags (water, gap-filled) remove rows. Row index is kept (the engine uses
#     it as cell id).
#   - TEMP_FIXED_LOCAL_TIME and COARSE_SOURCE are kept by every profile: they
#     describe an observation geometry / source resolution, not an invented
#     value (TEMP_FIXED_LOCAL_TIME is set on 1,199 of 1,200 Atacama cells:
#     MODIS overpasses at ~10:30 / 22:30 local time).
#############################################################################
from __future__ import annotations

import numpy as np
import pandas as pd

from utils import config

DEFAULT_PROFILE = "standard"
MAD_Z_THRESHOLD = 3.5            # Iglewicz & Hoaglin modified z-score cut-off
MAD_MIN_VALUES = 10              # robust statistics need a minimum sample

# Physical validity range of each feature (units of config.FEATURE_UNITS). Generous bounds that
# no real Earth / Mars / Moon surface value crosses (Olympus Mons 21.1 km, lunar night ~20 K).
PHYSICAL_RANGES = {
    "elevation": (-11_500.0, 22_000.0), "slope": (0.0, 90.0), "roughness": (0.0, 10_000.0),
    "relief": (0.0, 30_000.0), "temperature_day": (1.0, 450.0), "temperature_night": (1.0, 450.0),
    "albedo": (0.0, 1.0), "thermal_inertia": (0.0, 3_000.0), "mineral_index": (0.0, 100.0),
}
NORMALIZED_RANGE = (0.0, 1.0)

# Feature-level flags masked by strict / robust (flag -> features it concerns)
FEATURE_FLAGS = {
    "TEMP_DAY_ESTIMATED": ["temperature_day"],
    "TEMP_NIGHT_ESTIMATED": ["temperature_night"],
    "ALBEDO_PROXY": ["albedo"],
}
# Cell-level flags: the whole row is removed by strict / robust
ROW_FLAGS = ["WATER", "GAP_FILLED"]
# Flags kept by every profile (documented, never removed)
KEPT_FLAGS = {
    "TEMP_FIXED_LOCAL_TIME": "observation at a fixed local time (e.g. MODIS ~10:30 / 22:30), not an estimate",
    "COARSE_SOURCE": "one input product is coarser than the cell (e.g. NASA POWER 1 deg albedo)",
}

FLAG_MEANINGS = {
    "TEMP_DAY_ESTIMATED": "Daytime temperature modelled, not measured (Mars heat model, Moon latitude law)",
    "TEMP_NIGHT_ESTIMATED": "Night-time temperature modelled or a constant fallback",
    "TEMP_FIXED_LOCAL_TIME": "Temperature observed at a fixed local time instead of the diurnal extreme",
    "GAP_FILLED": "Cell value filled from neighbours in the source pipeline (QA gap filling)",
    "ALBEDO_PROXY": "Albedo derived from a proxy (LROC WAC 643 nm reflectance rescaled), not bolometric",
    "COARSE_SOURCE": "At least one input product is coarser than the ~11 km cell",
    "WATER": "Cell contains open water (Earth only): not a planetary terrain analog",
}

#############################################
# PROFILE CATALOGUE (served by GET /api/data/cleaning)
#############################################
PROFILES = {
    "raw": {
        "name": "Raw",
        "summary": "Published values exactly as delivered; quality flags ignored.",
        "description": "No cleaning at all. Use it to audit provenance or to reproduce third-party processing. "
                       "In a mission the engine also ignores quality flags (no down-weighting).",
        "engine": {"uncertainty_penalty": 0.0},
        "steps": [],
    },
    "standard": {
        "name": "Standard",
        "summary": "Default engine behaviour: flagged values count less, incomplete cells are not scored.",
        "description": "Values are not modified. The similarity engine multiplies the weight of a flagged value "
                       "by (1 - 0.3) and only scores cells that have every compared feature.",
        "engine": {"uncertainty_penalty": None},
        "steps": [
            {"id": "flag_weighting", "label": "Down-weight flagged values",
             "description": "Estimated temperatures, fixed-local-time temperatures and proxy albedo keep their value "
                            "but weigh 30 % less in the score."},
            {"id": "incomplete_cells", "label": "Do not score incomplete cells",
             "description": "Cells missing a compared feature stay in the data but receive no score "
                            "(a missing value would otherwise look like a perfect match)."},
        ],
    },
    "strict": {
        "name": "Strict",
        "summary": "Measured values only: estimated / proxy values masked, water and gap-filled cells removed.",
        "description": "Removes everything that was not directly measured, then checks every value against its "
                       "physical range. Fewer features may remain comparable (e.g. Mars temperatures are modelled).",
        "engine": {"uncertainty_penalty": None},
        "steps": [
            {"id": "invalid_coordinates", "label": "Drop invalid coordinates",
             "description": "Rows with missing latitude / longitude or outside -90..90 / -180..180 are removed."},
            {"id": "row_flags", "label": "Drop water and gap-filled cells",
             "description": "Cells flagged WATER (64) or GAP_FILLED (8) are removed."},
            {"id": "estimated_values", "label": "Mask estimated and proxy values",
             "description": "temperature_day where TEMP_DAY_ESTIMATED (1), temperature_night where "
                            "TEMP_NIGHT_ESTIMATED (2), albedo where ALBEDO_PROXY (16) become missing."},
            {"id": "physical_range", "label": "Mask out-of-range values",
             "description": "Values outside the physical range of the feature become missing "
                            "(normalized data: outside 0-1)."},
        ],
    },
    "robust": {
        "name": "Robust",
        "summary": "Strict + statistical outlier rejection (median / MAD, |z| > 3.5).",
        "description": "Applies every strict step, then masks values whose modified z-score "
                       "0.6745 (x - median) / MAD exceeds 3.5 within the selected data. Features with "
                       "MAD = 0 or fewer than 10 values are left untouched.",
        "engine": {"uncertainty_penalty": None},
        "steps": [],   # filled below (strict steps + outliers)
    },
}
PROFILES["robust"]["steps"] = PROFILES["strict"]["steps"] + [
    {"id": "mad_outliers", "label": "Mask robust outliers",
     "description": f"Per feature: |0.6745 (x - median) / MAD| > {MAD_Z_THRESHOLD} becomes missing."},
]
PROFILE_IDS = list(PROFILES)


class CleaningError(ValueError):
    """Unknown profile or invalid input."""


def validate_profile(profile) -> str:
    p = str(profile or DEFAULT_PROFILE).strip().lower()
    if p not in PROFILES:
        raise CleaningError(f"Unknown cleaning profile '{profile}'. Choose one of {PROFILE_IDS}.")
    return p


def catalogue() -> dict:
    """JSON description of every profile (GET /api/data/cleaning)."""
    return {
        "default": DEFAULT_PROFILE,
        "profiles": [{"id": pid, "name": p["name"], "summary": p["summary"], "description": p["description"],
                      "steps": p["steps"], "engine": p["engine"]} for pid, p in PROFILES.items()],
        "flags": [{"name": n, "bit": b, "meaning": FLAG_MEANINGS[n],
                   "strict_action": ("mask " + ", ".join(FEATURE_FLAGS[n]) if n in FEATURE_FLAGS
                                     else "drop row" if n in ROW_FLAGS else "keep (" + KEPT_FLAGS.get(n, "") + ")")}
                  for n, b in config.FLAG_BITS.items()],
        "physical_ranges": {f: {"min": lo, "max": hi, "units": config.FEATURE_UNITS.get(f, "")}
                            for f, (lo, hi) in PHYSICAL_RANGES.items()},
        "mad_z_threshold": MAD_Z_THRESHOLD,
    }


#############################################
# FLAG DECODING
#############################################
def decode_flags(flags) -> dict:
    """Count of rows carrying each flag bit: {name: n}."""
    arr = np.asarray(flags, dtype=np.int64) if len(flags) else np.zeros(0, np.int64)
    return {n: int(((arr & b) != 0).sum()) for n, b in config.FLAG_BITS.items()}


def _bits(names) -> int:
    m = 0
    for n in names:
        m |= config.FLAG_BITS[n]
    return m


#############################################
# MAIN ENTRY POINT
# Input : df with latitude, longitude, features, quality_flags
#         profile  raw | standard | strict | robust
#         features columns to clean (default: every schema feature present)
#         scale    "normalized" (0-1 files) | "physical" (harmonized / processed units)
# Output: (clean_df, report). For raw / standard clean_df IS df (no copy).
#############################################
def apply(df: pd.DataFrame, profile: str = DEFAULT_PROFILE, features=None,
          scale: str = "normalized") -> tuple[pd.DataFrame, dict]:
    profile = validate_profile(profile)
    if scale not in ("normalized", "physical"):
        raise CleaningError("scale must be 'normalized' or 'physical'")
    feats = [f for f in (features or config.FEATURES) if f in df.columns]
    qcol = config.QUALITY_COLUMN
    flags = (df[qcol].fillna(0).astype(np.int64).to_numpy() if qcol in df.columns
             else np.zeros(len(df), np.int64))
    valid_before = {f: int(df[f].notna().sum()) for f in feats}
    steps: list[dict] = []

    if profile in ("raw", "standard"):
        out = df
        if profile == "standard":
            fw = {}
            for f, names in config.SIMILARITY["uncertainty_bits"].items():
                if f in feats:
                    fw[f] = int((((flags & _bits(names)) != 0) & df[f].notna().to_numpy()).sum())
            steps.append({"step": "flag_weighting", "label": PROFILES["standard"]["steps"][0]["label"],
                          "removed": 0, "masked": 0,
                          "detail": {"down_weighted_values": fw,
                                     "weight_factor": round(1 - config.SIMILARITY["uncertainty_penalty"], 2)}})
            incomplete = int(df[feats].isna().any(axis=1).sum()) if feats else 0
            steps.append({"step": "incomplete_cells", "label": PROFILES["standard"]["steps"][1]["label"],
                          "removed": 0, "masked": 0,
                          "detail": {"rows_missing_a_feature": incomplete,
                                     "note": "kept in the data; the engine scores only features present at the target "
                                             "and every cell must have all of them"}})
        return out, _report(profile, df, out, feats, valid_before, steps, scale)

    # ---- strict / robust: work on a copy (never touch the shared cache) ----
    out = df.copy()
    keep = np.ones(len(out), bool)

    # 1. invalid coordinates
    lat = pd.to_numeric(out.get("latitude"), errors="coerce").to_numpy(dtype=float)
    lon = pd.to_numeric(out.get("longitude"), errors="coerce").to_numpy(dtype=float)
    bad = ~(np.isfinite(lat) & np.isfinite(lon) & (np.abs(lat) <= 90) & (np.abs(lon) <= 180))
    steps.append({"step": "invalid_coordinates", "label": "Drop invalid coordinates",
                  "removed": int((bad & keep).sum()), "masked": 0, "detail": {}})
    keep &= ~bad

    # 2. cell-level flags (water, gap-filled)
    per_flag = {}
    for name in ROW_FLAGS:
        hit = ((flags & config.FLAG_BITS[name]) != 0) & keep
        per_flag[name] = int(hit.sum())
        keep &= ~hit
    steps.append({"step": "row_flags", "label": "Drop water and gap-filled cells",
                  "removed": sum(per_flag.values()), "masked": 0, "detail": {"rows_by_flag": per_flag}})

    # 3. feature-level flags (estimated / proxy values)
    masked_by_flag = {}
    for name, fs in FEATURE_FLAGS.items():
        hit = (flags & config.FLAG_BITS[name]) != 0
        for f in fs:
            if f not in feats:
                continue
            m = hit & keep & out[f].notna().to_numpy()
            masked_by_flag[f"{f} ({name})"] = int(m.sum())
            if m.any():
                out.loc[m, f] = np.nan
    steps.append({"step": "estimated_values", "label": "Mask estimated and proxy values", "removed": 0,
                  "masked": sum(masked_by_flag.values()), "detail": {"values_by_flag": masked_by_flag}})

    # 4. physical range
    masked_range = {}
    for f in feats:
        lo, hi = NORMALIZED_RANGE if scale == "normalized" else PHYSICAL_RANGES.get(f, (-np.inf, np.inf))
        x = out[f].to_numpy(dtype=float)
        m = keep & np.isfinite(x) & ((x < lo) | (x > hi))
        m |= keep & np.isinf(x)
        if m.any():
            out.loc[m, f] = np.nan
        masked_range[f] = int(m.sum())
    steps.append({"step": "physical_range", "label": "Mask out-of-range values", "removed": 0,
                  "masked": sum(masked_range.values()),
                  "detail": {"values_by_feature": masked_range, "scale": scale,
                             "note": "normalized files are clipped to 0-1 by the pipeline, so this step "
                                     "can only fire on physical-unit data" if scale == "normalized" else ""}})

    # 5. robust: median / MAD outliers (on the rows still kept)
    if profile == "robust":
        masked_mad, skipped = {}, {}
        for f in feats:
            x = out[f].to_numpy(dtype=float)
            sel = keep & np.isfinite(x)
            vals = x[sel]
            if len(vals) < MAD_MIN_VALUES:
                skipped[f] = f"fewer than {MAD_MIN_VALUES} values"
                masked_mad[f] = 0
                continue
            med = float(np.median(vals))
            mad = float(np.median(np.abs(vals - med)))
            if mad == 0 or not np.isfinite(mad):
                skipped[f] = "MAD = 0 (too few distinct values, e.g. 1 deg climatology)"
                masked_mad[f] = 0
                continue
            z = np.zeros(len(x))
            z[sel] = 0.6745 * (vals - med) / mad
            m = sel & (np.abs(z) > MAD_Z_THRESHOLD)
            if m.any():
                out.loc[m, f] = np.nan
            masked_mad[f] = int(m.sum())
        steps.append({"step": "mad_outliers", "label": "Mask robust outliers", "removed": 0,
                      "masked": sum(masked_mad.values()),
                      "detail": {"values_by_feature": masked_mad, "skipped": skipped,
                                 "threshold": MAD_Z_THRESHOLD}})

    if not keep.all():
        out = out.loc[keep]
    return out, _report(profile, df, out, feats, valid_before, steps, scale)


def _report(profile, df_in, df_out, feats, valid_before, steps, scale) -> dict:
    per_feature = {}
    for f in feats:
        nulls = int(df_out[f].isna().sum())
        per_feature[f] = {"removed": int(valid_before[f] - (len(df_out) - nulls)), "nulls": nulls,
                          "valid": int(len(df_out) - nulls)}
    present = [f for f in feats if valid_before[f] > 0]       # features with any data at all
    complete = int(df_out[present].notna().all(axis=1).sum()) if present else int(len(df_out))
    return {
        "profile": profile, "name": PROFILES[profile]["name"], "scale": scale,
        "rows_in": int(len(df_in)), "rows_out": int(len(df_out)),
        "rows_removed": int(len(df_in) - len(df_out)),
        "values_masked": int(sum(s.get("masked", 0) for s in steps)),
        "rows_complete": complete, "complete_over": present,
        "steps": steps, "per_feature": per_feature,
    }


def summary(report: dict) -> dict:
    """Compact version of a report (for mission responses)."""
    return {k: report[k] for k in ("profile", "name", "rows_in", "rows_out", "rows_removed", "values_masked",
                                   "rows_complete")}
