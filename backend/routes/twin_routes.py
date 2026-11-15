#############################################################################
# API ROUTES - INTERACTIVE GLOBES (TWINSITE)
#
#   GET /api/layers?body=mars|moon|atacama|merzouga
#        -> data layers available for that body / Earth zone (legend, PNG url, rectangle)
#   GET /api/layer/<body>/<feature>.png
#        -> colour PNG of one harmonized physical feature (display only)
#   GET /api/region-info?planet=moon&lat=34.9&lon=21.9&radius=50
#        -> can the selected region be analysed? cells, features, physical profile,
#           and the location name to send to /api/similarity
#############################################################################
from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from services import analysis, layers
from utils import config

bp = Blueprint("twin", __name__, url_prefix="/api")


@bp.get("/layers")
def list_layers():
    body = str(request.args.get("body", "")).lower()
    try:
        return jsonify({"status": "ok", "body": body, "layers": layers.catalogue(body),
                        "radius_km_choices": config.CUSTOM_TARGET["radius_km_choices"],
                        "default_radius_km": config.CUSTOM_TARGET["default_radius_km"]})
    except KeyError:
        return jsonify({"status": "error", "message": f"Unknown body '{body}'"}), 400


@bp.get("/layer/<body>/<feature>.png")
def layer_png(body: str, feature: str):
    try:
        png = layers.layer_png(body.lower(), feature)
    except KeyError:
        return jsonify({"status": "error", "message": "Unknown layer"}), 404
    return Response(png, mimetype="image/png", headers={"Cache-Control": "public, max-age=86400"})


@bp.get("/region-info")
def region_info():
    a = request.args
    try:
        info = layers.region_info(str(a.get("planet", "")).lower(), float(a.get("lat")), float(a.get("lon")),
                                  int(a.get("radius", config.CUSTOM_TARGET["default_radius_km"])))
    except (TypeError, ValueError) as exc:
        if isinstance(exc, analysis.AnalysisInputError):
            return jsonify({"status": "error", "message": str(exc)}), 400
        return jsonify({"status": "error", "message": "lat, lon and radius must be numbers"}), 400
    return jsonify({"status": "ok", **info})
