#############################################################################
# MISSION REPORT (TWINSITE)
#
# Why this file exists:
#   Builds the content of the printable mission report for one target:
#     1. facts      - numbers taken from the analysis of EVERY Earth zone
#                     (analysis.run, same cached results as the dashboard)
#     2. narrative  - executive summary, findings, recommendations, risks,
#                     written by the Groq LLM from the facts ONLY (JSON mode);
#                     deterministic fallback text when no API key / no network
#     3. maps       - one PNG similarity map per Earth zone (Pillow), drawn
#                     from the scored ~11 km cells, ranked regions and the
#                     validation sites (no external tiles, so it always prints)
#
# Data roles: scores come from the normalized data (analysis), the text uses
# physical values (explanation role); nothing here changes any score.
#############################################################################
from __future__ import annotations

import base64
import io
import json
import logging
import math
import re

from services import analysis
from utils import config

log = logging.getLogger(__name__)


#############################################
# 1. FACTS (compact, JSON-ready)
#############################################
def _r(v, d=1):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), d)


def _region_facts(reg: dict) -> dict:
    p = reg.get("refined") or {}
    return {
        "rank": reg["rank"], "lat": _r(reg["lat"], 3), "lon": _r(reg["lon"], 3),
        "score": _r(reg["score"]), "confidence_pct": _r(100 * (reg.get("confidence") or 0), 0),
        "drivable_pct": reg.get("accessible_pct"),
        "exact_point": {"lat": _r(p.get("lat"), 4), "lon": _r(p.get("lon"), 4),
                        "elevation_m": _r(p.get("elevation_m"), 0), "slope_deg": _r(p.get("slope_deg"))} if p else None,
        "closest_parameters": reg["explanation"]["matches"],
        "biggest_differences": reg["explanation"]["differs"],
    }


def build_facts(planet: str, location: str, rover_mode: bool, max_slope: float) -> tuple[dict, dict]:
    """Return (facts for the LLM, raw results per zone)."""
    results = {}
    for zone in config.EARTH_ZONES:
        try:
            results[zone] = analysis.run(planet, location, rover_mode, max_slope, zone)
        except Exception as exc:  # noqa: BLE001 - a missing zone must not break the report
            log.warning("report: zone %s unavailable: %s", zone, exc)
    if not results:
        raise analysis.AnalysisInputError("No Earth zone could be analysed.")
    any_res = next(iter(results.values()))
    t = any_res["target"]
    facts = {
        "target": {"body": planet, "site": location, "lat": t["lat"], "lon": t["lon"], "note": t["note"],
                   "profile_physical": {k: _r(v, 2) for k, v in t["profile_physical"].items()}},
        "rover_filter": {"enabled": rover_mode, "max_slope_deg": max_slope},
        "features_compared": any_res["method"]["features_used"],
        "zones": {},
    }
    for zone, res in results.items():
        v = (res.get("validation") or {}).get("summary") or {}
        facts["zones"][zone] = {
            "name": res["zone"]["full_name"],
            "best_score": _r(res["score"]), "confidence_pct": _r(100 * (res.get("confidence") or 0), 0),
            "cells_scored": res["method"]["cells_scored"],
            "score_range": [_r(res["method"]["score_distribution"]["min"]), _r(res["method"]["score_distribution"]["max"])],
            "top_regions": [_region_facts(reg) for reg in res["ranking"][:3]],
            "validation": {"reference_sites_above_average": v.get("agreeing"), "evaluated": v.get("evaluated"),
                           "mean_percentile": _r(v.get("mean_percentile"), 0),
                           "sites": [{"name": s["name"], "percentile": _r(s.get("percentile"), 0), "verdict": s.get("verdict_label")}
                                     for s in (res.get("validation") or {}).get("sites", []) if s.get("evaluated")]},
        }
    scored = {z: f["best_score"] for z, f in facts["zones"].items() if f["best_score"] is not None}
    if scored:
        best = max(scored, key=scored.get)
        facts["recommended_zone"] = facts["zones"][best]["name"]
    facts["known_limits"] = [
        "Resolution ~11 km for scoring and ~1 km for the exact point; dune or boulder shapes are not resolved.",
        "Atmosphere, pressure, radiation and gravity are not compared (surface parameters only).",
        "Some target temperatures or albedo values are estimated and down-weighted.",
    ]
    return facts, results


#############################################
# 2. NARRATIVE (Groq LLM, JSON mode) + fallback
#############################################
SYSTEM = (
    "You are the TWINSITE mission analyst. Write a professional mission report section for a space agency team "
    "from the JSON facts you receive. Use ONLY numbers present in the facts; never invent data. Be concise and concrete. "
    "Answer with a JSON object with keys: executive_summary (string, 3-5 sentences), key_findings (array of 4-6 short strings), "
    "recommendations (array of 3-5 short strings), risks (array of 3-4 short strings), conclusion (string, 1-2 sentences). "
    "Write in English, in plain professional prose: never quote JSON key names (write 'similarity 86.8 / 100', not 'best_score'), "
    "and use degree, kelvin and metre units."
)


