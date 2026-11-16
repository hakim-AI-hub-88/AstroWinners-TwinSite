"""Body-aware location selection (port of ARES reference 0.4.0 scope rules)."""
from __future__ import annotations

import copy
import math

COORDINATE_SYSTEMS = {
    "Earth": "WGS84_lonlat",
    "Moon": "Moon_planetocentric_east_180",
    "Mars": "Mars_planetocentric_east_180",
}


def coordinate(value, lower, upper):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and lower <= value <= upper)


def validate_scope(mission):
    if mission.get("start_trigger") != "user_request":
        raise ValueError("a location choice and user_request start trigger are required")
    if mission.get("mode") not in {"auto", "custom"}:
        raise ValueError("mode must be auto or custom")
    scope = mission.get("scope", {})
    locations = scope.get("locations", [])
    if not 1 <= len(locations) <= 3:
        raise ValueError("select 1 to 3 bounded sites or zones, at most one selection per body")
    seen, bodies = set(), set()
    for location in locations:
        identifier = location.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("selected location IDs must be unique nonempty strings")
        seen.add(identifier)
        if location.get("kind", "site") not in {"site", "zone"}:
            raise ValueError("selection kind must be site or zone")
        body = location.get("body")
        if body not in COORDINATE_SYSTEMS:
            raise ValueError("location body must be Earth, Moon or Mars")
        if body in bodies:
            raise ValueError("select only one site or zone per body")
        bodies.add(body)
        if location.get("coordinate_system") != COORDINATE_SYSTEMS[body]:
            raise ValueError("location coordinate system must match its body")
        bounds = location.get("bbox", [])
        if len(bounds) != 4:
            raise ValueError("bbox requires west, south, east, north")
        west, south, east, north = bounds
        if not (coordinate(west, -180, 180) and coordinate(east, -180, 180)
                and coordinate(south, -90, 90) and coordinate(north, -90, 90)):
            raise ValueError("bbox has invalid longitude or latitude")
        longitude_span = (east - west) % 360
        if not 0 < longitude_span <= 2 or not 0 < north - south <= 2:
            raise ValueError("location bounds must span over 0 and at most 2 degrees per axis")
    compare_with = scope.get("compare_with", [])
    if (not isinstance(compare_with, list) or not all(isinstance(b, str) for b in compare_with)
            or len(set(compare_with)) != len(compare_with)):
        raise ValueError("compare_with must be a unique list of bodies")
    if "Earth" in bodies:
        if not compare_with or not set(compare_with) <= {"Moon", "Mars"}:
            raise ValueError("an Earth selection requires Moon, Mars, or both in compare_with")
        if not (bodies - {"Earth"}) <= set(compare_with):
            raise ValueError("selected planetary sites must be explicit Earth comparison targets")
    elif compare_with and compare_with != ["Earth"]:
        raise ValueError("Moon and Mars selections compare automatically with Earth only")
    return scope


def comparison_bodies(mission):
    scope = validate_scope(mission)
    bodies = {location["body"] for location in scope["locations"]}
    targets = set(scope["compare_with"]) if "Earth" in bodies else bodies
    return [body for body in ("Moon", "Mars") if body in targets]


def contains(location, site):
    if location["body"] != site["body"]:
        return False
    west, south, east, north = location["bbox"]
    longitude, latitude = site["longitude"], site["latitude"]
    longitude_matches = west <= longitude <= east
    if west > east:
        longitude_matches = longitude >= west or longitude <= east
    return longitude_matches and south <= latitude <= north


def apply_scope(payload):
    scope = validate_scope(payload["mission"])
    scoped = copy.deepcopy(payload)
    earth_anchor = next((item for item in scope["locations"] if item["body"] == "Earth"), None)
    selected, excluded, seen = [], [], set()
    for site in scoped["sites"]:
        identifier = site.get("id")
        if not isinstance(identifier, str) or not identifier or identifier in seen:
            raise ValueError("input site IDs must be unique nonempty strings")
        seen.add(identifier)
        body = site.get("body")
        if body not in COORDINATE_SYSTEMS or site.get("coordinate_system") != COORDINATE_SYSTEMS[body]:
            raise ValueError("each candidate needs its body and matching coordinate system")
        if not coordinate(site.get("longitude"), -180, 180) or not coordinate(site.get("latitude"), -90, 90):
            raise ValueError("invalid candidate location coordinates")
        if body == "Earth" and (earth_anchor is None or contains(earth_anchor, site)):
            selected.append(site)
        else:
            excluded.append(identifier)
    scoped["sites"] = selected
    return scoped, excluded


def contains_bounds(parent, child):
    """Containment for validated small boxes, including a wrapped dateline."""
    if parent["body"] != child["body"]:
        return False
    pw, ps, pe, pn = parent["bbox"]
    cw, cs, ce, cn = child["bbox"]
    offset = (cw - pw) % 360
    return ps <= cs <= cn <= pn and offset + (ce - cw) % 360 <= (pe - pw) % 360 + 1e-10
