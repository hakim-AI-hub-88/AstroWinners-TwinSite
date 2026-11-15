"""Server-owned published evidence. Release remains blocked pending independent C5 review."""
import json
import hashlib
import os
from pathlib import Path
from .contract import validate, digest
from twinsite.science.bridge import request_from_evidence

PAIR = Path(__file__).resolve().parents[1] / "processing/published/g2_feature_pair.json"
DATASET = "zagora-gale-v1"

def load_pair():
    pair = json.loads(PAIR.read_text())
    if pair["data_status"] != "measured":
        raise ValueError("Dataset is not measured")
    for asset in pair["assets"]:
        validate("asset_manifest", asset)
    assets = {a["asset_id"]: a for a in pair["assets"]}
    if len(assets) != len(pair["assets"]):
        raise ValueError("Duplicate assets")
    seen = set()
    for obs in pair["observations"]:
        validate("evidence_observation", obs)
        if obs["data_status"] != "measured" or obs["evidence_kind"] == "synthetic":
            raise ValueError("Synthetic evidence cannot enter measured workflow")
        if obs["evidence_id"] in seen:
            raise ValueError("Duplicate evidence")
        seen.add(obs["evidence_id"])
        sources = [assets.get(a) for a in obs["source_asset_ids"]]
        if not sources or any(a is None for a in sources) or not any(
            a["sha256"] == obs["source_checksum"] and a["source_url"] == obs["source_url"] and
            a["body"] == obs["body"] and a["product_id"] == obs["source_product"] for a in sources):
            raise ValueError("Evidence asset lineage mismatch")
        if obs["value"] is not None and (obs["spatial_resolution_m"] is None or obs["analysis_scale_m"] is None or obs["analysis_scale_m"] < obs["spatial_resolution_m"]):
            raise ValueError("Invalid spatial support")
    pinned = sorted(({"asset_id": a["asset_id"], "sha256": a["sha256"]} for a in pair["assets"]), key=lambda a: a["asset_id"])
    if digest(pinned) != pair["source_snapshot_sha256"]:
        raise ValueError("Published snapshot mismatch")
    return pair

def resolve_request(body):
    if not isinstance(body, dict) or set(body) != {"schema_version", "dataset_id"} or body.get("schema_version") != "1.0" or body.get("dataset_id") != DATASET:
        raise ValueError("Provide schema_version 1.0 and dataset_id zagora-gale-v1 only; arbitrary regions are not integrated")
    pair = load_pair()
    mission = {"id": DATASET + "-" + digest(pair)[:16], "features": {
        "slope_deg": {"unit": "degree", "weight": 0.45, "tolerance": 20, "required": True},
        "roughness_m": {"unit": "m", "weight": 0.35, "tolerance": 6, "required": False},
        "dry_fraction": {"unit": "1", "weight": 0.2, "tolerance": 0.5, "required": False}},
        "min_coverage": 0.65, "max_sites": 1, "budget": None, "max_days": None,
        "allow_unknown_access": False, "mode": "custom", "start_trigger": "user_request", "portfolio_mode": "standalone"}
    target = {"id": "mars-gale-aeolis", "body": "Mars", "coordinate_system": "Mars_planetocentric_east_180", "bbox": [137.25, -4.75, 137.55, -4.45]}
    earth = {"id": "earth-zagora-draa", "name": "Zagora Draa", "longitude": -5.8, "latitude": 30.35,
             "access": "unknown", "cost": None, "days": None}
    mission["scope"] = {"locations": [target, {"id": "zagora-region", "body": "Earth", "coordinate_system": "WGS84_lonlat", "bbox": [-5.95, 30.2, -5.65, 30.5]}], "compare_with": ["Mars"]}
    payload = request_from_evidence(mission, [earth], target, pair["observations"])
    validate("mission_request", payload)
    return payload

def evidence_for(payload):
    expected = resolve_request({"schema_version": "1.0", "dataset_id": DATASET})
    if payload != expected:
        raise ValueError("Measured request does not match server-resolved published snapshot")
    pair = load_pair()
    root = Path(os.environ.get("TWINSITE_SOURCE_DATA_DIR", PAIR.parents[4] / ".runtime/data")).resolve()
    for a in pair["assets"]:
        path = (root / a["object_key"]).resolve()
        if not path.is_relative_to(root) or not path.is_file() or path.stat().st_size != a["byte_size"]:
            raise ValueError("Source bytes missing or wrong size")
        if hashlib.sha256(path.read_bytes()).hexdigest() != a["sha256"]:
            raise ValueError("Source bytes checksum mismatch")
    return pair

AOI_EXTENT_TOLERANCE = 1.25


def extent_mismatches(pair):
    """Compare analysis-block counts per site (same 1852.3 m scale, so counts scale with AOI area).

    Equal angular bounding boxes are not equal areas across bodies; extent-dependent statistics
    such as max-min relief and the sample size behind slope/roughness distributions are then not
    comparable. Reported, never corrected here: fixing it requires matched metric AOIs from C1.
    """
    counts = {}
    for site in pair["sites"]:
        stats = site.get("provenance", {}).get("feature_details", {}).get("local_relief_m", {}).get("stats", {})
        if stats.get("n"):
            counts[site["site_id"]] = stats["n"]
    if len(counts) < 2:
        return ["AOI_EXTENT_UNVERIFIED"]
    ratio = max(counts.values()) / min(counts.values())
    if ratio <= AOI_EXTENT_TOLERANCE:
        return []
    detail = "/".join(f"{k}={v}" for k, v in sorted(counts.items()))
    return [f"AOI_EXTENT_MISMATCH:{ratio:.2f}x({detail} analysis blocks)"]


def sidecar(run, output, pair):
    value = dict(output["science_evidence"])
    value.update(run_id=run["run_id"], assets=pair["assets"], source_snapshot_id=pair["source_snapshot_id"],
                 source_snapshot_sha256=pair["source_snapshot_sha256"], release_action="BLOCK", strict_gate_status="BLOCK")
    value["observations"] = pair["observations"]
    value["blocking_issues"] = sorted(set(value["blocking_issues"] + ["C5_INDEPENDENT_REVIEW_REQUIRED"] +
        [flag for obs in pair["observations"] for flag in obs["quality_flags"] if "MIRROR" in flag] +
        extent_mismatches(pair)))
    value["assumptions"].append("Preset weights and tolerances are scenario assumptions, not measured quantities. Spatial p10-p90 intervals describe variability, not instrument uncertainty.")
    value["assumptions"].append("Earth and Mars areas of interest share an angular size, not a metric area; extent-dependent statistics (relief, distribution sample sizes) are not directly comparable until matched metric AOIs are produced.")
    return value