def _fallback(facts: dict) -> dict:
    t = facts["target"]
    zones = facts["zones"]
    best = max(zones.values(), key=lambda z: z["best_score"] or -1)
    top = best["top_regions"][0] if best["top_regions"] else None
    findings = [f"{z['name']}: best similarity {z['best_score']} / 100 (confidence {z['confidence_pct']} %), "
                f"{z['cells_scored']} cells scored." for z in zones.values()]
    if top:
        findings.append(f"Closest parameters at region #1: {', '.join(top['closest_parameters']) or '—'}.")
        findings.append(f"Biggest differences: {', '.join(top['biggest_differences']) or '—'}.")
    point = top and top.get("exact_point")
    return {
        "executive_summary": (f"For {t['site']} ({t['body']}), the closest Earth analog among the studied zones is "
                              f"{best['name']} with a similarity of {best['best_score']} / 100."
                              + (f" The recommended test point is {point['lat']}, {point['lon']}." if point else "")),
        "key_findings": findings,
        "recommendations": [
            f"Plan the field campaign in {best['name']}, starting from region #1.",
            "Verify site access, permits and local terrain at the exact point before deployment.",
            "Complement field tests with thermal-vacuum testing for the colder target nights.",
        ],
        "risks": facts["known_limits"],
        "conclusion": "Analysis generated without the AI narrative (deterministic summary of the computed results).",
        "generated_by": "fallback",
    }


def _parse_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text or "", re.S)
        if not m:
            raise
        return json.loads(m.group(0))


def narrative(facts: dict, use_ai: bool = True) -> dict:
    """AI narrative through the free multi-provider router (services.ai_bridge, JSON mode), anchored to the
    facts: every number it quotes must exist in the facts, otherwise the sentence (list item) is dropped, or
    the whole AI text is replaced by the deterministic summary when the summary/conclusion is affected."""
    if not use_ai:
        return _fallback(facts)
    from services import ai_bridge

    keys = ("executive_summary", "key_findings", "recommendations", "risks", "conclusion")

    def shape_ok(obj):
        if not isinstance(obj, dict) or not isinstance(obj.get("executive_summary"), str) or not obj["executive_summary"].strip():
            return ["executive_summary (non-empty string) required"]
        return [f"{k} must be a list" for k in keys[1:4] if not isinstance(obj.get(k, []), list)]

    try:
        res = ai_bridge.complete_text(SYSTEM, json.dumps(facts, ensure_ascii=False), json_mode=True,
                                      purpose="report", max_tokens=1400, validate=shape_ok)
        if res["status"] != "ok":
            fb = _fallback(facts)
            fb["note"] = f"AI narrative unavailable ({res['reason']}); deterministic summary used."
            return fb
        data = res.get("data") if isinstance(res.get("data"), dict) else _parse_json(res["text"])
        out = {k: data.get(k) for k in keys}
        for k in ("key_findings", "recommendations", "risks"):
            out[k] = [str(x) for x in (out[k] or [])][:8]
        out["executive_summary"] = str(out["executive_summary"] or "").strip()
        out["conclusion"] = str(out["conclusion"] or "").strip()
        allowed = _fact_numbers(facts)
        bad_head = _unanchored(out["executive_summary"], allowed) + _unanchored(out["conclusion"], allowed)
        if not out["executive_summary"] or bad_head:
            fb = _fallback(facts)
            fb["note"] = ("AI narrative rejected: it quoted numbers absent from the computed facts ("
                          + ", ".join(sorted(set(bad_head))[:6]) + "); deterministic summary used.") if bad_head else \
                "AI narrative was empty; deterministic summary used."
            return fb
        removed = []
        for k in ("key_findings", "recommendations", "risks"):
            kept = []
            for item in out[k]:
                bad = _unanchored(item, allowed)
                (removed.append({"section": k, "numbers": bad}) if bad else kept.append(item))
            out[k] = kept
        out["generated_by"] = ai_bridge.provider_label(res) + (" (cached)" if res.get("cached") else "")
        out["numeric_check"] = {"policy": "every quoted number must appear in the facts (2 % tolerance)",
                                "removed_items": removed}
        return out
    except Exception as exc:  # noqa: BLE001 - the report must still be produced
        log.warning("report narrative fallback: %s", exc)
        fb = _fallback(facts)
        fb["note"] = f"AI narrative unavailable ({type(exc).__name__}); deterministic summary used."
        return fb


_NUM_RE = re.compile(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|(?<![\w.])-?\d+(?:\.\d+)?")


def _fact_numbers(facts) -> list[float]:
    """Every number present in the facts (values and numbers written inside strings), plus 100 (score scale)."""
    out = [100.0]

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, (int, float)):
            if math.isfinite(v):
                out.append(abs(float(v)))
        elif isinstance(v, str):
            out.extend(abs(float(t.replace(",", ""))) for t in _NUM_RE.findall(v))
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
    walk(facts)
    return out


