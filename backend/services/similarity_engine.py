#############################################################################
# SIMILARITY ENGINE  (weighted, explainable, quality-aware)
#
# Why this file exists:
#   Scientific core of the application: how similar is each Atacama cell to
#   a selected Mars or Moon target?
#
# DATA ROLES (strict - never mixed):
#   - scoring / ranking     -> HARMONIZED + NORMALIZED data (0-1, same scale)
#   - explanation in units  -> HARMONIZED physical data (K, degrees, m)
#   - exact location        -> EARTH PROCESSED data (~1 km), via refinement.py
#
# Algorithm:
#   1. Target profile  t_f = mean normalized value of feature f over the cells
#                      within `window_km` of the target.
#   2. Usable features = weighted features (config.SIMILARITY) that exist on
#                      BOTH sides; `elevation` is excluded (different reference
#                      surface on each body).
#   3. Effective weight per Earth cell:
#        w_f * (1 - p * u_target_f) * (1 - p * u_earth_f)
#      u = share of values flagged uncertain (estimated temperature, proxy
#      albedo...), p = uncertainty_penalty. Uncertain data counts less.
#   4. Distance  d = sqrt( sum w (x_f - t_f)^2 / sum w )   in [0, 1]
#      Score     = 100 * (1 - d)       (100 = identical normalized profile)
#   5. Confidence = usable effective weight / total nominal weight: how much
#      of the planned evidence was actually available and trustworthy.
#   6. Ranking: best scores, keeping regions >= min_separation_km apart so the
#      top 10 are 10 different places, not 10 neighbouring cells.
#   7. Explanation: each feature's share of the distance, physical values of
#      target and Earth cell, features that match best / differ most.
#
# Input / output contract (used by routes/similarity_routes.py and app.js):
#   compute(SimilarityRequest) -> dict with
#     score, confidence, ranking[], comparison[], explanation, map[], method
#
# Future extension: user-adjustable weights (pass them in SimilarityRequest),
# more features (they join automatically when Earth data exists).
#############################################################################
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from services import refinement
from utils import config

ENGINE_STATUS = "ready"
ENGINE_MESSAGE = "Weighted similarity engine (normalized harmonized data, ~11 km cells)"

LABELS = {f: f.replace("_", " ") for f in config.FEATURES}


@dataclass
class SimilarityRequest:
    body: str                       # "mars" | "moon"
    location: str                   # target name
    target_window: pd.DataFrame     # role 1: normalized cells around the target
    earth: pd.DataFrame             # role 1: normalized Atacama cells
    target_window_physical: pd.DataFrame | None = None   # role 2
    earth_physical: pd.DataFrame | None = None           # role 2
    earth_processed: pd.DataFrame | None = None          # role 3
    rover_mode: bool = False        # mission planner: only propose rover-accessible regions
    max_slope: float | None = None  # slope limit (deg) for accessibility + exact point
    uncertainty_penalty: float | None = None  # None = config value; 0 = flags ignored (cleaning "raw")


#############################################
# HELPERS
#############################################
def _flag_mask(names: list[str]) -> int:
    mask = 0
    for n in names:
        mask |= config.FLAG_BITS[n]
    return mask


def _uncertain(flags: pd.Series | np.ndarray, feature: str) -> np.ndarray:
    """Boolean per row: value of `feature` is flagged as uncertain."""
    names = config.SIMILARITY["uncertainty_bits"].get(feature, [])
    if not names:
        return np.zeros(len(flags), bool)
    return (np.asarray(flags) & _flag_mask(names)) != 0


def _haversine_km(lat1, lon1, lat2, lon2, radius_m=config.BODY_RADIUS_M["earth"]) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat, dlon = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radius_m / 1000 * math.asin(math.sqrt(a))


def _key(df: pd.DataFrame) -> pd.MultiIndex:
    """(lat, lon) key rounded like the CSV files, to join normalized and physical rows."""
    return pd.MultiIndex.from_arrays([df["latitude"].round(4), df["longitude"].round(4)])


