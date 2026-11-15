#############################################################################
# LIVE NASA DATA (data_mode = "auto")
#
# Why this file exists:
#   With data_mode="auto" a mission uses the bundled data_ready datasets AND a
#   live characterization of the target point by the TwinSite platform API
#   (POST /v1/science/characterize: MOLA / LOLA / Diviner / terrain tiles,
#   downloaded and processed on demand, with provenance).
#
# Contract (docs/INTEGRATION_SPEC.md):
#   characterize(planet, lon, lat, name) -> {status:"ok"|"unavailable", reason?,
#                                            observations:[...], source_products:[...], ...}
#   for_target(planet, location)         -> same, coordinates from the catalogue
#                                            target or the selected-region name
#   Never raises and never fabricates: any failure is status "unavailable"
#   with the reason returned by the platform (or the network error).
#
# Successful answers are cached per point (the dashboard asks once per Earth
# zone + once for the report); concurrent calls for the same point wait for
# the first one instead of downloading twice. Failures are not cached.
#############################################################################
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request

log = logging.getLogger(__name__)

TIMEOUT_S = 60
BODIES = {"mars": "Mars", "moon": "Moon", "earth": "Earth"}
MAX_ABS_LAT = 88.0                      # platform AOI limit
SOURCE = "TwinSite platform API · POST /v1/science/characterize"

_cache: dict[tuple, dict] = {}
_locks: dict[tuple, threading.Lock] = {}
_guard = threading.Lock()


def api_url() -> str:
    """Platform API base URL, read at call time (tests and deployments can change it)."""
    return os.environ.get("TWINSITE_API_URL", "http://127.0.0.1:8080").rstrip("/")


def _unavailable(reason: str, **extra) -> dict:
    return {"status": "unavailable", "reason": reason, "observations": [], "source_products": [],
            "source": SOURCE, **extra}


def _compact(o: dict) -> dict:
    keys = ("feature_id", "value", "unit", "qa_status", "missing_reason", "source_product", "source_url",
            "spatial_resolution_m", "analysis_scale_m", "observation_period", "quality_flags", "evidence_id")
    return {k: o.get(k) for k in keys if k in o}


def characterize(planet: str, lon: float, lat: float, name: str | None = None) -> dict:
    body = BODIES.get(str(planet or "").lower())
    point = {"body": body or planet, "longitude": lon, "latitude": lat, "name": name}
    if body is None:
        return _unavailable(f"Live characterization supports {sorted(BODIES)}; got '{planet}'.", target=point)
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return _unavailable("Longitude and latitude must be numbers.", target=point)
    if not (-180 <= lon <= 180 and -MAX_ABS_LAT <= lat <= MAX_ABS_LAT):
        return _unavailable(f"Point outside the live acquisition domain (longitude -180..180, latitude "
                            f"-{MAX_ABS_LAT:.0f}..{MAX_ABS_LAT:.0f}).", target=point)
    key = (body, round(lon, 4), round(lat, 4))
    if key in _cache:
        return {**_cache[key], "cached": True}
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        if key in _cache:
            return {**_cache[key], "cached": True}
        out = _fetch(body, lon, lat, name, point)
        if out["status"] == "ok":
            _cache[key] = out
        return out


def _fetch(body, lon, lat, name, point) -> dict:
    url = f"{api_url()}/v1/science/characterize"
    payload = json.dumps({"body": body, "longitude": lon, "latitude": lat, "name": (name or "")[:80]}).encode()
    req = urllib.request.Request(url, data=payload, method="POST", headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        try:
            msg = (json.loads(err.read().decode("utf-8")).get("error") or {}).get("message")
        except Exception:  # noqa: BLE001
            msg = None
        hint = (" The running platform API has no /v1/science/characterize route (older build): restart it "
                "from this repository." if err.code == 404 else "")
        return _unavailable(f"Platform API answered HTTP {err.code}: {msg or err.reason}.{hint}", target=point)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
        reason = getattr(err, "reason", err)
        return _unavailable(f"Platform API not reachable at {api_url()} ({type(err).__name__}: {reason}). "
                            "Start it with `make dev` or `python -m twinsite.api`.", target=point)
    except ValueError as err:
        return _unavailable(f"Platform API returned invalid JSON ({err}).", target=point)
    obs = [_compact(o) for o in doc.get("observations") or []]
    products = sorted({o.get("source_product") for o in obs if o.get("source_product")})
    measured = [o for o in obs if o.get("value") is not None]
    if not measured:
        return _unavailable("The platform returned no measured value for this point.", target=point,
                            acquisition_errors=doc.get("acquisition_errors") or [])
    return {
        "status": "ok", "source": SOURCE, "target": point,
        "site_id": doc.get("site_id"), "name": doc.get("name"), "body": doc.get("body"),
        "longitude": doc.get("longitude"), "latitude": doc.get("latitude"), "aoi": doc.get("aoi"),
        "analysis_scale_m": doc.get("analysis_scale_m"),
        "observations": obs, "source_products": products,
        "acquisition_errors": doc.get("acquisition_errors") or [],
        "elapsed_s": round(time.time() - t0, 1),
        "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "note": "Live AOI statistics (platform analysis scale); shown as evidence next to the bundled ~11 km "
                "analysis, never mixed into the similarity score.",
    }


def for_target(planet: str, location: str) -> dict:
    """Live evidence for a catalogue target or a selected-region name (coordinates from analysis.target_def)."""
    from services import analysis
    t = analysis.target_def(str(planet or "").lower(), location)
    if t is None:
        return _unavailable(f"Unknown target '{location}' for {planet}.")
    return characterize(planet, t["lon"], t["lat"], location)
