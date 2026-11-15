"""Scoring arithmetic: a byte-compatible port of the ARES 0.4.0 reference.

Kept arithmetically identical (same operations, same order) so the frozen
synthetic request/result fixtures in contracts/examples reproduce exactly.
All quantities use explicit mission units; no unit conversion happens here.

Feature score (engineering similarity heuristic, NOT a probability):
    s_i = max(0, 1 - |x_i - t_i| / tolerance_i)
Weighted coverage C = sum of weights of observed comparable features.
Conservative bound L = sum(w_i * s_i); optimistic bound U = L + (1 - C).
[L, U] are bounds due solely to missing features, not confidence intervals.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math

from .scope import apply_scope, comparison_bodies, contains_bounds, validate_scope


def canonical_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode()).hexdigest()


def finite_number(value, name, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return value


def validate(payload):
    if payload.get("schema_version") != "1.0":
        raise ValueError("schema_version must be 1.0")
    if payload.get("data_status") not in {"synthetic", "measured"}:
        raise ValueError("data_status must identify synthetic or measured input")
    mission = payload["mission"]
    validate_scope(mission)
    if not isinstance(mission.get("id"), str) or not mission["id"]:
        raise ValueError("mission.id must be a nonempty string")
    features = mission["features"]
    if not features or len(features) > 12:
        raise ValueError("provide 1 to 12 feature definitions")
    total_weight = 0.0
    for name, spec in features.items():
        if not isinstance(spec["unit"], str) or not spec["unit"]:
            raise ValueError(f"{name} needs a canonical unit")
        total_weight += finite_number(spec["weight"], f"{name}.weight", 0)
        if finite_number(spec["tolerance"], f"{name}.tolerance", 0) == 0:
            raise ValueError(f"{name}.tolerance must be positive")
        if not isinstance(spec.get("required", False), bool):
            raise ValueError(f"{name}.required must be boolean")
    if total_weight == 0:
        raise ValueError("at least one weight must be positive")
    finite_number(mission["min_coverage"], "min_coverage", 0, 1)
    maximum = mission["max_sites"]
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not 1 <= maximum <= 3:
        raise ValueError("max_sites must be an integer from 1 to 3")
    output_mode = mission.get("portfolio_mode", "both")
    if output_mode not in {"standalone", "combined", "both"}:
        raise ValueError("portfolio_mode must be standalone, combined or both")
    if output_mode == "combined" and maximum < 2:
        raise ValueError("combined portfolios require max_sites of at least 2")
    for key in ("budget", "max_days"):
        if mission.get(key) is not None:
            finite_number(mission[key], key, 0)
    finite_number(mission.get("cost_penalty", 0.1), "cost_penalty", 0, 1)
    finite_number(mission.get("redundancy_penalty", 0.05), "redundancy_penalty", 0, 1)
    if not isinstance(mission.get("allow_unknown_access", False), bool):
        raise ValueError("allow_unknown_access must be boolean")
    profiles = payload.get("target_profiles", [])
    targets = comparison_bodies(mission)
    if not 1 <= len(profiles) <= 12 or {p.get("body") for p in profiles} != set(targets):
        raise ValueError("provide 1 to 12 profiles covering every requested target body")
    anchors = {item["body"]: item for item in mission["scope"]["locations"]}
    seen_profiles = set()
    for profile in profiles:
        body = profile["body"]
        location = profile["location"]
        validate_scope({"mode": "auto", "start_trigger": "user_request", "scope": {"locations": [location]}})
        key = (body, location["id"])
        if key in seen_profiles:
            raise ValueError("target profile locations must be unique within each body")
        seen_profiles.add(key)
        if location["body"] != body:
            raise ValueError("target profile body must match its location")
        anchor = anchors.get(body)
        if anchor:
            if anchor.get("kind", "site") == "zone":
                if not contains_bounds(anchor, location):
                    raise ValueError("target location must lie wholly inside its selected zone")
            elif location != anchor:
                raise ValueError("target profile must resolve to its selected planetary site")
        if set(profile["observations"]) - set(features):
            raise ValueError("target profile contains undefined features")
        for name, observation in profile["observations"].items():
            if observation["unit"] != features[name]["unit"] or not observation.get("source_id"):
                raise ValueError("target observation requires compatible units and source evidence")
            if observation.get("value") is not None:
                finite_number(observation["value"], "target observation")
    sites = payload["sites"]
    if not 0 <= len(sites) <= 12:
        raise ValueError("at most 12 scoped sites are supported (exact enumeration)")
    ids = set()
    for site in sites:
        if not isinstance(site["id"], str) or not site["id"] or site["id"] in ids:
            raise ValueError("site IDs must be unique nonempty strings")
        ids.add(site["id"])
        if site["access"] not in {"pass", "fail", "unknown"}:
            raise ValueError("access must be pass, fail or unknown")
        finite_number(site["longitude"], "longitude", -180, 180)
        finite_number(site["latitude"], "latitude", -90, 90)
        for key in ("cost", "days"):
            if site.get(key) is not None:
                finite_number(site[key], key, 0)
        if set(site["observations"]) - set(features):
            raise ValueError("observation contains an undefined feature")
        for name, observation in site["observations"].items():
            if observation["unit"] != features[name]["unit"]:
                raise ValueError(f"{site['id']}.{name} has an incompatible unit")
            if not isinstance(observation.get("source_id"), str) or not observation["source_id"]:
                raise ValueError(f"{site['id']}.{name} needs source_id")
            if observation.get("value") is not None:
                finite_number(observation["value"], name)
    for excluded in mission.get("exclude_portfolios", []):
        if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
            raise ValueError("excluded portfolios must contain site IDs")
    return payload


def clean(payload):
    """Apply only explicitly declared missing sentinels, retaining a ledger."""
    cleaned, excluded = apply_scope(payload)
    ledger = []
    for site in cleaned.get("sites", []) + [dict(profile, id="target:" + profile["body"])
                                           for profile in cleaned.get("target_profiles", [])]:
        for name, observation in site.get("observations", {}).items():
            sentinel = observation.get("missing_sentinel")
            if sentinel is not None and observation.get("value") == sentinel:
                observation["value"] = None
                observation["missing_reason"] = "declared_source_sentinel"
                ledger.append({"rule": "sentinel_to_null_v1", "site_id": site["id"], "feature": name})
    validate(cleaned)
    return cleaned, excluded, ledger


def expand_comparisons(payload):
    """Equal body priority, then equal location priority within each body."""
    expanded = copy.deepcopy(payload)
    features = payload["mission"]["features"]
    profiles = sorted(payload["target_profiles"], key=lambda item: (item["body"], item["location"]["id"]))
    counts = {body: sum(p["body"] == body for p in profiles) for body in comparison_bodies(payload["mission"])}
    expanded["mission"]["features"] = {}
    criteria = []
    for profile in profiles:
        body = profile["body"]
        for name, spec in features.items():
            key = (body + "/" + name if counts[body] == 1
                   else json.dumps([body, profile["location"]["id"], name], separators=(",", ":")))
            target = profile["observations"].get(name, {})
            expanded["mission"]["features"][key] = dict(
                spec, weight=spec["weight"] / len(counts) / counts[body],
                target=target.get("value"), target_source_id=target.get("source_id"),
                target_body=body, target_location_id=profile["location"]["id"], feature_id=name)
            criteria.append((key, name))
    for site in expanded["sites"]:
        original = site["observations"]
        site["observations"] = {key: copy.deepcopy(original[name]) for key, name in criteria if name in original}
    return expanded


def weights_for(mission):
    total = math.fsum(spec["weight"] for spec in mission["features"].values())
    return {name: spec["weight"] / total for name, spec in mission["features"].items()}


def similarity(value, target, tolerance):
    return max(0.0, 1.0 - abs(value - target) / tolerance)


def score_site(site, mission, weights):
    contributions = {}
    missing = []
    coverage = 0.0
    lower = 0.0
    failures = []
    for name, spec in mission["features"].items():
        observation = site["observations"].get(name)
        if observation is None or observation.get("value") is None or spec.get("target") is None:
            missing.append(name)
            if spec.get("required", False):
                failures.append(f"required feature {name} missing")
            continue
        s = similarity(observation["value"], spec["target"], spec["tolerance"])
        coverage += weights[name]
        lower += weights[name] * s
        contributions[name] = {"similarity": s, "weighted_contribution": weights[name] * s,
                               "value": observation["value"], "unit": observation["unit"],
                               "source_id": observation["source_id"], "target_source_id": spec.get("target_source_id"),
                               "target_value": spec["target"], "target_body": spec.get("target_body"),
                               "target_location_id": spec.get("target_location_id"),
                               "feature_id": spec.get("feature_id", name)}
    if coverage + 1e-12 < mission["min_coverage"]:
        failures.append("insufficient weighted data coverage")
    if site["access"] == "fail":
        failures.append("access constraint failed")
    if site["access"] == "unknown" and not mission.get("allow_unknown_access", False):
        failures.append("access status unknown")
    return {"id": site["id"], "name": site.get("name", site["id"]), "eligible": not failures,
            "body": site["body"], "coordinate_system": site["coordinate_system"],
            "failures": failures, "coverage": coverage, "observed_similarity": lower / coverage if coverage else None,
            "lower_utility": lower, "upper_utility": min(1.0, lower + 1.0 - coverage),
            "contributions": contributions, "missing": missing, "access": site["access"],
            "cost": site.get("cost"), "days": site.get("days"),
            "longitude": site["longitude"], "latitude": site["latitude"]}


def score_all(comparison_input, weights):
    mission = comparison_input["mission"]
    scored = [score_site(site, mission, weights) for site in comparison_input["sites"]]
    scored.sort(key=lambda item: (-item["lower_utility"], item["id"]))
    return scored
