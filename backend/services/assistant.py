#############################################################################
# AI MISSION ASSISTANT  (Groq LLM + tool calling)
#
# Why this file exists:
#   Lets a user ask questions in natural language ("why is site #1 better than
#   #3?", "can my rover drive there?", "explain Jezero's score to a child") and
#   get an answer GROUNDED in the project's own results.
#
# How it works:
#   1. The browser sends the question, the recent conversation and the current
#      dashboard state (target, rover filter, selected region).
#   2. The LLM (Groq, OpenAI-compatible tool calling) decides which TOOLS to call.
#   3. Each tool runs the project's real code (services/analysis.py ->
#      similarity_engine) and returns compact JSON.
#   4. The LLM writes the answer from those tool results only.
#
# Scientific guard-rails (system prompt + tool design):
#   - every number must come from a tool; nothing is invented
#   - limits are always stated (estimated temperatures, 11 km cells, gaps)
#   - the assistant explains; it never changes scores or rankings
#
# Input : question (str), history (list of {role, content}), context (dict)
# Output: {"answer", "tools_used", "model", "provider", "tokens", "mode"}
# Fallback: no Groq key / Groq error -> services.ai_bridge (free multi-provider
#           router) answers WITHOUT tools from the current analysis facts.
# Raises: AssistantUnavailable (Groq AND the router unavailable)
#
# Future extension: add a tool -> write the function, add it to TOOLS and
# TOOL_FUNCTIONS. A visual-similarity tool can plug in the same way.
#############################################################################
from __future__ import annotations

import json
import logging
import math
import os

from services import analysis
from utils import config

log = logging.getLogger(__name__)


class AssistantUnavailable(RuntimeError):
    """The assistant cannot answer (missing key, network, provider error)."""


#############################################
# SYSTEM PROMPT (static -> cacheable prefix)
#############################################
SYSTEM_PROMPT = """You are the Mission Assistant of the "Planetary Analog Discovery System", a NASA Space Apps project.
The system compares ~11 km regions of two Earth analog zones - the Atacama Desert (Chile, default) and
Merzouga / Erg Chebbi (Morocco) - with a Mars or Moon target (Jezero Crater, Gale Crater, Mare Tranquillitatis,
Apollo 15) using NASA data, and recommends field-test sites for rovers and crews. Both zones use the same pipeline
and the same normalized scale, so their scores are directly comparable.

How to answer:
1. Get every number from the tools. Never invent scores, coordinates, temperatures, percentages or dataset
   names. If no tool provides something, say it is not available.
2. Answer in the user's language (French if they write in French, English if in English).
3. Be concise: at most 120 words (one short paragraph or 3-5 bullets) unless the user asks for detail.
   Use **bold** for key numbers. No tables, no headings. Scores are written "86.6 / 100", never as a percentage.
   If the user asks for a simple explanation (for a child, a beginner, the public), use everyday words, one
   concrete comparison from daily life, no jargon (no "normalized", no "distance"), and at most 3 numbers.
4. "Site #N", "site n°N" or "region N" means rank N of the CURRENT dashboard analysis given in the dashboard state
   (current target AND current Earth zone), unless the user names another target or zone. Use the dashboard's rover
   filter settings unless asked otherwise. To compare the Atacama and Merzouga, call compare_zones.
5. Explain the science honestly and mention the limits that matter for the question:
   - scores are 0-100 (100 = identical profile on the normalized scale) and rank regions of the chosen Earth zone;
   - Mars temperatures are model estimates; Moon temperatures are partly measured (Diviner), partly published values;
   - cells are ~11 km; thermal inertia and iron are missing on Earth (and on the Moon);
   - elevation is NOT compared because each body measures altitude from a different zero (Earth sea level,
     Mars areoid, Moon reference sphere) - not because data is missing;
   - night temperature usually dominates the remaining difference (Earth nights are much warmer than on Mars/Moon);
   - in Merzouga, features at ~3.7 km cannot see dune shapes (Erg Chebbi), a known limit.
6. Physical values (K, degrees, m) explain; normalized values (0-1) are what the score uses.
7. For field logistics (roads, permits, safety), say the exact point must be checked on site.
"""

