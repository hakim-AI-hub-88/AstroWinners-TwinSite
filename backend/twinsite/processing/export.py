"""Export decoded/featured products as TwinSite v1 contract records.

Outputs only artifact references and summarised numbers -- never raster bytes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Sequence

from twinsite.sources.base import ADAPTER_VERSION, FeatureSet, RawAsset, Validation, iso_utc

from . import terrain

PROCESSING_VERSION = f"{ADAPTER_VERSION}; {terrain.TERRAIN_METHOD_VERSION}"
QA_METHOD_VERSION = "c1-qa/1.0.0"


def canonical_sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)
                          .encode("utf-8")).hexdigest()


def asset_manifest(a: RawAsset) -> Dict[str, Any]:
    return {
        "schema_version": "1.0",
        "asset_id": a.asset_id,
        "source_id": a.source_id,
        "product_id": a.product_id,
        "product_version": a.product_version,
        "body": a.body,
        "source_url": a.source_url,
        "object_key": a.object_key,
        "sha256": a.sha256,
        "retrieved_at": a.retrieved_at,
        "observation_start": iso_utc(a.observation.start),
        "observation_end": iso_utc(a.observation.end),
        "format": a.fmt,
        "crs": a.crs,
        "coordinate_conventions": a.coordinate_conventions
        + (f"; byte ranges (inclusive) of source file: {len(a.byte_ranges)} ranges "
           f"{a.byte_ranges[0][0]}..{a.byte_ranges[-1][1]}" if a.byte_ranges else ""),
        "license_url": a.license_url,
        "byte_size": a.byte_size,
        "adapter_version": ADAPTER_VERSION,
        "parent_asset_ids": list(a.parent_asset_ids),
    }


def quality_verdict(primary: RawAsset, v: Validation, cleaned_sha256: str) -> Dict[str, Any]:
    return {
        "asset_id": primary.asset_id,
        "source_product_id": f"{primary.product_id}.{primary.product_version}",
        "verdict": v.verdict,
        "issues": [i.as_record() for i in v.issues],
        "attempt_count": 0,
        "raw_checksum": primary.sha256,
        "cleaned_checksum": cleaned_sha256,
        "method_version": QA_METHOD_VERSION,
    }


def cleaned_checksum(fs: FeatureSet) -> str:
    """SHA-256 of the canonical cleaned AOI grid (values + georeference)."""
    g = fs.decoded.grid
    return canonical_sha256({"nrows": g.nrows, "ncols": g.ncols, "lat0": g.lat0, "lon0": g.lon0,
                             "dlat": g.dlat, "dlon": g.dlon, "values": g.values,
                             "transformations": fs.decoded.transformations})


def evidence_qa(raw: Validation, fs: FeatureSet, approved_rules: Sequence[str]) -> str:
    """QA status of the *cleaned* evidence.

    REPAIR_ALLOWED on raw becomes ACCEPT only when every repairable issue's rule
    was applied and coverage after masking still meets the minimum; critical
    issues always stay QUARANTINE.
    """
    from .dem_features import MIN_COVERAGE

    if raw.verdict == "REPAIR_ALLOWED":
        needed = {i.rule_id for i in raw.issues if i.severity != "info" and i.rule_id}
        if needed <= set(approved_rules) and fs.valid_coverage_fraction >= MIN_COVERAGE:
            return "ACCEPT"
    return raw.verdict


def observations(fs: FeatureSet, v: Validation, site_id: str, provenance_id: str,
                 approved_rules: Sequence[str] = ()) -> List[Dict[str, Any]]:
    d = fs.decoded
    qa = evidence_qa(v, fs, approved_rules)
    primary = next(a for a in d.assets if a.role == "data")
    out = []
    for f in fs.features:
        rec = {
            "schema_version": "1.0",
            "feature_id": f.feature_id,
            "site_id": site_id,
            "body": d.aoi.body,
            "geometry": {"type": "bbox", "coordinates": d.aoi.bbox, "crs": d.aoi.crs},
            "value": f.value,
            "unit": f.unit,
            "source_product": primary.product_id,  # must equal asset_manifest.product_id (C0 lineage gate)
            "source_granule_id": primary.granule_id,
            "source_url": primary.source_url,
            "source_checksum": primary.sha256,
            "source_asset_ids": sorted({a.asset_id for a in d.assets}),
            "observation_period": {"start": iso_utc(d.granule.observation.start),
                                   "end": iso_utc(d.granule.observation.end)},
            "spatial_resolution_m": round(d.native_resolution_m, 3),
            "analysis_scale_m": fs.analysis_scale_m,
            "quality_flags": sorted(set(fs.quality_flags)),
            "valid_coverage_fraction": fs.valid_coverage_fraction,
            "uncertainty": f.uncertainty,
            "processing_version": PROCESSING_VERSION,
            "provenance_id": provenance_id,
            "evidence_kind": f.evidence_kind,
            "data_status": "measured",
            "missing_reason": f.missing_reason,
            "qa_status": qa if f.value is not None else "INSUFFICIENT",
        }
        rec["evidence_id"] = f"ev-{site_id}-{f.feature_id}-{canonical_sha256(rec)[:16]}"
        out.append(rec)
    return out


def snapshot_sha256(assets: Sequence[Dict[str, Any]]) -> str:
    """Contract: SHA-256 of canonical JSON array of {asset_id, sha256} sorted by asset_id."""
    arr = sorted(({"asset_id": a["asset_id"], "sha256": a["sha256"]} for a in assets), key=lambda x: x["asset_id"])
    return canonical_sha256(arr)
