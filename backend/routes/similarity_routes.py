#############################################################################
# API ROUTES - SIMILARITY
#
# Why this file exists:
#   Defines the HTTP API used by the web interface. Routes stay thin: they
#   validate input, call the services (data_loader, similarity_engine) and
#   turn the result into JSON. No science happens here.
#
# Endpoints:
#   GET  /api/targets     -> planetary targets that can be selected
#   GET  /api/status      -> datasets loaded, rows, available features
#   POST /api/similarity  -> run the analysis for one target
#                            body: {"planet": "mars", "location": "Jezero Crater"}
#
# Future extension:
#   - GET /api/targets/<planet>/<location>/profile  (target feature profile)
#   - query parameters for weights / top-N once the engine exists
#############################################################################
from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import analysis, data_loader, similarity_engine
from utils import config

bp = Blueprint("similarity", __name__, url_prefix="/api")


#############################################
# GET /api/targets
# Output: {"mars": ["Jezero Crater", "Gale Crater"], "moon": [...]}
#############################################
@bp.get("/zones")
def get_zones():
    """Earth analog zones: id, names, bounding box and whether their data is loaded."""
    return jsonify({zid: {"name": z["name"], "full_name": z["full_name"], "country": z["country"], "bbox": z["bbox"],
                          "available": data_loader.zone_available(zid), "default": zid == config.DEFAULT_ZONE}
                    for zid, z in config.EARTH_ZONES.items()})


@bp.get("/targets")
def get_targets():
    return jsonify({planet: list(locations) for planet, locations in config.TARGETS.items()})


#############################################
# GET /api/status
# Output: {"datasets": {body: {loaded, rows, available_features, ...}},
#          "features": [...], "engine": "ready"}
#############################################
def _memory_mb() -> dict:
    """Resident memory of this web process and of the whole container (Linux cgroup), in MB.
    Lets operators of small hosts (e.g. 512 MB) see their headroom; empty where not available."""
    out = {}
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith(("VmRSS:", "VmHWM:")):
                    out["web_rss" if line.startswith("VmRSS") else "web_peak"] = round(int(line.split()[1]) / 1024)
    except OSError:
        pass
    for path, key in (("/sys/fs/cgroup/memory.current", "container"), ("/sys/fs/cgroup/memory.peak", "container_peak"),
                      ("/sys/fs/cgroup/memory/memory.usage_in_bytes", "container"),
                      ("/sys/fs/cgroup/memory/memory.max_usage_in_bytes", "container_peak")):
        try:
            with open(path) as fh:
                out.setdefault(key, round(int(fh.read().strip()) / 2**20))
        except (OSError, ValueError):
            pass
    return out


@bp.get("/status")
def get_status():
    return jsonify({
        "datasets": data_loader.dataset_status(),
        "features": config.FEATURES,
        "data_dir": str(config.HARMONIZED_DATA_DIR),
        "engine": similarity_engine.ENGINE_STATUS,
        "memory_mb": _memory_mb(),
    })


#############################################
# POST /api/similarity
# Input : JSON {"planet": "mars" | "moon", "location": "<target name>",
#               "rover_mode": true|false (optional, default false),
#               "max_slope": 5-30 degrees (optional, default 15),
#               "cleaning": raw|standard|strict|robust (optional, default standard),
#               "data_mode": bundled|auto (optional, default bundled)}
# Output adds options {data_mode, cleaning}, cleaning_report and, for auto,
# live_evidence (live NASA characterization of the target, or "unavailable" + reason).
# Output: similarity result (score, ranking, explanation, map, method) + target info.
# Errors: 400 for invalid input, 503 if data is not available.
# The computation lives in services/analysis.py (shared with the AI assistant).
#############################################
@bp.post("/similarity")
def post_similarity():
    payload = request.get_json(silent=True) or {}
    try:
        planet, location, rover_mode, max_slope = analysis.validate(
            payload.get("planet"), payload.get("location"), payload.get("rover_mode", False), payload.get("max_slope"))
        zone = analysis.validate_zone(payload.get("zone"))          # optional, default: Atacama
        cleaning, data_mode = analysis.validate_options(payload.get("cleaning"), payload.get("data_mode"))
    except analysis.AnalysisInputError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    try:
        result = analysis.run(planet, location, rover_mode, max_slope, zone, cleaning)
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
    # The cached result is shared: build the response as a new dict, never mutate it.
    out = {**result, "options": {"data_mode": data_mode, "cleaning": cleaning}}
    if data_mode == "auto":
        from services import live_data
        out["live_evidence"] = live_data.for_target(planet, location)
    if result.get("status") == "error" and cleaning != "standard":
        # the chosen profile left too few comparable features: explain instead of failing silently
        return jsonify({**out, "message": f"{result.get('message')} The '{cleaning}' cleaning profile removed "
                        "too much data for this target; try 'standard'."}), 422
    return jsonify(out)