#############################################
# TOOL DEFINITIONS (JSON schema, OpenAI-compatible format used by Groq)
#############################################
_TARGET_PROPS = {
    "planet": {"type": "string", "enum": ["mars", "moon"], "description": "Body of the target."},
    "location": {"type": "string", "enum": ["Jezero Crater", "Gale Crater", "Mare Tranquillitatis", "Apollo 15"],
                 "description": "Target name (Jezero/Gale are on Mars, Mare Tranquillitatis/Apollo 15 on the Moon)."},
    "rover_mode": {"type": "boolean", "description": "Only propose rover-accessible regions. Omit to use the dashboard setting."},
    "max_slope": {"type": "number", "description": "Rover slope limit in degrees (5-30). Omit to use the dashboard setting."},
    "zone": {"type": "string", "enum": ["atacama", "merzouga"],
             "description": "Earth analog zone: 'atacama' (Chile) or 'merzouga' (Erg Chebbi, Morocco). Omit to use the dashboard zone."},
}


def _tool(name: str, description: str, props: dict, required: list[str]) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": description,
        "parameters": {"type": "object", "properties": props, "required": required}}}


TOOLS = [
    _tool("run_similarity",
          "Run the similarity analysis for a target in one Earth zone: best score, confidence, top 10 regions "
          "(score, drivable share, exact point), features used/skipped, target physical profile.",
          dict(_TARGET_PROPS), ["planet", "location"]),
    _tool("get_region_details",
          "Details of one ranked region of the Earth zone: per-feature physical values for target and region, each feature's "
          "share of the distance, closest matches, biggest differences, exact point (slope, elevation, temperatures).",
          {**_TARGET_PROPS, "rank": {"type": "integer", "description": "Rank in the ranking (1 = best)."}},
          ["planet", "location", "rank"]),
    _tool("compare_regions",
          "Explain why one ranked region scores higher than another: feature-by-feature comparison of two ranks.",
          {**_TARGET_PROPS, "rank_a": {"type": "integer"}, "rank_b": {"type": "integer"}},
          ["planet", "location", "rank_a", "rank_b"]),
    _tool("get_cell_at",
          "Score, rover accessibility and physical values of the Earth-zone cell containing a latitude/longitude "
          "(any place in 25-22 S, 70-66 W, not only ranked regions).",
          {**_TARGET_PROPS, "lat": {"type": "number"}, "lon": {"type": "number"}},
          ["planet", "location", "lat", "lon"]),
    _tool("compare_zones",
          "Compare the two Earth analog zones (Atacama, Chile vs Merzouga, Morocco) for one target: best score, "
          "confidence, best region and exact point, physical values of the best region per feature, validation summary.",
          {k: v for k, v in _TARGET_PROPS.items() if k != "zone"}, ["planet", "location"]),
    _tool("get_method_and_limits",
          "How the score is computed (features, weights, uncertainty penalty, rover filter, data roles) and the known "
          "scientific limits of the project.", {}, []),
    _tool("get_validation",
          "Validation: where published Mars-analog sites of the Earth zone fall in this target's ranking (Atacama: NASA / "
          "NASA-funded Licancabur, Yungay, Salar de Pajonales; Merzouga: Austrian Space Forum MARS2013 camps), with sources.",
          dict(_TARGET_PROPS), ["planet", "location"]),
    _tool("get_ml_insights",
          "Machine-learning view (unsupervised, independent of the score): PCA position of the Earth zone vs Mars and the "
          "Moon, K-means terrain types shared by the three bodies, the target's terrain type, and how many top-10 "
          "regions share it (agreement between methods).",
          dict(_TARGET_PROPS), ["planet", "location"]),
    _tool("get_dataset_info",
          "NASA datasets used for a body or Earth zone ('earth' = Atacama, 'merzouga'), resolution, coverage, missing features.",
          {"body": {"type": "string", "enum": ["earth", "merzouga", "mars", "moon"]}}, ["body"]),
]


#############################################
# TOOL IMPLEMENTATIONS (all reuse the real analysis)
#############################################
def _r(v, d=2):
    return None if v is None or (isinstance(v, float) and not math.isfinite(v)) else round(v, d)


