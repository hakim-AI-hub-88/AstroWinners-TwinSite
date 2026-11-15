"""Read-only bounded views over published C1 observations; no SQL or expressions."""
from twinsite.jobs.measured import load_pair

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
                      "source": obs[0]["source_product"], "domain": "terrain", "data_status": "measured",
                      "resolution": str(pair["analysis_scale_m"]) + " m analysis scale", "records": len(obs),
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
            "data_status": "measured", "crs": obs[0]["geometry"]["crs"], "unit_notes": "degree and metre; spatial variability is not measurement uncertainty",
            "time_basis": _period(obs) + " (source acquisition period)", "qa": "Scientific release BLOCKED pending independent C5 review; " + "; ".join(sorted({f for o in obs for f in o["quality_flags"]})),
            "lineage": [o["evidence_id"] + " | " + o["source_url"] for o in obs],
            "transforms": [str(x) for x in p["transformations"]]}

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
