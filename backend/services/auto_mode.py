#############################################################################
# AGENTIC AUTO MODE  (autonomous end-to-end missions)
#
# Why this file exists:
#   One click runs the whole TwinSite workflow for a Moon / Mars target and
#   records every step honestly:
#     plan    -> objective -> rover filter / slope limit, zones, data mode
#     acquire -> bundled NASA datasets (data_ready) + live NASA acquisition of
#                the target point through the platform gateway (data_mode=auto)
#     clean   -> cleaning profile (raw / standard / strict / robust)
#     analyze -> similarity engine on every selected Earth zone
#     agents  -> platform mission /v1/missions/match (13 agents A01-A13, AI or
#                deterministic), polled until terminal; agent trace stored
#     report  -> facts + facts-anchored narrative (services.report)
#   A step that cannot run is "skipped" or "failed" with its reason; the
#   others still run. Nothing is invented: every number shown comes from the
#   bundled analysis or the platform API.
#
# Storage: one JSON file per mission under $TWINSITE_DATA_DIR/auto/
#   (default <repo>/.runtime/auto/), written atomically. One background
#   thread per mission; at most MAX_CONCURRENT run at once.
#############################################################################
from __future__ import annotations

import inspect
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

from utils import config

log = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[2]
MAX_CONCURRENT = int(os.environ.get("TWINSITE_AUTO_MAX_CONCURRENT", "2"))
AGENTS_TIMEOUT_S = float(os.environ.get("TWINSITE_AUTO_AGENTS_TIMEOUT_S", "360"))
SUBMIT_TIMEOUT_S = 180.0
POLL_S = 3.0
TERMINAL = ("completed", "completed_with_limits", "failed", "cancelled")

OBJECTIVES = {
    "rover_test": {"label": "Rover mobility test", "rover_mode": True,
                   "why": "rover filter on: only regions drivable under the slope limit are proposed"},
    "eva_training": {"label": "EVA / crew training", "rover_mode": True,
                     "why": "rover filter on (walkable terrain under the slope limit)"},
    "habitat": {"label": "Habitat / long-duration analog", "rover_mode": False,
                "why": "all regions ranked; terrain and thermal similarity drive the choice"},
    "instrument_calibration": {"label": "Instrument calibration", "rover_mode": False,
                               "why": "all regions ranked; surface-property similarity drives the choice"},
    "general": {"label": "General analog search", "rover_mode": False, "why": "all regions ranked"},
}
DATA_MODES = ("bundled", "auto")
CLEANING = ("standard", "raw", "strict", "robust")
STEPS = [("plan", "Plan mission"), ("acquire", "Acquire data"), ("clean", "Clean data"),
         ("analyze", "Analyze Earth zones"), ("agents", "Run the 13 agents"), ("report", "Write report")]
_ID_RE = re.compile(r"^am-[0-9a-f]{12}$")
_BODY = {"mars": "Mars", "moon": "Moon"}


class MissionInputError(ValueError):
    """Invalid mission request (HTTP 400)."""