def _analysis(args: dict, ctx: dict) -> dict:
    rover = args.get("rover_mode", ctx.get("rover_mode", False))
    slope = args.get("max_slope", ctx.get("max_slope"))
    planet, location, rover, slope = analysis.validate(args.get("planet"), args.get("location"), rover, slope)
    zone = analysis.validate_zone(args.get("zone", ctx.get("zone")))
    try:   # analyse with the same cleaning profile the dashboard used, so numbers match what the user sees
        cleaning, _ = analysis.validate_options(ctx.get("cleaning"), None)
    except Exception:  # noqa: BLE001 - unknown profile from the client: fall back to the default
        cleaning = "standard"
    return analysis.run(planet, location, rover, slope, zone, cleaning)


def _region(res: dict, rank: int) -> dict:
    if not 1 <= int(rank) <= len(res["ranking"]):
        raise analysis.AnalysisInputError(f"rank must be between 1 and {len(res['ranking'])}")
    return res["ranking"][int(rank) - 1]


def _comparison_rows(region: dict) -> list[dict]:
    return [{"feature": c["feature"], "units": c["units"], "status": c["status"],
             "target_value": _r(c["target_value"], 3), "atacama_value": _r(c["earth_value"], 3),
             "share_of_distance_pct": c["share_of_distance_pct"]} for c in region["comparison"]]


def tool_run_similarity(args: dict, ctx: dict) -> dict:
    res = _analysis(args, ctx)
    m = res["method"]
    return {
        "target": {k: res["target"][k] for k in ("planet", "location", "lat", "lon", "note", "window_km", "cells_in_window")},
        "target_physical_profile": {k: _r(v, 3) for k, v in res["target"]["profile_physical"].items()},
        "best_score": res["score"], "best_confidence": res["confidence"],
        "score_range_all_cells": m["score_distribution"], "cells_scored": m["cells_scored"],
        "rover_filter": m["rover"], "features_used": m["features_used"], "features_skipped": m["features_skipped"],
        "top_regions": [{"rank": x["rank"], "lat": x["lat"], "lon": x["lon"], "score": x["score"],
                         "confidence": x["confidence"], "drivable_pct": x["accessible_pct"],
                         "exact_point": x["refined"]} for x in res["ranking"]],
    }


def tool_get_region_details(args: dict, ctx: dict) -> dict:
    res = _analysis(args, ctx)
    reg = _region(res, args.get("rank", 1))
    return {"rank": reg["rank"], "lat": reg["lat"], "lon": reg["lon"], "score": reg["score"],
            "confidence": reg["confidence"], "drivable_pct": reg["accessible_pct"],
            "features": _comparison_rows(reg), "closest_matches": reg["explanation"]["matches"],
            "biggest_differences": reg["explanation"]["differs"], "not_compared": reg["explanation"]["not_compared"],
            "exact_point": reg["refined"]}


def tool_compare_regions(args: dict, ctx: dict) -> dict:
    res = _analysis(args, ctx)
    a, b = _region(res, args.get("rank_a", 1)), _region(res, args.get("rank_b", 2))
    rows_b = {r["feature"]: r for r in _comparison_rows(b)}
    feats = []
    for ra in _comparison_rows(a):
        if ra["status"] != "used":
            continue
        rb = rows_b[ra["feature"]]
        feats.append({"feature": ra["feature"], "units": ra["units"], "target_value": ra["target_value"],
                      f"region_{a['rank']}_value": ra["atacama_value"], f"region_{b['rank']}_value": rb["atacama_value"],
                      f"region_{a['rank']}_share_of_distance_pct": ra["share_of_distance_pct"],
                      f"region_{b['rank']}_share_of_distance_pct": rb["share_of_distance_pct"]})
    return {"region_a": {"rank": a["rank"], "score": a["score"], "lat": a["lat"], "lon": a["lon"],
                         "drivable_pct": a["accessible_pct"]},
            "region_b": {"rank": b["rank"], "score": b["score"], "lat": b["lat"], "lon": b["lon"],
                         "drivable_pct": b["accessible_pct"]},
            "score_difference": _r((a["score"] or 0) - (b["score"] or 0), 1), "features": feats,
            "note": "Lower share of distance = closer to the target on that feature."}


