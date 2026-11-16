#############################################################################
# API ROUTES - AGENTIC AUTO MODE
#
#   POST /api/auto/missions        body {target:{planet, location}|{planet, lat, lon, name, radius_km?},
#                                        objective, slope_limit?, zones?, data_mode, cleaning, ai}
#                                  202 {mission_id, status_url} | 400 invalid input | 429 too many running
#   GET  /api/auto/missions        {missions:[...recent], objectives, limits}
#   GET  /api/auto/missions/<id>   {mission_id, state, steps:[...], options, result} | 404
#
# The mission runs in a background thread (services/auto_mode.py); the page
# polls GET /api/auto/missions/<id> to follow the timeline.
#############################################################################
from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import auto_mode

bp = Blueprint("auto", __name__, url_prefix="/api/auto")


def _public(m: dict) -> dict:
    return {k: v for k, v in m.items() if k != "pid"}


@bp.post("/missions")
def create():
    payload = request.get_json(silent=True)
    try:
        m = auto_mode.create(payload)
    except auto_mode.MissionInputError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except auto_mode.MissionBusy as exc:
        return jsonify({"status": "error", "message": str(exc)}), 429, {"Retry-After": "30"}
    mid = m["mission_id"]
    return jsonify({"status": "accepted", "mission_id": mid, "status_url": f"/api/auto/missions/{mid}",
                    "options": m["options"]}), 202, {"Location": f"/api/auto/missions/{mid}"}


@bp.get("/missions")
def recent():
    try:
        limit = max(1, min(50, int(request.args.get("limit", 20))))
    except ValueError:
        return jsonify({"status": "error", "message": "limit must be an integer"}), 400
    return jsonify({"missions": auto_mode.list_recent(limit),
                    "objectives": {k: v["label"] for k, v in auto_mode.OBJECTIVES.items()},
                    "limits": {"max_concurrent": auto_mode.MAX_CONCURRENT,
                               "agents_timeout_s": int(auto_mode.AGENTS_TIMEOUT_S)}})


@bp.get("/missions/<mission_id>")
def one(mission_id: str):
    m = auto_mode.get(mission_id)
    if m is None:
        return jsonify({"status": "error", "message": "Unknown mission"}), 404
    return jsonify(_public(m))
