#############################################################################
# DATA HUB API  (/api/data)  - owned by the data lane, see docs/INTEGRATION_SPEC.md
#
#   GET  /api/data/datasets                       catalogue of every bundled dataset
#   GET  /api/data/datasets/<id>                  metadata: column stats, quality flags, normalization, provenance
#   GET  /api/data/datasets/<id>/records          ?limit&offset&bbox=minLon,minLat,maxLon,maxLat&columns=a,b
#                                                 &cleaning=<profile>&format=json|csv[&download=1]
#   GET  /api/data/datasets/<id>/file             the original bundled file (as shipped in data_ready/)
#   GET  /api/data/cleaning                       cleaning profiles and their steps
#   POST /api/data/clean                          {dataset, profile, bbox?} -> cleaning report only
#   GET  /api/data/sources                        bundled products + live platform connectors
#
# Errors: 400 invalid input, 404 unknown dataset, 503 dataset file not available.
# Routes stay thin: the work happens in services/datasets.py and services/cleaning.py.
#############################################################################
from __future__ import annotations

import json
import urllib.error
import urllib.request

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context

from services import cleaning, datasets, live_data

bp = Blueprint("data", __name__, url_prefix="/api/data")


def _error(status: int, message: str):
    return jsonify({"status": "error", "message": message}), status


@bp.errorhandler(datasets.DatasetError)
def _bad_request(exc):
    return _error(400, str(exc))


@bp.errorhandler(datasets.DatasetNotFound)
def _not_found(exc):
    return _error(404, str(exc.args[0] if exc.args else exc))


@bp.errorhandler(datasets.DatasetUnavailable)
def _unavailable(exc):
    return _error(503, str(exc))


@bp.get("/datasets")
def list_datasets():
    items = datasets.catalog()
    return jsonify({"datasets": items, "count": len(items), "available": sum(d["available"] for d in items),
                    "stages": datasets.STAGES})


@bp.get("/datasets/<dataset_id>")
def get_dataset(dataset_id: str):
    return jsonify(datasets.metadata(dataset_id))


@bp.get("/datasets/<dataset_id>/records")
def get_records(dataset_id: str):
    a = request.args
    fmt = (a.get("format") or "json").lower()
    if fmt not in ("json", "csv"):
        raise datasets.DatasetError("format must be json or csv")
    entry = datasets.describe(dataset_id)                 # 404 for unknown ids
    if not entry["available"]:
        raise datasets.DatasetUnavailable(f"{dataset_id} is not available: {entry['reason']}")
    limit = datasets.parse_int(a.get("limit"), "limit", 100 if fmt == "json" else datasets.LIMITS["csv"],
                               1, datasets.LIMITS[fmt])
    offset = datasets.parse_int(a.get("offset"), "offset", 0, 0, 10_000_000)
    bbox = datasets.parse_bbox(a.get("bbox"))
    columns = datasets.parse_columns(a.get("columns"), entry["columns"])
    profile = datasets.parse_profile(a.get("cleaning"))
    suffix = "" if profile == cleaning.DEFAULT_PROFILE else f"_{profile}"

    if fmt == "csv":
        df, report = datasets.select(dataset_id, profile, bbox)
        page = df.iloc[offset:offset + limit]
        resp = Response(stream_with_context(datasets.csv_chunks(page, columns)), mimetype="text/csv")
        resp.headers["Content-Disposition"] = f'attachment; filename="{dataset_id.replace(".", "_")}{suffix}.csv"'
        resp.headers["X-Total-Count"] = str(len(df))
        resp.headers["X-Rows-Returned"] = str(len(page))
        resp.headers["X-Cleaning-Profile"] = profile
        resp.headers["X-Rows-Removed"] = str(report["rows_removed"])
        return resp

    out = datasets.records(dataset_id, profile, bbox, columns, limit, offset)
    if a.get("download") in ("1", "true"):
        resp = Response(json.dumps(out, ensure_ascii=False), mimetype="application/json")
        resp.headers["Content-Disposition"] = f'attachment; filename="{dataset_id.replace(".", "_")}{suffix}.json"'
        return resp
    return jsonify(out)


@bp.get("/datasets/<dataset_id>/file")
def get_file(dataset_id: str):
    key, stage = datasets.parse_id(dataset_id)
    ok, reason = datasets.availability(key, stage)
    if not ok:
        raise datasets.DatasetUnavailable(f"{dataset_id} is not available: {reason}")
    path = datasets.file_path(dataset_id)
    return send_file(path, as_attachment=True, download_name=path.name, conditional=True,
                     mimetype="application/gzip" if path.suffix == ".gz" else "text/csv")


@bp.get("/cleaning")
def get_cleaning():
    return jsonify(cleaning.catalogue())


@bp.post("/clean")
def post_clean():
    p = request.get_json(silent=True)
    if not isinstance(p, dict):
        raise datasets.DatasetError("JSON body required: {dataset, profile, bbox?}")
    dataset_id = p.get("dataset")
    if not dataset_id or not isinstance(dataset_id, str):
        raise datasets.DatasetError("dataset is required (an id from GET /api/data/datasets)")
    datasets.parse_id(dataset_id)
    profile = datasets.parse_profile(p.get("profile"))
    bbox = datasets.parse_bbox(p.get("bbox"))
    _, report = datasets.select(dataset_id, profile, bbox)
    return jsonify({"dataset": dataset_id, "profile": profile, "bbox": list(bbox) if bbox else None,
                    "report": report})


@bp.get("/sources")
def get_sources():
    bundled = [{"kind": "bundled", "id": d["id"], "title": d["title"], "body": d["body"], "stage": d["stage"],
                "available": d["available"], "reason": d["reason"], "rows": d["rows"], "resolution": d["resolution"],
                "source": d["source"]} for d in datasets.catalog()]
    base = live_data.api_url()
    try:
        with urllib.request.urlopen(f"{base}/v1/science/sources", timeout=8) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        live = [{"kind": "live", **s} for s in doc.get("sources") or []]
        platform = {"status": "ok", "api_url": "/v1", "count": len(live)}
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError, ValueError) as err:
        live = []
        platform = {"status": "unavailable", "api_url": "/v1",
                    "reason": f"TwinSite platform API not reachable ({type(err).__name__}). "
                              "Start it with `make dev` or `python -m twinsite.api`."}
    return jsonify({"platform": platform, "bundled_products": datasets.bundled_products(),
                    "sources": bundled + live, "console": "/console/"})