def tool_get_cell_at(args: dict, ctx: dict) -> dict:
    res = _analysis(args, ctx)
    lat, lon = float(args["lat"]), float(args["lon"])
    h = res["map_cell_deg"] / 2
    cell = next((c for c in res["map"] if abs(c["lat"] - lat) <= h and abs(c["lon"] - lon) <= h), None)
    if cell is None:
        b = res["zone"]["bbox"]
        return {"error": f"This point is outside the {res['zone']['full_name']} study area ({b['lat_min']} to {b['lat_max']} lat, {b['lon_min']} to {b['lon_max']} lon)."}
    scored = sorted(c["score"] for c in res["map"] if c["score"] is not None)
    rank_pct = (sum(s < cell["score"] for s in scored) / len(scored) * 100) if cell["score"] is not None else None
    return {"cell_center": {"lat": cell["lat"], "lon": cell["lon"]}, "score": cell["score"],
            "better_than_pct_of_cells": _r(rank_pct, 0),
            "drivable_fraction": cell["accessible"], "rover_slope_limit_deg": res["method"]["rover"]["max_slope_deg"],
            "physical_values": cell.get("physical"),
            "note": None if cell["score"] is not None else "Not scored: some features are missing for this cell."}


def tool_compare_zones(args: dict, ctx: dict) -> dict:
    out = {}
    for zid in config.EARTH_ZONES:
        try:
            res = _analysis({**args, "zone": zid}, ctx)
        except (FileNotFoundError, ValueError) as exc:
            out[zid] = {"error": str(exc)}
            continue
        best = res["ranking"][0] if res["ranking"] else None
        out[zid] = {
            "zone": res["zone"]["full_name"], "best_score": res["score"], "confidence": res["confidence"],
            "score_range_all_cells": res["method"]["score_distribution"],
            "best_region": None if not best else {"lat": best["lat"], "lon": best["lon"], "drivable_pct": best["accessible_pct"],
                                                  "exact_point": best["refined"]},
            "best_region_features": [] if not best else [
                {"feature": c["feature"], "units": c["units"], "target_value": _r(c["target_value"], 3),
                 "zone_value": _r(c["earth_value"], 3)} for c in best["comparison"] if c["status"] == "used"],
            "validation_summary": res["validation"]["summary"],
        }
    scores = {z: v.get("best_score") for z, v in out.items() if v.get("best_score") is not None}
    winner = max(scores, key=scores.get) if scores else None
    return {"zones": out, "closer_analog_zone": winner,
            "score_difference": _r(abs(scores["atacama"] - scores["merzouga"]), 1) if len(scores) == 2 else None}


def tool_get_method_and_limits(args: dict, ctx: dict) -> dict:
    s, rv = config.SIMILARITY, config.ROVER
    return {
        "algorithm": "Weighted distance on normalized (0-1) harmonized features between each ~11 km Earth-zone cell and the "
                     "mean profile of the target area (50 km radius). Score = 100 x (1 - distance).",
        "weights": s["weights"], "excluded_features": s["excluded"],
        "uncertainty_penalty": f"Weights of values flagged uncertain (estimated temperature, proxy albedo) are reduced by "
                               f"{int(s['uncertainty_penalty'] * 100)} %.",
        "missing_data_rule": "Only cells with every compared feature are scored (missing data would inflate scores).",
        "ranking": f"Top {s['top_n']} regions at least {s['min_separation_km']} km apart.",
        "rover_filter": f"A region is proposed only if >= {int(rv['min_accessible_fraction'] * 100)} % of its 1 km land "
                        "cells have a mean slope under the limit; it never changes scores.",
        "exact_point": "Inside each region: 1 km cell with no water, slope under the limit, temperatures closest to the target.",
        "data_roles": {"normalized_harmonized": "scoring and ranking only",
                       "physical_harmonized": "explanations only",
                       "earth_processed_1km": "rover filter and exact point only"},
        "known_limits": [
            "Mars day/night temperatures are estimated with a thermal model from TES albedo + thermal inertia (validated at "
            "Jezero: day 276 K vs 276 K reference, night 179 K vs 194 K).",
            "Moon temperatures: measured by Diviner where available, otherwise published values (~392 K day, ~95 K night).",
            "Earth temperatures are MODIS snapshots (~10:30 and ~22:30 local time), not daily max/min.",
            "Thermal inertia and iron are missing on Earth; thermal inertia and iron are missing on the Moon.",
            "Cells are ~11 km (3.7 km elevation pixels); local terrain must be checked on site.",
            "Night temperature usually dominates the remaining distance: Earth nights are 85-180 K warmer.",
            "Scores rank regions of one Earth zone for one target; both zones share the same scale, so their "
            "best scores can be compared. They are not an absolute probability.",
        ],
    }


