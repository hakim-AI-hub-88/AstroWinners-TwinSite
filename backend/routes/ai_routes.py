#############################################################################
# API ROUTES - AI PROVIDER STATUS
#
#   GET /api/ai/status -> {"enabled", "reason", "configured_count",
#                          "providers": [{id, name, configured, state, models, calls_today}],
#                          "assistant": {"tool_calling": bool}}
#
# Names and counts only: key values and account names never leave the server.
#############################################################################
from __future__ import annotations

from flask import Blueprint, jsonify

from services import ai_bridge

bp = Blueprint("ai", __name__, url_prefix="/api/ai")


@bp.get("/status")
def status():
    from services import assistant
    body = ai_bridge.status()
    body["assistant"] = {"tool_calling": assistant.groq_configured(),
                         "fallback": "multi-provider router without tools" if body["enabled"] else None}
    return jsonify(body)