def _num(x, digits=4):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) or pd.isna(x) else round(float(x), digits)


#############################################
# STEP 1-2: TARGET PROFILE + USABLE FEATURES
#############################################
def target_profile(window: pd.DataFrame) -> tuple[dict, dict]:
    """Mean normalized value per feature, and share of uncertain values per feature."""
    profile = {f: _num(window[f].mean()) for f in config.FEATURES}
    uncertainty = {f: float(_uncertain(window[config.QUALITY_COLUMN], f).mean()) if len(window) else 0.0
                   for f in config.FEATURES}
    return profile, uncertainty


def usable_features(profile: dict, earth: pd.DataFrame) -> tuple[list[str], dict]:
    """Features used for scoring, and the reason each other feature is skipped."""
    used, skipped = [], {}
    for f in config.FEATURES:
        if f in config.SIMILARITY["excluded"]:
            skipped[f] = "excluded: " + config.SIMILARITY["excluded"][f]
        elif f not in config.SIMILARITY["weights"]:
            skipped[f] = "no weight configured"
        elif profile[f] is None:
            skipped[f] = "no data at the target"
        elif earth[f].notna().sum() == 0:
            skipped[f] = "no Earth data yet"
        else:
            used.append(f)
    return used, skipped


#############################################
# STEP 3-5: SCORE EVERY EARTH CELL
# Output: DataFrame aligned with `earth` -> score, confidence, n_features,
#         contrib_<feature> (share of the distance, 0-1)
#############################################
def score_cells(earth: pd.DataFrame, profile: dict, target_unc: dict, used: list[str],
                penalty: float | None = None) -> pd.DataFrame:
    s = config.SIMILARITY
    p = s["uncertainty_penalty"] if penalty is None else penalty
    nominal_total = sum(w for f, w in s["weights"].items() if f not in s["excluded"])
    n = len(earth)
    num, den, count = np.zeros(n), np.zeros(n), np.zeros(n, int)
    parts = {}
    for f in used:
        x = earth[f].to_numpy(dtype=float)
        valid = np.isfinite(x)
        w = s["weights"][f] * (1 - p * target_unc[f]) * (1 - p * _uncertain(earth[config.QUALITY_COLUMN], f))
        w = np.where(valid, w, 0.0)
        sq = np.where(valid, (x - profile[f]) ** 2, 0.0)
        parts[f] = w * sq
        num += parts[f]
        den += w
        count += valid
    with np.errstate(invalid="ignore", divide="ignore"):
        dist = np.sqrt(num / den)
        out = pd.DataFrame({"score": 100 * (1 - dist), "confidence": den / nominal_total, "n_features": count},
                           index=earth.index)
        for f in used:
            out[f"contrib_{f}"] = np.where(num > 0, parts[f] / num, 0.0)
    # Missing-data bias guard: fewer features = fewer differences = artificially high score.
    needed = len(used) if s.get("require_all_features", True) else s["min_shared_features"]
    out.loc[out["n_features"] < needed, "score"] = np.nan
    return out


#############################################
# STEP 6: RANKING WITH SPATIAL SEPARATION
# `eligible` (bool Series) restricts which cells may be proposed, e.g. the
# rover-accessible filter. It never changes any score.
#############################################
def rank(earth: pd.DataFrame, scores: pd.DataFrame, eligible: pd.Series | None = None) -> list[int]:
    s = config.SIMILARITY
    candidates = scores["score"].dropna()
    if eligible is not None:
        candidates = candidates[eligible.reindex(candidates.index).fillna(False).astype(bool)]
    order = candidates.sort_values(ascending=False).index
    chosen: list[int] = []
    for idx in order:
        lat, lon = earth.at[idx, "latitude"], earth.at[idx, "longitude"]
        if all(_haversine_km(lat, lon, earth.at[j, "latitude"], earth.at[j, "longitude"]) >= s["min_separation_km"]
               for j in chosen):
            chosen.append(idx)
        if len(chosen) == s["top_n"]:
            break
    return chosen


