#############################################################################
# API ROUTES - AI MISSION ASSISTANT
#
# Endpoints:
#   GET  /api/assistant/status -> is the assistant configured? which model?
#   POST /api/assistant        -> answer one question
#        body: {"question": "...",
#               "history": [{"role": "user"|"assistant", "content": "..."}],   (optional)
#               "context": {"planet", "location", "rover_mode", "max_slope", "selected_rank"}}  (optional)
#        200: {"answer", "tools_used", "model", "tokens"}
#        400: missing / too long question ; 503: assistant unavailable (no key, network, provider)
#
# The API key stays on the server (utils/config.py reads it from app/.env).
#############################################################################
from __future__ import annotations

import os

from flask import Blueprint, jsonify, request

from services import assistant
from utils import config

bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


@bp.get("/status")
def status():
    cfg = config.ASSISTANT
    return jsonify({"configured": bool(os.environ.get(cfg["api_key_env"], "").strip()),
                    "provider": "Groq", "model": cfg["model"]})


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
