#############################################################################
# VALIDATION AGAINST KNOWN NASA ANALOG SITES
#
# Why this file exists:
#   Checks whether the engine's results agree with what NASA already knows:
#   where do Atacama sites that NASA (or NASA-funded teams) studied as Mars
#   analogs fall in OUR ranking?
#
# What it does NOT do (scientific rule):
#   - it never changes the model, the weights or any score
#   - the reference sites are never an input of the similarity calculation
#   It only reads results that were already computed.
#
# Metrics per reference site:
#   - nearest scored ~11 km cell (distance to the site; sites just outside the
#     study area use the closest cell inside it)
#   - that cell's score and percentile ("better than X % of Atacama cells";
#     a random pick would sit at 50 % on average)
#   - nearest top-10 region (rank, distance)
#   - verdict from the percentile
#
# Input : analysis result dict (services/analysis.py)
# Output: {"sites": [...], "summary": {...}, "method": "..."}
#############################################################################
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

SITES_FILE = Path(__file__).resolve().parents[1] / "data" / "validation_sites.json"
MAX_CELL_DISTANCE_KM = 30.0       # sites further than this from any scored cell are reported as "outside"
EARTH_RADIUS_KM = 6371.0


@lru_cache(maxsize=1)
def load_sites() -> list[dict]:
    return json.loads(SITES_FILE.read_text(encoding="utf-8"))["sites"]


def _km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _verdict(pct: float) -> tuple[str, str]:
    if pct >= 80:
        return "strong", "Strong agreement (top 20 %)"
    if pct >= 60:
        return "agree", "Agreement (above average)"
    if pct >= 40:
        return "neutral", "Neutral (average)"
    return "disagree", "Low rank"


def evaluate(result: dict) -> dict:
    cells = [c for c in result.get("map", []) if c.get("score") is not None]
    if not cells or not result.get("map"):
        return {"sites": [], "summary": {"evaluated": 0}, "method": "No scored cells."}
    scores = sorted(c["score"] for c in cells)
    h = result["map_cell_deg"] / 2
    lat_min = min(c["lat"] for c in result["map"]) - h
    lat_max = max(c["lat"] for c in result["map"]) + h
    lon_min = min(c["lon"] for c in result["map"]) - h
    lon_max = max(c["lon"] for c in result["map"]) + h

    zone = (result.get("zone") or {}).get("id", "atacama")
    out = []
    for s in (x for x in load_sites() if x.get("zone", "atacama") == zone):
        inside = lat_min <= s["lat"] <= lat_max and lon_min <= s["lon"] <= lon_max
        dist, cell = min(((_km(s["lat"], s["lon"], c["lat"], c["lon"]), c) for c in cells), key=lambda x: x[0])
        row = {k: s[k] for k in ("id", "name", "lat", "lon", "program", "studied_for", "analog_type", "sources")}
        row["zone"] = zone
        row["inside_study_area"] = inside
        if dist > MAX_CELL_DISTANCE_KM:
            row.update(evaluated=False, note=f"No scored cell within {MAX_CELL_DISTANCE_KM:.0f} km.")
            out.append(row)
            continue
        pct = 100.0 * sum(v < cell["score"] for v in scores) / len(scores)
        top = min(((_km(s["lat"], s["lon"], r["lat"], r["lon"]), r["rank"]) for r in result["ranking"]),
                  default=(None, None), key=lambda x: x[0] if x[0] is not None else 1e9)
        code, label = _verdict(pct)
        row.update(evaluated=True, cell={"lat": cell["lat"], "lon": cell["lon"], "distance_km": round(dist, 1)},
                   score=cell["score"], percentile=round(pct, 0), verdict=code, verdict_label=label,
                   nearest_top10={"rank": top[1], "distance_km": round(top[0], 0) if top[0] is not None else None})
        out.append(row)

    ev = [r for r in out if r.get("evaluated")]
    mean_pct = round(sum(r["percentile"] for r in ev) / len(ev), 0) if ev else None
    agree = [r for r in ev if r["percentile"] >= 60]
    t = result.get("target", {})
    return {
        "sites": out,
        "summary": {
            "target": t.get("location"), "planet": t.get("planet"),
            "evaluated": len(ev), "agreeing": len(agree), "mean_percentile": mean_pct,
            "random_baseline_percentile": 50,
            "agreeing_sites": [r["name"] for r in agree],
            "is_mars_target": t.get("planet") == "mars",
            "zone": zone,
        },
        "method": "Reference sites are only compared with results already computed; the model was not tuned on them.",
    }