#############################################
# STEP 7: EXPLANATION (physical values come from role-2 data only)
#############################################
def compare(idx: int, earth: pd.DataFrame, scores: pd.DataFrame, profile: dict, used: list[str],
            skipped: dict, target_phys: dict, earth_phys_row: pd.Series | None) -> list[dict]:
    rows = []
    for f in config.FEATURES:
        e_norm = earth.at[idx, f]
        rows.append({
            "feature": f, "label": LABELS[f], "units": config.FEATURE_UNITS[f],
            "status": "used" if f in used else skipped.get(f, "not used"),
            "target_normalized": profile[f], "earth_normalized": _num(e_norm),
            "difference_normalized": _num(abs(e_norm - profile[f])) if f in used and pd.notna(e_norm) else None,
            "share_of_distance_pct": _num(100 * scores.at[idx, f"contrib_{f}"], 1) if f in used else None,
            "target_value": _num(target_phys.get(f), 3),
            "earth_value": _num(earth_phys_row[f], 3) if earth_phys_row is not None else None,
        })
    return rows


def explain(comparison: list[dict]) -> dict:
    used = [c for c in comparison if c["status"] == "used" and c["difference_normalized"] is not None]
    by_diff = sorted(used, key=lambda c: c["difference_normalized"])

    def phrase(c):
        u = f" {c['units']}" if c["units"] else ""
        if c["target_value"] is None or c["earth_value"] is None:
            return c["label"]
        return f"{c['label']} (target {c['target_value']:.3g}{u}, Earth {c['earth_value']:.3g}{u})"

    return {"matches": [phrase(c) for c in by_diff[:2]],
            "differs": [phrase(c) for c in by_diff[::-1][:2]],
            "not_compared": [f"{c['label']}: {c['status']}" for c in comparison if c["status"] != "used"]}


