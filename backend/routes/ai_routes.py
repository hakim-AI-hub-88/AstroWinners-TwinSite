"""AI provider status (multi-provider free router). Owned by the ai lane; see docs/INTEGRATION_SPEC.md."""
from flask import Blueprint

bp = Blueprint("ai", __name__, url_prefix="/api/ai")
