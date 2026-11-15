#############################################################################
# API ROUTES - MACHINE LEARNING MODELS
#
# GET /api/ml?planet=mars&location=Jezero%20Crater&rover_mode=true&max_slope=15
#   -> PCA "planetary environment space" points, K-means terrain types and
#      their agreement with the similarity ranking (services/ml_models.py).
# 400: invalid target ; 503: data or scikit-learn not available.
#############################################################################
from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import analysis, ml_models

bp = Blueprint("ml", __name__, url_prefix="/api")


@bp.get("/ml")
def get_ml():
    args = request.args
    try:
        planet, location, rover_mode, max_slope = analysis.validate(
            args.get("planet"), args.get("location"),
            args.get("rover_mode", "false").lower() in ("1", "true", "yes"), args.get("max_slope"))
        zone = analysis.validate_zone(args.get("zone"))
    except analysis.AnalysisInputError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    try:
        result = analysis.run(planet, location, rover_mode, max_slope, zone)
        return jsonify({"status": "ok", **ml_models.insights(result)})
    except ImportError:
        return jsonify({"status": "error", "message": "scikit-learn is not installed (pip install -r requirements.txt)."}), 503
    except (FileNotFoundError, ValueError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