#############################################
# MAIN ENTRY POINT
#############################################
def compute(req: SimilarityRequest) -> dict:
    profile, target_unc = target_profile(req.target_window)
    used, skipped = usable_features(profile, req.earth)
    if len(used) < config.SIMILARITY["min_shared_features"]:
        return {"status": "error", "message": f"Only {len(used)} comparable features (need "
                f"{config.SIMILARITY['min_shared_features']}).", "score": None, "ranking": [], "comparison": [],
                "map": []}

    penalty = config.SIMILARITY["uncertainty_penalty"] if req.uncertainty_penalty is None else req.uncertainty_penalty
    scores = score_cells(req.earth, profile, target_unc, used, penalty)
    cell_deg = float(np.median(np.diff(np.sort(req.earth["latitude"].unique()))))

    # ------------------------------------------------------------------
    # MISSION PLANNER FILTER (role 3, Earth processed 1 km data):
    # share of each region's land that a rover can drive (slope <= max_slope).
    # Applied only to WHICH regions are proposed - scores are unchanged.
    # ------------------------------------------------------------------
    rover = config.ROVER
    max_slope = req.max_slope if req.max_slope is not None else rover["default_max_slope_deg"]
    access = (refinement.accessibility_by_cell(req.earth, cell_deg, req.earth_processed, max_slope)
              if req.earth_processed is not None else None)
    eligible = (access >= rover["min_accessible_fraction"]) if (req.rover_mode and access is not None) else None
    top = rank(req.earth, scores, eligible)

    # role-2 lookups (physical units) for explanation only
    target_phys = ({f: req.target_window_physical[f].mean() for f in config.FEATURES}
                   if req.target_window_physical is not None else {})
    earth_phys = None
    if req.earth_physical is not None:
        earth_phys = req.earth_physical.set_index(_key(req.earth_physical))
    earth_keys = _key(req.earth)

    ranking = []
    for r, idx in enumerate(top, start=1):
        phys_row = earth_phys.loc[earth_keys[req.earth.index.get_loc(idx)]] if earth_phys is not None else None
        comparison = compare(idx, req.earth, scores, profile, used, skipped, target_phys, phys_row)
        lat, lon = float(req.earth.at[idx, "latitude"]), float(req.earth.at[idx, "longitude"])
        refined = (refinement.refine(lat, lon, cell_deg, target_phys, req.earth_processed, max_slope)
                   if req.earth_processed is not None else None)
        ranking.append({
            "rank": r, "cell_id": int(idx), "lat": round(lat, 4), "lon": round(lon, 4),
            "region": {"lat_min": round(lat - cell_deg / 2, 4), "lat_max": round(lat + cell_deg / 2, 4),
                       "lon_min": round(lon - cell_deg / 2, 4), "lon_max": round(lon + cell_deg / 2, 4)},
            "score": _num(scores.at[idx, "score"], 1),
            "confidence": _num(scores.at[idx, "confidence"], 2),
            "accessible_pct": _num(100 * access.at[idx], 0) if access is not None else None,
            "comparison": comparison, "explanation": explain(comparison), "refined": refined,
        })

    best = ranking[0] if ranking else None
    valid = scores["score"].notna()

    # ------------------------------------------------------------------
    # MAP CELLS (one entry per Atacama cell) for the interactive map + radar:
    #   score  -> colour            (role 1, normalized)
    #   values -> radar axes 0-1    (role 1, same scale as the score)
    #   physical -> tooltips in K/deg/m (role 2, explanation only)
    # ------------------------------------------------------------------
    # Column arrays instead of per-row pandas lookups (1,200 cells x 6 features).
    def col(a, digits=3):
        return [None if not np.isfinite(v) else float(v) for v in np.round(np.asarray(a, dtype=float), digits)]

    n_cells = len(req.earth)
    lat_c, lon_c = col(req.earth["latitude"], 4), col(req.earth["longitude"], 4)
    score_c = col(scores["score"], 1)
    access_c = col(access.to_numpy(), 2) if access is not None else [None] * n_cells
    norm_c = {f: col(req.earth[f]) for f in used}
    phys_aligned = earth_phys.reindex(earth_keys) if earth_phys is not None else None
    phys_c = {f: col(phys_aligned[f]) for f in used} if phys_aligned is not None else None
    map_cells = []
    for k in range(n_cells):
        cell = {"lat": lat_c[k], "lon": lon_c[k], "score": score_c[k], "accessible": access_c[k],
                "values": {f: norm_c[f][k] for f in used}}
        if phys_c is not None:
            cell["physical"] = {f: phys_c[f][k] for f in used}
        map_cells.append(cell)
    return {
        "status": ENGINE_STATUS, "message": ENGINE_MESSAGE,
        "score": best["score"] if best else None,
        "confidence": best["confidence"] if best else None,
        "ranking": ranking,
        "comparison": best["comparison"] if best else [],
        "earth_profile": {c["feature"]: c["earth_normalized"] for c in best["comparison"]} if best else {},
        "explanation": best["explanation"] if best else {},
        "map": map_cells,
        "target_values": {f: profile[f] for f in used},                              # radar, role 1
        "target_physical": {f: _num(target_phys.get(f), 3) for f in used},          # tooltips, role 2
        "map_cell_deg": cell_deg,
        "method": {
            "features_used": used, "features_skipped": skipped,
            "weights": {f: config.SIMILARITY["weights"][f] for f in used},
            "target_uncertainty": {f: round(target_unc[f], 2) for f in used},
            "uncertainty_penalty": penalty,
            "cells_scored": int(valid.sum()),
            "rover": {"enabled": bool(req.rover_mode), "max_slope_deg": max_slope,
                      "min_accessible_fraction": rover["min_accessible_fraction"],
                      "eligible_regions": int(eligible.sum()) if eligible is not None else None,
                      "source": "Earth processed data (1 km cells, mean of 30 m NASADEM slopes)"},
            "score_distribution": {"min": _num(scores["score"].min(), 1), "median": _num(scores["score"].median(), 1),
                                   "max": _num(scores["score"].max(), 1)},
        },
    }
