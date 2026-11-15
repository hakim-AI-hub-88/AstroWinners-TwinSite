#############################################################################
# API ROUTES - MISSION REPORT (TWINSITE)
#
#   POST /api/report
#        body: {"planet", "location", "rover_mode", "max_slope", "use_ai": true,
#               "cleaning": raw|standard|strict|robust (optional), "data_mode": bundled|auto (optional)}
#        200: {"status": "ok", "facts", "narrative", "maps": {zone: "data:image/png;base64,..."}}
#        400: invalid target
#
# The browser combines this with the dashboard (tables, radar, atlas, photos)
# into a printable report page. The Groq key never leaves the server.
#############################################################################
from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import analysis, report

bp = Blueprint("report", __name__, url_prefix="/api/report")


@bp.post("")
def create():
    p = request.get_json(silent=True) or {}
    try:
        data = report.build(p.get("planet"), p.get("location"), bool(p.get("rover_mode")),
                            p.get("max_slope"), use_ai=bool(p.get("use_ai", True)),
                            cleaning=p.get("cleaning"), data_mode=p.get("data_mode"))
    except analysis.AnalysisInputError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    return jsonify({"status": "ok", **data})
