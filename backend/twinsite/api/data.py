"""Read-only bounded views over published C1 observations; no SQL or expressions."""
import hashlib
import json
import math

from twinsite.jobs.measured import load_all as load_pair, source_root

RADIUS_M = {"Earth": 6371008.8, "Mars": 3396000.0, 'Moon': 1737400.0}  # spherical approximation, display of extent only
DISPLAY_MAX_CELLS = 72


class SourceIntegrityError(RuntimeError):
    """A pinned object exists but does not match its recorded checksum."""

COLUMNS = ["record_id", "feature_id", "value", "unit", "analysis_scale_m", "spatial_resolution_m", "valid_coverage_fraction", "quality_flags", "source_product", "source_url"]

def observations(dataset):
    rows = [o for o in load_pair()["observations"] if o["site_id"] == dataset]
    if not rows:
        raise KeyError(dataset)
    return rows

def _period(obs):
    period = obs[0]["observation_period"]
    return f'{period["start"][:10]} → {period["end"][:10]}' if isinstance(period, dict) else str(period)

def _assets(obs):
    ids = {i for o in obs for i in o["source_asset_ids"]}
    return [a for a in load_pair()["assets"] if a["asset_id"] in ids]

def catalog():
    pair = load_pair()
    items = []
    for site in pair["sites"]:
        obs = observations(site["site_id"])
        title = site.get("provenance", {}).get("description") or site["site_id"]
        items.append({"dataset_id": site["site_id"], "title": title, "body": site["body"], "temporal_coverage": _period(obs),
                      "source": ", ".join(sorted({o["source_product"] for o in obs})),
                      "domain": "terrain + thermal" if any(o["unit"] == "K" for o in obs) else "terrain", "data_status": "measured",
                      "resolution": str(site.get("provenance", {}).get("analysis_scale_m", obs[0]["analysis_scale_m"])) + " m analysis scale",
                      "records": len(obs),
                      "qa_status": "RELEASE BLOCKED — independent review pending"})
    return {"items": items}

def records(dataset, stage, limit=100):
    obs = observations(dataset)
    if stage not in ("raw", "cleaned", "derived"):
        raise ValueError("Unknown stage")
    if stage == "raw":
        rows = [{"record_id": a["asset_id"], "product_id": a["product_id"], "byte_size": a["byte_size"], "sha256": a["sha256"], "source_url": a["source_url"]} for a in _assets(obs)]
        columns = ["record_id", "product_id", "byte_size", "sha256", "source_url"]
    else:
        rows = [{**{c: o.get(c) for c in COLUMNS}, "record_id": o["evidence_id"], "quality_flags": "; ".join(o["quality_flags"])} for o in obs]
        columns = COLUMNS
    return {"stage": stage, "columns": columns, "rows": rows[:limit], "sampled": len(rows)>limit, "total": len(rows), "next_cursor": None,
            "note": "Raw view lists asset metadata. Cleaned/derived views contain published terrain summaries, not raster cells. Scientific release is blocked."}

def _site(dataset):
    observations(dataset)
    return next(s for s in load_pair()["sites"] if s["site_id"] == dataset)


def extent_km(obs, body):
    """Approximate metric size of the AOI bounding box (spherical mean radius)."""
    west, south, east, north = obs[0]["geometry"]["coordinates"]
    radius = RADIUS_M[body]
    mid = math.radians((south + north) / 2)
    return {"east_west_km": round(math.radians(east - west) * radius * math.cos(mid) / 1000, 1),
            "north_south_km": round(math.radians(north - south) * radius / 1000, 1),
            "bbox_deg": [west, south, east, north],
            "method": "spherical mean radius approximation (display only)"}


def distributions(dataset):
    details = _site(dataset)["provenance"].get("feature_details", {})
    keep = ("n", "min", "p10", "median", "mean", "p90", "max", "sd")
    return {feature: {k: d["stats"][k] for k in keep if k in d.get("stats", {})} for feature, d in sorted(details.items())}