class MissionBusy(RuntimeError):
    """Too many auto missions running (HTTP 429)."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def api_url() -> str:
    return os.environ.get("TWINSITE_API_URL", "http://127.0.0.1:8080").rstrip("/")


def store_dir() -> Path:
    d = Path(os.environ.get("TWINSITE_DATA_DIR") or APP_ROOT / ".runtime") / "auto"
    d.mkdir(parents=True, exist_ok=True)
    return d


#############################################
# INPUT VALIDATION
#############################################
def _num(value, name, lo, hi) -> float:
    try:
        x = float(value)
    except (TypeError, ValueError):
        raise MissionInputError(f"{name} must be a number") from None
    if x != x or not lo <= x <= hi:
        raise MissionInputError(f"{name} must be between {lo} and {hi}")
    return x


def validate(payload) -> dict:
    """Normalise a request body into mission options or raise MissionInputError."""
    if not isinstance(payload, dict):
        raise MissionInputError("JSON object body required")
    target = payload.get("target")
    if not isinstance(target, dict):
        raise MissionInputError("target must be an object: {planet, location} or {planet, lat, lon, name}")
    planet = str(target.get("planet") or "").lower()
    if planet not in _BODY:
        raise MissionInputError("target.planet must be 'mars' or 'moon'")
    radius = int(config.CUSTOM_TARGET["default_radius_km"])
    if target.get("location") not in (None, ""):
        location = str(target["location"])
        if location not in config.TARGETS[planet]:
            raise MissionInputError(f"Unknown location '{location}' for {planet}; choose one of {list(config.TARGETS[planet])} "
                                    "or give lat/lon")
        t = config.TARGETS[planet][location]
        lat, lon, name, custom = float(t["lat"]), float(t["lon"]), location, False
    else:
        if "lat" not in target or "lon" not in target:
            raise MissionInputError("target needs a preset location or numeric lat and lon")
        lat = _num(target.get("lat"), "target.lat", -88, 88)
        lon = _num(target.get("lon"), "target.lon", -180, 180)
        if target.get("radius_km") is not None:
            radius = int(_num(target["radius_km"], "target.radius_km", 1, 1000))
            if radius not in config.CUSTOM_TARGET["radius_km_choices"]:
                raise MissionInputError(f"target.radius_km must be one of {config.CUSTOM_TARGET['radius_km_choices']}")
        name = re.sub(r"[^\w .,'()\-]", "", str(target.get("name") or ""))[:60].strip() or \
            f"{_BODY[planet]} point {lat:.2f}, {lon:.2f}"
        from services import analysis
        location, custom = analysis.custom_location(lat, lon, radius), True
    objective = str(payload.get("objective") or "general")
    if objective not in OBJECTIVES:
        raise MissionInputError(f"objective must be one of {list(OBJECTIVES)}")
    lo, hi = config.ROVER["slope_limits"]
    slope = config.ROVER["default_max_slope_deg"] if payload.get("slope_limit") in (None, "") else \
        _num(payload.get("slope_limit"), "slope_limit", lo, hi)
    zones = payload.get("zones") or list(config.EARTH_ZONES)
    if not isinstance(zones, list) or not zones or any(z not in config.EARTH_ZONES for z in zones):
        raise MissionInputError(f"zones must be a non-empty list drawn from {list(config.EARTH_ZONES)}")
    zones = list(dict.fromkeys(zones))
    data_mode = str(payload.get("data_mode") or "bundled")
    if data_mode not in DATA_MODES:
        raise MissionInputError(f"data_mode must be one of {list(DATA_MODES)}")
    cleaning = str(payload.get("cleaning") or "standard")
    if cleaning not in CLEANING:
        raise MissionInputError(f"cleaning must be one of {list(CLEANING)}")
    ai = payload.get("ai", True)
    if not isinstance(ai, bool):
        raise MissionInputError("ai must be true or false")
    return {"target": {"planet": planet, "location": location, "name": name, "lat": round(lat, 4), "lon": round(lon, 4),
                       "custom": custom, "radius_km": radius},
            "objective": objective, "rover_mode": OBJECTIVES[objective]["rover_mode"], "slope_limit": float(slope),
            "zones": zones, "data_mode": data_mode, "cleaning": cleaning, "ai": ai}


#############################################
# PERSISTENCE
#############################################
_LOCK = threading.Lock()
_ACTIVE: dict[str, threading.Thread] = {}


def _path(mid: str) -> Path:
    return store_dir() / f"{mid}.json"


def _save(m: dict) -> None:
    m["updated"] = _now()
    p = _path(m["mission_id"])
    tmp = p.with_suffix(f".{uuid.uuid4().hex[:6]}.tmp")
    tmp.write_text(json.dumps(m, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, p)


def _load(mid: str) -> dict | None:
    try:
        return json.loads(_path(mid).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _pid_alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _interrupted(m: dict) -> bool:
    """Running mission whose owner thread is gone: same process but no thread, or owner process dead."""
    if m.get("state") != "running" or m["mission_id"] in _ACTIVE:
        return False
    pid = m.get("pid")
    return pid == os.getpid() or not _pid_alive(pid)


def _reconcile(m: dict) -> dict:
    """A 'running' mission without a live owner thread was interrupted (server restart)."""
    if _interrupted(m):
        for s in m["steps"]:
            if s["state"] in ("pending", "running"):
                s.update(state="failed" if s["state"] == "running" else "skipped", finished=s.get("finished") or _now(),
                         detail=(s.get("detail") or "") + " Interrupted: the server restarted while this step was running.")
        m["state"] = "failed"
        m["error"] = "Interrupted by a server restart; launch the mission again."
        _save(m)
    return m


def get(mid: str) -> dict | None:
    if not _ID_RE.match(str(mid or "")):
        return None
    m = _load(mid)
    return _reconcile(m) if m else None


def list_recent(limit: int = 20) -> list[dict]:
    files = sorted(store_dir().glob("am-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
    out = []
    for f in files:
        m = get(f.stem)
        if not m:
            continue
        res = m.get("result") or {}
        out.append({"mission_id": m["mission_id"], "state": m["state"], "created": m["created"], "updated": m.get("updated"),
                    "target": m["options"]["target"], "objective": m["options"]["objective"],
                    "ai": m["options"]["ai"], "data_mode": m["options"]["data_mode"], "cleaning": m["options"]["cleaning"],
                    "steps": {s["id"]: s["state"] for s in m["steps"]},
                    "best": res.get("best"), "platform_run_id": res.get("platform_run_id")})
    return out


def create(payload) -> dict:
    opts = validate(payload)
    with _LOCK:
        alive = [k for k, t in _ACTIVE.items() if t.is_alive()]
        for k in list(_ACTIVE):
            if k not in alive:
                _ACTIVE.pop(k, None)
        if len(alive) >= MAX_CONCURRENT:
            raise MissionBusy(f"{len(alive)} auto missions already running (limit {MAX_CONCURRENT}); try again shortly")
        mid = "am-" + uuid.uuid4().hex[:12]
        m = {"mission_id": mid, "state": "running", "created": _now(), "updated": None, "pid": os.getpid(),
             "options": opts, "steps": [{"id": i, "label": lbl, "state": "pending", "started": None, "finished": None,
                                         "duration_s": None, "detail": None} for i, lbl in STEPS],
             "result": {"similarity": {}, "top_regions": [], "cleaning_report": None, "live_evidence": None,
                        "platform_run_id": None, "agents": [], "report_url": None, "links": {}}, "error": None}
        th = threading.Thread(target=_run, args=(m,), name=f"auto-{mid}", daemon=True)
        _ACTIVE[mid] = th
        _save(m)
    th.start()
    return m


#############################################
# STEP RUNNER
#############################################
class _Skip(Exception):
    pass


def _step(m: dict, sid: str) -> dict:
    return next(s for s in m["steps"] if s["id"] == sid)


def _run_step(m: dict, sid: str, fn) -> bool:
    s = _step(m, sid)
    s.update(state="running", started=_now())
    t0 = time.monotonic()
    _save(m)
    try:
        detail = fn(m, s)
        s.update(state="completed", detail=detail if detail is not None else s.get("detail"))
    except _Skip as exc:
        s.update(state="skipped", detail=str(exc))
    except Exception as exc:  # noqa: BLE001 - a failing step must not stop the mission
        log.warning("auto %s step %s failed: %s", m["mission_id"], sid, exc, exc_info=not isinstance(exc, RuntimeError))
        s.update(state="failed", detail=f"{exc}" if isinstance(exc, RuntimeError) else f"{exc.__class__.__name__}: {exc}")
    s.update(finished=_now(), duration_s=round(time.monotonic() - t0, 2))
    _save(m)
    return s["state"] == "completed"


def _run(m: dict) -> None:
    try:
        for sid, fn in (("plan", _plan), ("acquire", _acquire), ("clean", _clean), ("analyze", _analyze),
                        ("agents", _agents), ("report", _report)):
            _run_step(m, sid, fn)
        states = {s["id"]: s["state"] for s in m["steps"]}
        ok = states["analyze"] == "completed" or states["agents"] == "completed"
        m["state"] = "completed" if ok else "failed"
        if not ok:
            m["error"] = "Neither the bundled analysis nor the platform agents produced a result (see step details)."
    except Exception as exc:  # noqa: BLE001
        log.exception("auto mission crashed")
        m["state"], m["error"] = "failed", f"{exc.__class__.__name__}: {exc}"
    finally:
        _save(m)
        with _LOCK:
            _ACTIVE.pop(m["mission_id"], None)


# ---------------------------------------------------------------- plan
def _plan(m: dict, s: dict) -> str:
    o = m["options"]
    t = o["target"]
    obj = OBJECTIVES[o["objective"]]
    zones = ", ".join(config.EARTH_ZONES[z]["full_name"] for z in o["zones"])
    plan = [f"Target: {t['name']} ({_BODY[t['planet']]}, lat {t['lat']}, lon {t['lon']}"
            + (f", {t['radius_km']} km region" if t["custom"] else "") + ").",
            f"Objective: {obj['label']} -> {obj['why']} (slope limit {o['slope_limit']} deg).",
            f"Earth zones: {zones}.",
            "Data: bundled NASA datasets" + (" + live NASA acquisition of the target point." if o["data_mode"] == "auto" else "."),
            f"Cleaning profile: {o['cleaning']}.",
            "Agents: platform mission with " + ("AI-powered analysis (free providers, deterministic fallback)."
                                                if o["ai"] else "simple (deterministic) analysis.")]
    m["result"]["plan"] = plan
    return " ".join(plan)


# ---------------------------------------------------------------- acquire
def _post_json(path: str, body: dict, headers=None, timeout=60.0):
    req = urllib.request.Request(api_url() + path, data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", **(headers or {})})
    return _send(req, timeout)


def _get_json(path: str, timeout=20.0):
    return _send(urllib.request.Request(api_url() + path), timeout)


def _send(req, timeout):
    """(status, json) or raise RuntimeError with an explicit, user-readable reason."""
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as err:
        try:
            e = json.loads(err.read().decode("utf-8")).get("error") or {}
            msg = f"{e.get('code', 'HTTP_ERROR')}: {e.get('message', '')}".strip()
        except Exception:  # noqa: BLE001
            msg = "no error body"
        raise RuntimeError(f"platform API returned HTTP {err.code} ({msg})") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as err:
        reason = getattr(err, "reason", err)
        raise RuntimeError(f"platform API not reachable at {api_url()} ({reason})") from None


def _compact_obs(obs: list) -> list:
    keep = ("feature_id", "value", "unit", "qa_status", "source_id", "product_id", "method")
    return [{k: o.get(k) for k in keep if k in o} for o in (obs or [])][:40]


def live_characterize(planet: str, lon: float, lat: float, name: str) -> dict:
    """Live NASA evidence for the target point: services.live_data (data lane) when present, else the gateway."""
    try:
        from services import live_data  # type: ignore
        return live_data.characterize(planet, lon, lat, name)
    except ImportError:
        pass
    try:
        _, doc = _post_json("/v1/science/characterize",
                            {"body": _BODY[planet], "longitude": lon, "latitude": lat, "name": name}, timeout=SUBMIT_TIMEOUT_S)
    except RuntimeError as exc:
        return {"status": "unavailable", "reason": str(exc), "observations": [], "source_products": []}
    obs = doc.get("observations") or []
    valid = [o for o in obs if o.get("value") is not None]
    return {"status": "ok" if valid else "unavailable",
            "reason": None if valid else "the gateway returned no valid measurement for this point",
            "site_id": doc.get("site_id"), "analysis_scale_m": doc.get("analysis_scale_m"),
            "observations": _compact_obs(obs), "acquisition_errors": doc.get("acquisition_errors") or [],
            "source_products": sorted({o.get("source_id") or o.get("product_id") for o in obs
                                       if o.get("source_id") or o.get("product_id")})[:20]}


def _acquire(m: dict, s: dict) -> str:
    from services import data_loader
    o, t = m["options"], m["options"]["target"]
    parts, bundled = [], {}
    try:
        df = data_loader.LOADERS[t["planet"]]()
        bundled[t["planet"]] = {"status": "ok", "rows": int(len(df))}
        parts.append(f"{_BODY[t['planet']]} bundled dataset: {len(df):,} cells.")
    except Exception as exc:  # noqa: BLE001
        bundled[t["planet"]] = {"status": "unavailable", "reason": f"{exc.__class__.__name__}: {exc}"}
        parts.append(f"{_BODY[t['planet']]} bundled dataset unavailable ({exc.__class__.__name__}).")
    for z in o["zones"]:
        try:
            n = len(data_loader.load_zone(z, "normalized"))
            bundled[z] = {"status": "ok", "rows": int(n)}
            parts.append(f"{config.EARTH_ZONES[z]['name']}: {n:,} cells.")
        except Exception as exc:  # noqa: BLE001
            bundled[z] = {"status": "unavailable", "reason": f"{exc.__class__.__name__}: {exc}"}
            parts.append(f"{config.EARTH_ZONES[z]['name']} unavailable ({exc.__class__.__name__}).")
    if t["custom"] and bundled[t["planet"]]["status"] == "ok":
        try:
            from services import layers
            info = layers.region_info(t["planet"], t["lat"], t["lon"], t["radius_km"])
            bundled["target_region"] = {k: info[k] for k in ("cells", "features_available", "analysable", "reason")}
            parts.append(f"Selected region: {info['cells']} cells, "
                         + ("analysable." if info["analysable"] else f"not analysable ({info['reason']})."))
        except Exception as exc:  # noqa: BLE001
            bundled["target_region"] = {"analysable": None, "reason": str(exc)}
    m["result"]["bundled"] = bundled
    if o["data_mode"] == "auto":
        s["detail"] = " ".join(parts) + " Acquiring live NASA data for the target point (can take a few minutes)..."
        _save(m)
        live = live_characterize(t["planet"], t["lon"], t["lat"], t["name"])
        m["result"]["live_evidence"] = live
        if live.get("status") == "ok":
            parts.append(f"Live NASA acquisition: {sum(1 for x in live.get('observations', []) if x.get('value') is not None)} "
                         "valid measurements at the target point.")
        else:
            parts.append(f"Live NASA acquisition unavailable: {live.get('reason')}.")
    else:
        parts.append("Live acquisition not requested (bundled data mode).")
    have_target = bundled[t["planet"]]["status"] == "ok"
    have_zone = any(bundled[z]["status"] == "ok" for z in o["zones"])
    live_ok = (m["result"].get("live_evidence") or {}).get("status") == "ok"
    if not (have_target and have_zone) and not live_ok:
        raise RuntimeError("No usable data: " + " ".join(parts))
    return " ".join(parts)


# ---------------------------------------------------------------- clean
def _clean(m: dict, s: dict) -> str:
    o = m["options"]
    try:
        from services import cleaning  # type: ignore  (data lane)
    except ImportError:
        if o["cleaning"] == "standard":
            raise _Skip("Cleaning module not available in this build; the analysis uses the standard engine behaviour "
                        "(quality flags lower weights, incomplete cells excluded).") from None
        raise _Skip(f"Cleaning profile '{o['cleaning']}' requested but the cleaning module is not available in this build; "
                    "the standard engine behaviour is used instead.") from None
    from services import analysis, data_loader
    reports = {}
    features = [f for f in config.FEATURES if f not in config.SIMILARITY["excluded"]]
    # Clean exactly what the scoring cleans: the target window (not the whole 1.8M-cell planet grid,
    # which would need a full in-memory copy) and every selected Earth zone.
    planet = o["target"]["planet"]
    t = analysis.target_def(planet, o["target"]["location"])
    if t is None:
        raise RuntimeError(f"Unknown target location {o['target']['location']!r}")

    def target_window():
        return data_loader.extract_target_window(data_loader.LOADERS[planet](), t["lat"], t["lon"], t["window_km"],
                                                 config.BODY_RADIUS_M[planet])

    for key, loader in [(f"{planet} target window ({t['window_km']:g} km)", target_window)] + \
            [(z, (lambda z=z: data_loader.load_zone(z, "normalized"))) for z in o["zones"]]:
        try:
            _, rep = cleaning.apply(loader(), o["cleaning"], features)
            reports[key] = rep
        except Exception as exc:  # noqa: BLE001
            reports[key] = {"error": f"{exc.__class__.__name__}: {exc}"}
    m["result"]["cleaning_report"] = {"profile": o["cleaning"], "datasets": reports}
    ok = {k: r for k, r in reports.items() if "error" not in r}
    if not ok:
        raise RuntimeError("Cleaning failed on every dataset: " + "; ".join(f"{k}: {r['error']}" for k, r in reports.items()))
    return f"Profile '{o['cleaning']}': " + "; ".join(
        f"{k} {r.get('rows_in', '?')} -> {r.get('rows_out', '?')} rows" for k, r in ok.items())


# ---------------------------------------------------------------- analyze
def run_analysis(planet, location, rover_mode, max_slope, zone, cleaning="standard"):
    """services.analysis.run with `cleaning` passed only when the installed engine supports it."""
    from services import analysis
    try:
        params = inspect.signature(analysis.run).parameters
    except (TypeError, ValueError):
        params = {}
    if "cleaning" in params:
        return analysis.run(planet, location, rover_mode, max_slope, zone, cleaning=cleaning)
    return analysis.run(planet, location, rover_mode, max_slope, zone)


def _zone_summary(res: dict) -> dict:
    m = res.get("method") or {}
    return {"zone": res["zone"]["full_name"], "best_score": res.get("score"), "confidence": res.get("confidence"),
            "cells_scored": m.get("cells_scored"), "features_used": m.get("features_used"),
            "features_skipped": m.get("features_skipped"),
            "validation": ((res.get("validation") or {}).get("summary")),
            "cleaning_report": res.get("cleaning_report"), "options": res.get("options"),
            "top_regions": [{"rank": r["rank"], "lat": r["lat"], "lon": r["lon"], "score": r["score"],
                             "confidence": r.get("confidence"), "drivable_pct": r.get("accessible_pct"),
                             "exact_point": r.get("refined"),
                             "closest": (r.get("explanation") or {}).get("matches"),
                             "differs": (r.get("explanation") or {}).get("differs")}
                            for r in (res.get("ranking") or [])[:5]]}


def _analyze(m: dict, s: dict) -> str:
    o, t = m["options"], m["options"]["target"]
    region = (m["result"].get("bundled") or {}).get("target_region")
    if region and region.get("analysable") is False:
        raise _Skip(f"Bundled analysis not possible for this region: {region.get('reason')}")
    if (m["result"].get("bundled") or {}).get(t["planet"], {}).get("status") == "unavailable":
        raise _Skip(f"{_BODY[t['planet']]} bundled dataset unavailable on this server; "
                    "the platform agents step uses live NASA data instead.")
    out, errors = {}, {}
    for z in o["zones"]:
        try:
            out[z] = _zone_summary(run_analysis(t["planet"], t["location"], o["rover_mode"], o["slope_limit"], z, o["cleaning"]))
        except Exception as exc:  # noqa: BLE001
            errors[z] = f"{exc.__class__.__name__}: {exc}"
    m["result"]["similarity"] = out
    m["result"]["analysis_errors"] = errors
    if not m["result"].get("cleaning_report"):
        reps = {z: v["cleaning_report"] for z, v in out.items() if v.get("cleaning_report")}
        if reps:
            m["result"]["cleaning_report"] = {"profile": o["cleaning"], "datasets": reps}
    top = [dict(r, zone=z, zone_name=v["zone"]) for z, v in out.items() for r in v["top_regions"]]
    top.sort(key=lambda r: -(r["score"] if r["score"] is not None else -1))
    m["result"]["top_regions"] = top[:10]
    if top:
        b = top[0]
        m["result"]["best"] = {"zone": b["zone_name"], "score": b["score"], "lat": b["lat"], "lon": b["lon"], "source": "bundled"}
    if not out:
        raise RuntimeError("Analysis failed in every zone: " + "; ".join(f"{z}: {e}" for z, e in errors.items()))
    msg = "; ".join(f"{v['zone']}: best {v['best_score']} / 100" for v in out.values())
    return msg + ("" if not errors else " | failed: " + "; ".join(f"{z}: {e}" for z, e in errors.items()))


# ---------------------------------------------------------------- agents
def _agent_rows(trace: dict) -> list[dict]:
    rows = []
    for r in trace.get("records") or []:
        inf = r.get("inference") or {}
        rows.append({"agent_id": r.get("agent_id"), "role": r.get("role"), "phase": r.get("phase"),
                     "execution": r.get("execution"), "purpose": r.get("purpose"),
                     "summary": str(r.get("summary") or "")[:600],
                     "outcome": (r.get("agent_result") or {}).get("status"),
                     "provider": inf.get("provider"), "model": inf.get("model"), "cached": inf.get("cached"),
                     "latency_ms": inf.get("latency_ms"), "error": inf.get("error")})
    return rows


def _agents(m: dict, s: dict) -> str:
    o, t = m["options"], m["options"]["target"]
    mode = "ai" if o["ai"] else "simple"
    s["detail"] = f"Submitting a {mode} mission to the platform ({api_url()})..."
    _save(m)
    _, acc = _post_json(f"/v1/missions/match?analysis_mode={mode}",
                        {"target": {"body": _BODY[t["planet"]], "longitude": t["lon"], "latitude": t["lat"], "name": t["name"]}},
                        headers={"Idempotency-Key": f"auto-{m['mission_id']}"}, timeout=SUBMIT_TIMEOUT_S)
    run_id = acc["run_id"]
    res = m["result"]
    res["platform_run_id"] = run_id
    res["platform"] = {"analysis_mode": mode, "prerank": acc.get("prerank") or [],
                       "excluded_extent_incompatible": acc.get("excluded_extent_incompatible") or [],
                       "dataset_id": acc.get("dataset_id")}
    res["links"] = {"console": f"/console/analysis/{run_id}", "platform_report": f"/v1/missions/{run_id}/report",
                    "platform_status": f"/v1/missions/{run_id}"}
    deadline = time.monotonic() + AGENTS_TIMEOUT_S
    after, status, events, trace, st, grace = 0, "queued", [], {}, {}, 3
    while time.monotonic() < deadline:
        try:
            _, st = _get_json(f"/v1/missions/{run_id}")
            status = st.get("status", status)
            _, new = _get_json(f"/v1/missions/{run_id}/events?after={after}")
            for e in new or []:
                after = max(after, int(e.get("sequence") or after))
                events.append({"seq": e.get("sequence"), "phase": e.get("phase"), "state": e.get("state"),
                               "summary": str(e.get("summary") or "")[:300], "at": e.get("timestamp")})
            _, trace = _get_json(f"/v1/missions/{run_id}/agents")
        except RuntimeError as exc:
            s["detail"] = f"Run {run_id}: polling error ({exc}); retrying."
            _save(m)
            time.sleep(POLL_S)
            continue
        res["platform"]["events"] = events[-40:]
        res["agents"] = _agent_rows(trace)
        last = events[-1]["summary"] if events else "queued"
        s["detail"] = f"Run {run_id} {status}: {last}"
        _save(m)
        if status in ("failed", "cancelled"):
            break                                  # report the platform's own error below
        if status in TERMINAL:
            if trace.get("records") or not trace.get("pending"):
                break
            grace -= 1                             # trace may land just after the run commits
            if grace <= 0:
                break
        time.sleep(POLL_S)
    else:
        raise RuntimeError(f"Platform run {run_id} still '{status}' after {int(AGENTS_TIMEOUT_S)} s; "
                           "follow it in the console. The agent trace above is partial.")
    res["platform"]["status"] = status
    res["platform"]["ai"] = {k: trace.get(k) for k in ("analysis_mode", "ai_available", "ai_calls_attempted",
                                                        "ai_roles_executed", "fallback_reason")}
    if status in ("completed", "completed_with_limits"):
        try:
            _, result = _get_json(f"/v1/missions/{run_id}/result", timeout=30)
            sites = sorted((x for x in result.get("sites") or [] if x.get("eligible")),
                           key=lambda x: -(x.get("observed_similarity") or 0))
            res["platform"]["top_sites"] = [{"site_id": x.get("id"), "name": x.get("name"),
                                             "similarity": x.get("observed_similarity"), "coverage": x.get("coverage")}
                                            for x in sites[:5]]
            res["platform"]["limitations"] = (result.get("limitations") or [])[:6]
            res["report_url"] = f"/v1/missions/{run_id}/report"
            if sites and not res.get("best"):
                res["best"] = {"zone": sites[0].get("name"), "score": round(100 * (sites[0].get("observed_similarity") or 0), 1),
                               "source": "platform"}
        except RuntimeError as exc:
            res["platform"]["result_error"] = str(exc)
    n_ai = sum(1 for a in res["agents"] if a["execution"] in ("ai", "ai_cached"))
    summary = (f"Run {run_id} {status}: {len(res['agents'])} agent records "
               f"({n_ai} AI, {sum(1 for a in res['agents'] if a['execution'] == 'deterministic')} deterministic, "
               f"{sum(1 for a in res['agents'] if a['execution'] in ('failed', 'skipped', 'fallback'))} failed/skipped).")
    if status in ("failed", "cancelled"):
        raise RuntimeError(summary + (f" Error: {st.get('error')}" if st.get("error") else ""))
    return summary


# ---------------------------------------------------------------- report
def build_report(planet, location, rover_mode, max_slope, use_ai, cleaning, data_mode):
    """services.report.build, passing cleaning/data_mode only when the installed version accepts them."""
    from services import report
    params = inspect.signature(report.build).parameters
    kw = {"use_ai": use_ai}
    if "cleaning" in params:
        kw["cleaning"] = cleaning
    if "data_mode" in params:
        kw["data_mode"] = data_mode
    return report.build(planet, location, rover_mode, max_slope, **kw)


def _report(m: dict, s: dict) -> str:
    o, t = m["options"], m["options"]["target"]
    res = m["result"]
    if not res.get("similarity"):
        if res.get("report_url"):
            raise _Skip("No bundled analysis to report on; the platform mission report is available "
                        f"({res['report_url']}).")
        raise _Skip("No analysis result to report on.")
    rep = build_report(t["planet"], t["location"], o["rover_mode"], o["slope_limit"], o["ai"], o["cleaning"], o["data_mode"])
    nar = rep.get("narrative") or {}
    res["report"] = {"narrative": nar, "recommended_zone": (rep.get("facts") or {}).get("recommended_zone"),
                     "maps": sorted((rep.get("maps") or {}).keys())}
    res["links"]["mission_control"] = "/app#mission"
    if not res.get("report_url"):
        res["report_url"] = "/app#mission"
    return f"Narrative by {nar.get('generated_by', 'unknown')}." + (f" {nar['note']}" if nar.get("note") else "")
