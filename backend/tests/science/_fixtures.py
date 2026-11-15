"""SYNTHETIC ENGINEERING FIXTURES — not NASA data, not scientific validation.

Values are invented to exercise arithmetic, gating and lineage. Records that
say data_status="measured" exist only to drive the measured code path; their
provenance_id and URLs mark them as engineering fixtures.
"""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for p in (ROOT / "backend", ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

TAG = "SYNTHETIC-ENGINEERING-FIXTURE"
TARGET_ID = "eng-mars-target"
TARGET_BBOX = [137.3, -4.7, 137.5, -4.5]


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def evidence(eid, feature, site_id, body, value, unit, product, scale=100.0, period=("2020-01-01T00:00:00Z", "2020-12-31T23:59:59Z"),
             qa="ACCEPT", status="measured", kind="derived_measurement", checksum_seed=None, bbox=None):
    seed = checksum_seed or (product + ":" + site_id)
    return {
        "schema_version": "1.0", "evidence_id": eid, "feature_id": feature, "site_id": site_id, "body": body,
        "geometry": {"type": "bbox", "coordinates": bbox or ([-116.9, 35.1, -116.8, 35.2] if body == "Earth" else TARGET_BBOX),
                     "crs": "EPSG:4326" if body == "Earth" else "IAU_2015:49900"},
        "value": value, "unit": unit, "source_product": product, "source_granule_id": f"{TAG}-{product}-{site_id}",
        "source_url": f"https://example.invalid/{TAG}/{product}/{site_id}",
        "source_checksum": sha(seed), "source_asset_ids": [f"asset-{product}-{site_id}"],
        "observation_period": {"start": period[0], "end": period[1]},
        "spatial_resolution_m": 30.0 if body == "Earth" else 463.0, "analysis_scale_m": scale,
        "quality_flags": [], "valid_coverage_fraction": 0.98,
        "uncertainty": {"kind": "unknown", "low": None, "high": None, "standard_deviation": None, "basis": TAG},
        "processing_version": "fixture/1", "provenance_id": TAG, "evidence_kind": kind if value is not None else "unavailable",
        "data_status": status, "missing_reason": None if value is not None else "fixture missing", "qa_status": qa,
    }


# feature -> (weight, tolerance, required, unit, product, target value)
FEATURES = {
    "slope_deg": (0.5, 10.0, True, "degree", "SRTMGL1.003", 5.0),
    "roughness_m": (0.3, 2.0, False, "m", "SRTMGL1.003", 1.0),
    "local_relief_m": (0.2, 200.0, False, "m", "SRTMGL1.003", 300.0),
}
TARGET_PRODUCT = "MOLA_MEGDR"

# Earth candidate sites: id -> (lon, lat, cost, days, access, {feature: value})
SITES = {
    "GOOD": (-116.85, 35.15, 300, 4, "pass", {"slope_deg": 6.0, "roughness_m": 1.2, "local_relief_m": 320.0}),
    "SLOPE_ONLY": (-116.70, 35.30, 200, 3, "pass", {"slope_deg": 5.0, "roughness_m": 4.0, "local_relief_m": 700.0}),
    "ROUGH_ONLY": (-116.60, 35.40, 250, 3, "pass", {"slope_deg": 13.0, "roughness_m": 1.0, "local_relief_m": 300.0}),
    "NEG_CONTROL": (-116.50, 35.50, 100, 2, "pass", {"slope_deg": 40.0, "roughness_m": 9.0, "local_relief_m": 2500.0}),
}


def build(data_status="measured", sites=None, features=None, budget=None, max_sites=2):
    features = features or FEATURES
    sites = sites or SITES
    mission_features = {f: {"unit": u, "weight": w, "tolerance": t, "required": r}
                        for f, (w, t, r, u, _p, _v) in features.items()}
    target_obs, records = {}, []
    for f, (_w, _t, _r, u, _p, v) in features.items():
        eid = f"ev-target-{f}"
        target_obs[f] = {"value": v, "unit": u, "source_id": eid}
        records.append(evidence(eid, f, TARGET_ID, "Mars", v, u, TARGET_PRODUCT, status=data_status))
    site_rows = []
    for sid, (lon, lat, cost, days, access, values) in sites.items():
        obs = {}
        for f, v in values.items():
            u, product = features[f][3], features[f][4]
            eid = f"ev-{sid}-{f}"
            obs[f] = {"value": v, "unit": u, "source_id": eid}
            records.append(evidence(eid, f, sid, "Earth", v, u, product, status=data_status))
        site_rows.append({"id": sid, "name": f"{TAG} {sid}", "longitude": lon, "latitude": lat, "access": access,
                          "cost": cost, "days": days, "observations": obs, "body": "Earth",
                          "coordinate_system": "WGS84_lonlat"})
    location = {"id": TARGET_ID, "body": "Mars", "coordinate_system": "Mars_planetocentric_east_180", "bbox": TARGET_BBOX}
    request = {
        "schema_version": "1.0", "data_status": data_status,
        "mission": {"id": "eng-fixture-mission", "features": mission_features, "min_coverage": 0.6,
                    "max_sites": max_sites, "budget": budget, "max_days": None, "allow_unknown_access": False,
                    "cost_penalty": 0.1, "redundancy_penalty": 0.05, "exclude_portfolios": [],
                    "mode": "custom", "start_trigger": "user_request",
                    "scope": {"locations": [copy.deepcopy(location)], "compare_with": ["Earth"]}},
        "sites": site_rows,
        "target_profiles": [{"body": "Mars", "location": copy.deepcopy(location), "observations": target_obs}],
    }
    return request, records