def tool_get_validation(args: dict, ctx: dict) -> dict:
    v = _analysis(args, ctx)["validation"]
    keep = ("name", "program", "studied_for", "inside_study_area", "score", "percentile", "verdict_label",
            "nearest_top10", "cell", "note")
    return {"summary": v["summary"], "method": v["method"],
            "sites": [{k: s.get(k) for k in keep} | {"sources": [x["label"] for x in s["sources"]]} for s in v["sites"]],
            "field_meaning": {"percentile": "share of the zone's cells scoring lower than the site's own cell",
                              "nearest_top10": "the CLOSEST ranked region to the site and its distance - this is NOT "
                                               "the site's own rank"},
            "interpretation": "Agreement is expected when a site was chosen for terrain/thermal properties "
                              "(Licancabur, Pajonales). Yungay was chosen for extreme dryness, which the cross-planet "
                              "features do not compare, so a low rank there shows a limit of the method."}


def tool_get_ml_insights(args: dict, ctx: dict) -> dict:
    from services import ml_models
    ins = ml_models.insights(_analysis(args, ctx))
    c, p = ins["clustering"], ins["pca"]
    return {"pca": {"explained_variance_pct": p["explained_variance_pct"], "axis_meaning": p["axis_labels"],
                    "centroid_distance_6d": p["centroid_distance"],
                    "atacama_closer_to_mars_by": round(p["centroid_distance"]["earth_moon"] / p["centroid_distance"]["earth_mars"], 2)},
            "terrain_types": [{k: ty[k] for k in ("id", "name", "share_pct", "target_share_pct")} for ty in c["types"]],
            "k": c["k"], "silhouettes": c["silhouettes"], "target_type": c["target_type"],
            "target_type_share_pct": c["target_type_share_pct"], "atacama_same_type_pct": c["atacama_same_type_pct"],
            "agreement_with_score": ins["agreement"], "method": ins["method"],
            "note": "Temperatures are excluded from the terrain types on purpose (with them, clusters just separate "
                    "the bodies). Albedo is excluded because each body uses a different instrument."}


def tool_get_dataset_info(args: dict, ctx: dict) -> dict:
    body = args.get("body")
    datasets = {
        "earth": ["NASADEM (30 m elevation)", "MODIS MOD11A2 land surface temperature (1 km)",
                  "MODIS MOD13Q1 vegetation", "MCD19A2 aerosols", "SMAP soil moisture", "NASA POWER albedo (1 deg)"],
        "merzouga": ["NASADEM (30 m elevation, tiles n30-n31 w004-w005)", "MODIS MOD11A2 land surface temperature (1 km)",
                     "MODIS MOD13Q1 vegetation", "MCD19A2 aerosols (4 days)", "SMAP soil moisture",
                     "NASA POWER albedo (1 deg)"],
        "mars": ["MGS MOLA MEGDR elevation (16 px/deg, ~3.7 km)", "MGS TES albedo (8 px/deg)",
                 "MGS TES thermal inertia (8 px/deg)", "Mars Odyssey GRS iron (5 deg)"],
        "moon": ["LRO LOLA LDEM_16 elevation (~1.9 km)", "LRO Diviner temperatures (GCP bands + GDR L3)",
                 "LROC WAC 643 nm reflectance (albedo proxy)"],
    }
    if body not in datasets:
        return {"error": "body must be earth, merzouga, mars or moon"}
    out = {"body": body, "nasa_datasets": datasets[body]}
    report = config.HARMONIZED_DATA_DIR / "validation_report.json"
    if report.is_file():
        s = json.loads(report.read_text(encoding="utf-8"))["bodies"].get(body, {})
        out.update(resolution=s.get("resolution"), rows=s.get("rows_written"),
                   missing_features=s.get("missing_features"),
                   coverage_pct={k: v.get("valid_pct") for k, v in s.get("features", {}).items()})
    return out