def grid(dataset):
    """Cleaned native grid, verified against its pinned SHA-256, block-averaged for display only."""
    site = _site(dataset)
    prov = site["provenance"]
    root = source_root()
    path = (root / prov["cleaned_object_key"]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise KeyError("cleaned grid not provisioned")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != prov["cleaned_sha256"]:
        raise SourceIntegrityError("cleaned grid checksum mismatch")
    doc = json.loads(raw)
    g = doc["grid"]
    rows, cols, values = g["nrows"], g["ncols"], g["values"]
    k = max(1, math.ceil(max(rows, cols) / DISPLAY_MAX_CELLS))
    out_rows, out_cols = rows // k, cols // k
    cells = []
    for r in range(out_rows):
        for c in range(out_cols):
            block = [values[(r * k + y) * cols + c * k + x] for y in range(k) for x in range(k)]
            cells.append(None if any(v is None for v in block) else round(math.fsum(block) / len(block), 1))
    valid = [v for v in cells if v is not None]
    half = (k - 1) / 2
    return {"dataset_id": dataset, "body": site["body"], "stage": "cleaned", "unit": doc["unit"],
            "vertical_datum": doc.get("vertical_datum"), "cleaned_sha256": prov["cleaned_sha256"],
            "native": {key: g[key] for key in ("nrows", "ncols", "dlat", "dlon", "lat0", "lon0", "registration")},
            "display": {"factor": k, "nrows": out_rows, "ncols": out_cols, "values": cells,
                        "first_center": [g["lon0"] + half * g["dlon"], g["lat0"] - half * g["dlat"]],
                        "step_deg": [k * g["dlon"], k * g["dlat"]], "min": min(valid, default=None), "max": max(valid, default=None),
                        "trimmed_native_rows": rows - out_rows * k, "trimmed_native_cols": cols - out_cols * k},
            "method": (f"Display-only mean of {k}x{k} native samples (null if any sample is null); "
                       f"not the {prov.get('analysis_scale_m')} m analysis grid and not used by any score.") if k > 1 else
                      f"Native cleaned cells, no display aggregation; not the {prov.get('analysis_scale_m')} m analysis grid.",
            "transformations": [str(t) for t in doc.get("transformations", [])],
            "caveats": ["Absolute elevations use body-specific vertical datums and are never compared across bodies.",
                        *sorted({f for o in observations(dataset) for f in o["quality_flags"]})]}


def metadata(dataset):
    obs = observations(dataset)
    site = next(s for s in load_pair()["sites"] if s["site_id"] == dataset)
    p = site["provenance"]
    assets = _assets(obs)
    versions = sorted({a["product_id"] + " " + a["product_version"] for a in assets})
    licenses = sorted({a["license_url"] for a in assets if a.get("license_url")})
    return {"dataset_id": dataset, "source": obs[0]["source_product"], "product": obs[0]["source_product"],
            "version": "; ".join(versions) or None,
            "license": ("Provider data policy: " + "; ".join(licenses)) if licenses else None,
            "data_status": "measured", "crs": obs[0]["geometry"]["crs"], "unit_notes": "degree, metre and kelvin; spatial variability is not measurement uncertainty",
            "time_basis": _period(obs) + " (source acquisition period)", "qa": "Scientific release BLOCKED pending independent C5 review; " + "; ".join(sorted({f for o in obs for f in o["quality_flags"]})),
            "lineage": [o["evidence_id"] + " | " + o["source_url"] for o in obs],
            "transforms": [str(x) for x in p["transformations"]],
            "extent": extent_km(obs, site["body"]),
            "distributions": distributions(dataset),
            "native_resolution_m": p.get("native_resolution_m"), "analysis_scale_m": p.get("analysis_scale_m")}

def compare(body):
    from twinsite.jobs.contract import validate
    validate("data_compare_request", body)
    stage = body["stage"]
    left = records(body["left_dataset_id"], stage)
    right = records(body["right_dataset_id"], stage)
    columns = body["columns"]
    if not set(columns) <= set(left["columns"]) & set(right["columns"]):
        raise ValueError("Unknown comparison columns")
    selected = []
    for side, result in (("left",left),("right",right)):
        ids = body[side + "_record_ids"]
        if not set(ids) <= {r["record_id"] for r in result["rows"]}:
            raise ValueError("Unknown record ID")
        selected.append({r.get("feature_id",r["record_id"]): r for r in result["rows"] if not ids or r["record_id"] in ids})
    l, r = selected
    return {"columns": columns, "rows": [{"key": k, "left": l.get(k), "right": r.get(k)} for k in sorted(l.keys() | r.keys())]}
