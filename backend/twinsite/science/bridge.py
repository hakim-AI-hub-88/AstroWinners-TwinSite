"""Build a mission_request from C1 evidence_observation records (no value copying errors).

C3 (or a G2 script) supplies the mission parameters and Earth site operational
metadata (access/cost/days are USER parameters or None, never inferred). Values,
units and source_ids are taken verbatim from evidence so lineage stays exact.
"""
from __future__ import annotations

import copy


def request_from_evidence(mission, earth_sites, target_location, evidence, data_status="measured"):
    """mission: mission_request.mission (features with unit/weight/tolerance/required).
    earth_sites: [{id, name, longitude, latitude, access, cost, days}].
    target_location: scope location dict for the Moon/Mars target (its id == evidence site_id).
    """
    features = mission["features"]
    by_site = {}
    for r in evidence:
        if r["feature_id"] in features and r["value"] is not None:
            key = (r["site_id"], r["feature_id"])
            if key in by_site:
                raise ValueError(f"ambiguous evidence: several records for {key}; choose one period explicitly")
            by_site[key] = r

    def observations(site_id):
        return {f: {"value": r["value"], "unit": r["unit"], "source_id": r["evidence_id"]}
                for (sid, f), r in sorted(by_site.items()) if sid == site_id}

    sites = []
    for meta in earth_sites:
        sites.append(dict(copy.deepcopy(meta), body="Earth", coordinate_system="WGS84_lonlat",
                          observations=observations(meta["id"])))
    mission = copy.deepcopy(mission)
    mission.setdefault("scope", {"locations": [copy.deepcopy(target_location)], "compare_with": ["Earth"]})
    return {"schema_version": "1.0", "data_status": data_status, "mission": mission, "sites": sites,
            "target_profiles": [{"body": target_location["body"], "location": copy.deepcopy(target_location),
                                 "observations": observations(target_location["id"])}]}