TOOL_FUNCTIONS = {
    "run_similarity": tool_run_similarity, "get_region_details": tool_get_region_details,
    "compare_regions": tool_compare_regions, "get_cell_at": tool_get_cell_at,
    "get_method_and_limits": tool_get_method_and_limits, "get_dataset_info": tool_get_dataset_info,
    "get_validation": tool_get_validation, "get_ml_insights": tool_get_ml_insights,
    "compare_zones": tool_compare_zones,
}


def run_tool(name: str, raw_args: str, ctx: dict) -> str:
    """Execute one tool call; errors are returned to the model as JSON (it can recover)."""
    try:
        args = json.loads(raw_args or "{}")
        if not isinstance(args, dict):
            raise ValueError("arguments must be a JSON object")
        fn = TOOL_FUNCTIONS.get(name)
        result = fn(args, ctx) if fn else {"error": f"unknown tool {name}"}
    except (ValueError, KeyError, TypeError, analysis.AnalysisInputError) as exc:
        result = {"error": str(exc)}
    text = json.dumps(result, ensure_ascii=False, default=str)
    limit = config.ASSISTANT["max_tool_result_chars"]
    return text if len(text) <= limit else text[:limit] + "... [truncated]"


#############################################
# CONVERSATION LOOP
#############################################
def _groq_key() -> str:
    """Groq key from the environment or the platform secret file (any GROQ_API_KEY* name)."""
    primary = config.ASSISTANT["api_key_env"]
    key = os.environ.get(primary, "").strip()
    if key:
        return key
    try:
        from twinsite.ai.secrets import load_ai_secrets
        secrets = load_ai_secrets()
    except Exception:  # noqa: BLE001 - unreadable secret file = no key
        secrets = {}
    names = sorted((n for n in secrets if n.startswith(primary)), key=lambda n: (n != primary, n))
    return secrets[names[0]] if names else ""


def groq_configured() -> bool:
    return bool(_groq_key())


def _client():
    key = _groq_key()
    if not key:
        raise AssistantUnavailable("Groq tool-calling unavailable: no GROQ_API_KEY configured.")
    try:
        from groq import Groq
    except ImportError as exc:
        raise AssistantUnavailable("Groq tool-calling unavailable: the 'groq' package is not installed.") from exc
    return Groq(api_key=key, timeout=config.ASSISTANT["timeout_s"], max_retries=1)


def _context_note(ctx: dict) -> str:
    if not ctx.get("planet"):
        return "[Dashboard state: no analysis run yet.]"
    zone = config.EARTH_ZONES.get(ctx.get("zone") or config.DEFAULT_ZONE, {}).get("full_name", "Atacama Desert (Chile)")
    return (f"[Dashboard state: Earth zone = {zone}, target = {ctx.get('location')} ({ctx.get('planet')}), "
            f"rover filter = {'on' if ctx.get('rover_mode') else 'off'}, max slope = {ctx.get('max_slope')} deg, "
            f"selected region = #{ctx.get('selected_rank', 1)}, cleaning = {ctx.get('cleaning') or 'standard'}.]")


def _clean_history(history) -> list[dict]:
    out = []
    for h in (history or [])[-config.ASSISTANT["max_history_messages"]:]:
        if isinstance(h, dict) and h.get("role") in ("user", "assistant") and isinstance(h.get("content"), str):
            out.append({"role": h["role"], "content": h["content"][:4000]})
    return out


def answer(question: str, history=None, context: dict | None = None) -> dict:
    """Groq tool-calling first. When Groq is missing or fails, the free multi-provider router
    (services.ai_bridge) answers WITHOUT tools, from the dashboard state and the current analysis
    facts. Raises AssistantUnavailable only when both paths fail."""
    ctx = context or {}
    try:
        return _answer_groq(question, history, ctx)
    except AssistantUnavailable as exc:
        groq_reason = str(exc)
    except Exception as exc:  # noqa: BLE001 - any Groq/SDK failure -> router fallback
        log.warning("assistant: Groq path failed (%s)", exc.__class__.__name__)
        groq_reason = f"Groq tool-calling failed ({exc.__class__.__name__})."
    return _answer_router(question, history, ctx, groq_reason)


