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
@bp.get("/status")
def get_status():
    return jsonify({
        "datasets": data_loader.dataset_status(),
        "features": config.FEATURES,
        "data_dir": str(config.HARMONIZED_DATA_DIR),
        "engine": similarity_engine.ENGINE_STATUS,
    })


#############################################
# POST /api/similarity
# Input : JSON {"planet": "mars" | "moon", "location": "<target name>",
#               "rover_mode": true|false (optional, default false),
#               "max_slope": 5-30 degrees (optional, default 15)}
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
    except analysis.AnalysisInputError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    try:
        result = analysis.run(planet, location, rover_mode, max_slope, zone)
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
    return jsonify(result)
