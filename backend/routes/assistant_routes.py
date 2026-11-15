#############################################################################
# API ROUTES - AI MISSION ASSISTANT
#
# Endpoints:
#   GET  /api/assistant/status -> is the assistant configured? which path/model?
#   POST /api/assistant        -> answer one question
#        body: {"question": "...",
#               "history": [{"role": "user"|"assistant", "content": "..."}],   (optional)
#               "context": {"planet", "location", "rover_mode", "max_slope", "selected_rank"}}  (optional)
#        200: {"answer", "tools_used", "model", "provider", "tokens", "mode"}
#        400: missing / too long question ; 503: assistant unavailable (no provider reachable)
#
# Paths: Groq tool-calling when a Groq key exists (env or the platform secret
# file); otherwise the free multi-provider router answers without tools.
# Keys stay on the server.
#############################################################################
from __future__ import annotations

from flask import Blueprint, jsonify, request

from services import ai_bridge, assistant
from utils import config

bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


@bp.get("/status")
def status():
    cfg = config.ASSISTANT
    if assistant.groq_configured():
        return jsonify({"configured": True, "provider": "Groq", "model": cfg["model"], "mode": "groq_tools"})
    st = ai_bridge.status()
    names = [p["name"] for p in st["providers"] if p["configured"]]
    return jsonify({"configured": bool(st["enabled"]), "provider": "free AI router",
                    "model": ", ".join(names) + " (no tools)" if names else "", "mode": "router_no_tools",
                    "reason": None if st["enabled"] else st["reason"]})


@bp.post("")
def ask():
    payload = request.get_json(silent=True) or {}
    question = str(payload.get("question", "")).strip()
    if not question:
        return jsonify({"status": "error", "message": "Please type a question."}), 400
    if len(question) > config.ASSISTANT["max_question_chars"]:
        return jsonify({"status": "error", "message": "Question too long."}), 400
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    try:
        result = assistant.answer(question, payload.get("history"), context)
    except assistant.AssistantUnavailable as exc:
        return jsonify({"status": "error", "message": str(exc)}), 503
    return jsonify({"status": "ok", **result})
