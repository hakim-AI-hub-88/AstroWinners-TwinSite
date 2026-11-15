"""Agentic Auto Mode API (autonomous end-to-end missions). Owned by the auto lane; see docs/INTEGRATION_SPEC.md."""
from flask import Blueprint

bp = Blueprint("auto", __name__, url_prefix="/api/auto")