FALLBACK_NOTE = """
Tools are NOT available in this conversation. The only data you may use is the JSON block "Analysis facts" in the
user message (computed by this project's own analysis for the current dashboard state). If the facts do not contain
what is asked, say so and suggest running the analysis in Mission Control. Never invent numbers."""


def _answer_router(question: str, history, ctx: dict, groq_reason: str) -> dict:
    from services import ai_bridge

    facts = None
    if ctx.get("planet") and ctx.get("location"):
        try:
            facts = tool_run_similarity({"planet": ctx["planet"], "location": ctx["location"]}, ctx)
        except Exception as exc:  # noqa: BLE001 - datasets may be missing; answer without facts
            facts = {"error": f"analysis unavailable: {exc}"}
    convo = "\n".join(f"{h['role']}: {h['content']}" for h in _clean_history(history))
    parts = [f"Conversation so far:\n{convo}" if convo else "", f"Question: {question.strip()}", _context_note(ctx),
             "Analysis facts:\n" + json.dumps(facts, ensure_ascii=False, default=str)[:config.ASSISTANT["max_tool_result_chars"]]]
    res = ai_bridge.complete_text(SYSTEM_PROMPT + FALLBACK_NOTE, "\n\n".join(p for p in parts if p),
                                  json_mode=False, purpose="assistant", max_tokens=900)
    if res["status"] != "ok" or not res["text"]:
        raise AssistantUnavailable(f"Assistant unavailable. {groq_reason} Free AI router: {res['reason']}")
    return {"answer": res["text"], "tools_used": [], "model": ai_bridge.provider_label(res) + " (no tools)",
            "provider": res["provider"], "tokens": 0, "mode": "router_no_tools", "fallback_reason": groq_reason}


def _answer_groq(question: str, history, ctx: dict) -> dict:
    cfg = config.ASSISTANT
    client = _client()                 # raises AssistantUnavailable when no key / no SDK
    import groq  # error classes

    label = f"Groq · {cfg['model']}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *_clean_history(history),
                {"role": "user", "content": f"{question.strip()}\n\n{_context_note(ctx)}"}]
    used, tokens = [], 0

    try:
        for round_ in range(cfg["max_tool_rounds"] + 1):
            last = round_ == cfg["max_tool_rounds"]
            resp = client.chat.completions.create(
                model=cfg["model"], messages=messages, temperature=cfg["temperature"],
                tools=TOOLS, tool_choice="none" if last else "auto")
            tokens += getattr(resp.usage, "total_tokens", 0) or 0
            msg = resp.choices[0].message
            if not msg.tool_calls:
                text = (msg.content or "").strip()
                if not text:
                    raise AssistantUnavailable("Groq returned an empty answer.")
                return {"answer": text, "tools_used": used, "model": label, "provider": "groq",
                        "tokens": tokens, "mode": "groq_tools"}
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": t.id, "type": "function", "function": {"name": t.function.name, "arguments": t.function.arguments}}
                for t in msg.tool_calls]})
            for t in msg.tool_calls:
                used.append(t.function.name)
                messages.append({"role": "tool", "tool_call_id": t.id,
                                 "content": run_tool(t.function.name, t.function.arguments, ctx)})
    except groq.AuthenticationError as exc:
        raise AssistantUnavailable("Groq rejected the API key.") from exc
    except groq.RateLimitError as exc:
        raise AssistantUnavailable("Groq rate limit reached.") from exc
    except groq.APIConnectionError as exc:
        raise AssistantUnavailable("Cannot reach Groq.") from exc
    except groq.APIStatusError as exc:
        log.warning("Groq API error %s", exc.status_code)
        raise AssistantUnavailable(f"Groq error (HTTP {exc.status_code}).") from exc
    return {"answer": "I could not finish within the tool limit.", "tools_used": used, "model": label,
            "provider": "groq", "tokens": tokens, "mode": "groq_tools"}
