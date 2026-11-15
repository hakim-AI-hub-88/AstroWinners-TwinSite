#############################################################################
# PLATFORM PAGES + GATEWAYS
#
# Why this file exists:
#   One place for the site's page routes (landing, auto mode, data hub,
#   resources, sitemap, policy), the React mission console (/console) and the
#   reverse proxy to the TwinSite platform API (/v1 -> python -m twinsite.api).
#
#   In production nginx routes /v1 straight to the platform API; the proxy
#   here keeps a single origin for local development and simple hosts.
#############################################################################
from __future__ import annotations

import os
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, send_from_directory

from utils import config

bp = Blueprint("platform", __name__)

PLATFORM_API = os.environ.get("TWINSITE_API_URL", "http://127.0.0.1:8080").rstrip("/")
CONSOLE_DIST = Path(os.environ.get("TWINSITE_CONSOLE_DIST", config.APP_ROOT / "frontend" / "dist")).resolve()
REPO_URL = "https://github.com/hakim-AI-hub-88/AstroWinners-TwinSite"

# Public pages: (path, template, title, sitemap section, description)
PAGES = [
    ("/", "home.html", "Home", "Platform", "Overview of TwinSite and what it does."),
    ("/app", "index.html", "Mission Control", "Platform", "Interactive analog search: twin globes, ranking, science, report."),
    ("/auto", "auto.html", "Agentic Auto Mode", "Platform", "Autonomous end-to-end missions run by the 13 TwinSite agents."),
    ("/console/", None, "Mission Console", "Platform", "Advanced console: live NASA characterization, analog matching, portfolios, evidence."),
    ("/data", "data.html", "Data Hub", "Data & APIs", "Browse, clean, filter and download every TwinSite dataset; live NASA sources."),
    ("/resources", "resources.html", "Resources", "Guides & Docs", "Guides, documentation, architecture, stack, APIs, agents and algorithms."),
    ("/sitemap", "sitemap.html", "Sitemap", "Project", "Every page and endpoint of the platform."),
    ("/policy", "policy.html", "Policy & License", "Project", "Open-source license, data attribution, privacy and acceptable use."),
]


def site_context() -> dict:
    """Variables every page template can use (nav, footer, sitemap)."""
    return {"pages": PAGES, "repo_url": REPO_URL, "year": date.today().year}


@bp.app_context_processor
def _inject():
    return site_context()


def _render(template: str, active: str, **extra):
    return render_template(template, active=active, **extra)


@bp.get("/auto")
def auto_page():
    return _render("auto.html", "auto", targets=config.TARGETS, zones=config.EARTH_ZONES)


@bp.get("/data")
def data_page():
    return _render("data.html", "data")


@bp.get("/resources")
def resources_page():
    return _render("resources.html", "resources")


@bp.get("/sitemap")
def sitemap_page():
    return _render("sitemap.html", "sitemap")


@bp.get("/policy")
def policy_page():
    return _render("policy.html", "policy")


@bp.get("/sitemap.xml")
def sitemap_xml():
    base = request.url_root.rstrip("/")
    urls = "".join(f"<url><loc>{base}{p}</loc></url>" for p, *_ in PAGES)
    xml = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>'
    return Response(xml, mimetype="application/xml")


@bp.get("/robots.txt")
def robots():
    base = request.url_root.rstrip("/")
    return Response(f"User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /v1/\nSitemap: {base}/sitemap.xml\n",
                    mimetype="text/plain")


# ---------------------------------------------------------------------------
# React mission console (frontend/, built with Vite base "/console/")
# ---------------------------------------------------------------------------
@bp.get("/console")
@bp.get("/console/")
@bp.get("/console/<path:path>")
def console(path: str = ""):
    if not (CONSOLE_DIST / "index.html").is_file():
        return _render("console_missing.html", "console"), 503
    target = (CONSOLE_DIST / path).resolve() if path else None
    if target and target.is_file() and target.is_relative_to(CONSOLE_DIST):
        return send_from_directory(CONSOLE_DIST, path)
    return send_from_directory(CONSOLE_DIST, "index.html")      # SPA fallback


# ---------------------------------------------------------------------------
# /v1 reverse proxy -> TwinSite platform API (missions, agents, science, data)
# ---------------------------------------------------------------------------
_HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization",
        "proxy-authenticate", "content-encoding", "content-length", "host"}


@bp.route("/v1/<path:path>", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
def v1_proxy(path: str):
    url = f"{PLATFORM_API}/v1/{path}"
    if request.query_string:
        url += "?" + request.query_string.decode("latin-1")
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    body = request.get_data() if request.method in ("POST", "PUT") else None
    req = urllib.request.Request(url, data=body, headers=headers, method=request.method)
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            out_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in _HOP]
            return Response(resp.read(), status=resp.status, headers=out_headers)
    except urllib.error.HTTPError as err:
        out_headers = [(k, v) for k, v in err.headers.items() if k.lower() not in _HOP]
        return Response(err.read(), status=err.code, headers=out_headers)
    except (urllib.error.URLError, TimeoutError, ConnectionError) as err:
        return jsonify({"schema_version": "1.0", "error": {
            "code": "PLATFORM_API_UNAVAILABLE",
            "message": f"The TwinSite platform API is not reachable at {PLATFORM_API} ({err.__class__.__name__}). "
                       "Start it with `make dev` (or `python -m twinsite.api`).",
            "field": None}}), 503


def platform_get(path: str, timeout: float = 10.0):
    """Server-side helper for other blueprints: GET a /v1 JSON document or raise RuntimeError."""
    import json
    try:
        with urllib.request.urlopen(f"{PLATFORM_API}{path}", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as err:  # noqa: BLE001
        raise RuntimeError(f"platform API {path}: {err.__class__.__name__}: {err}") from None