def _unanchored(text: str, allowed: list[float]) -> list[str]:
    """Numbers quoted in `text` that are not in the facts (small integers 0-10 are exempt)."""
    bad = []
    for token in _NUM_RE.findall(text or ""):
        x = abs(float(token.replace(",", "")))
        if x <= 10 and x.is_integer():
            continue
        tol = 0.051 if "." in token else 0.51
        if not any(abs(x - a) <= max(0.02 * a, tol) for a in allowed):
            bad.append(token)
    return bad


#############################################
# 3. MAP IMAGES (Pillow)
#############################################
RAMP = [(44, 123, 182), (171, 217, 233), (255, 255, 191), (253, 174, 97), (215, 25, 28)]


def _ramp(t: float) -> tuple[int, int, int]:
    x = min(max(t, 0.0), 1.0) * (len(RAMP) - 1)
    i = min(int(x), len(RAMP) - 2)
    f = x - i
    return tuple(round(a + (b - a) * f) for a, b in zip(RAMP[i], RAMP[i + 1]))


def zone_map_png(res: dict, width: int = 640) -> str:
    """Similarity map of one zone as a base64 PNG (rank colours, like the web map)."""
    from PIL import Image, ImageDraw, ImageFont

    cells = res["map"]
    step = res["map_cell_deg"]
    lats = [c["lat"] for c in cells]
    lons = [c["lon"] for c in cells]
    lat0, lat1 = min(lats) - step / 2, max(lats) + step / 2
    lon0, lon1 = min(lons) - step / 2, max(lons) + step / 2
    kx = math.cos(math.radians((lat0 + lat1) / 2))            # keep ground proportions
    scale = width / ((lon1 - lon0) * kx)
    height = max(200, int((lat1 - lat0) * scale))
    img = Image.new("RGB", (width, height), (12, 10, 9))
    d = ImageDraw.Draw(img)

    def xy(lat, lon):
        return ((lon - lon0) * kx * scale, (lat1 - lat) * scale)

    scores = sorted(c["score"] for c in cells if c.get("score") is not None)
    n = len(scores)
    rover = res["method"].get("rover") or {}
    import bisect
    for c in cells:
        x0, y0 = xy(c["lat"] + step / 2, c["lon"] - step / 2)
        x1, y1 = xy(c["lat"] - step / 2, c["lon"] + step / 2)
        s = c.get("score")
        if s is None:
            col = (42, 51, 80)
        elif rover.get("enabled") and c.get("accessible") is not None and c["accessible"] < rover.get("min_accessible_fraction", 0.5):
            col = (74, 80, 104)
        else:
            col = _ramp(bisect.bisect_left(scores, s) / max(n - 1, 1))
        d.rectangle([x0, y0, x1 + 1, y1 + 1], fill=col)

    try:
        font = ImageFont.load_default(size=13)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    for v in (res.get("validation") or {}).get("sites", []):
        x, y = xy(v["lat"], v["lon"])
        d.polygon([(x, y - 8), (x - 7, y + 5), (x + 7, y + 5)], fill=(255, 255, 255), outline=(0, 0, 0))
    # exact point first, so the rank numbers stay readable on top of it
    best = res["ranking"][0] if res["ranking"] else None
    if best and best.get("refined"):
        x, y = xy(best["refined"]["lat"], best["refined"]["lon"])
        pts = []
        for k in range(10):
            ang = -math.pi / 2 + k * math.pi / 5
            rr = 9 if k % 2 == 0 else 4
            pts.append((x + rr * math.cos(ang), y + rr * math.sin(ang)))
        d.polygon(pts, fill=(255, 255, 255), outline=(0, 0, 0))

    for reg in res["ranking"][:10]:
        x, y = xy(reg["lat"], reg["lon"])
        r = 10
        d.ellipse([x - r, y - r, x + r, y + r], fill=(255, 122, 47) if reg["rank"] == 1 else (16, 12, 10),
                  outline=(255, 255, 255) if reg["rank"] == 1 else (255, 122, 47), width=2)
        d.text((x, y), str(reg["rank"]), fill=(255, 255, 255), font=font, anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


#############################################
# ENTRY POINT
#############################################
def build(planet: str, location: str, rover_mode: bool, max_slope: float, use_ai: bool = True) -> dict:
    planet, location, rover_mode, max_slope = analysis.validate(planet, location, rover_mode, max_slope)
    facts, results = build_facts(planet, location, rover_mode, max_slope)
    maps = {}
    for zone, res in results.items():
        try:
            maps[zone] = zone_map_png(res)
        except Exception as exc:  # noqa: BLE001
            log.warning("report map %s failed: %s", zone, exc)
    return {"facts": facts, "narrative": narrative(facts, use_ai), "maps": maps}
