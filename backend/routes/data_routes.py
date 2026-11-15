"""Data Hub API (bundled datasets, cleaning, downloads). Owned by the data lane; see docs/INTEGRATION_SPEC.md."""
from flask import Blueprint

bp = Blueprint("data", __name__, url_prefix="/api/data")
