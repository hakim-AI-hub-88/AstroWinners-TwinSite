"""Intake of typed evidence observations (contracts/v1/evidence_observation.schema.json).

The engine is typed against the frozen contract, not any lane's internal
classes. A request observation's `source_id` must resolve to an `evidence_id`
whose value/unit/feature/body/site match exactly (this is the lineage that
contracts.validation.measured_release_issues verifies after the run).
"""
from __future__ import annotations

import math
import re

REQUIRED_KEYS = (
    "schema_version", "evidence_id", "feature_id", "site_id", "body", "geometry", "value", "unit",
    "source_product", "source_granule_id", "source_url", "source_checksum", "source_asset_ids",
    "observation_period", "spatial_resolution_m", "analysis_scale_m", "quality_flags",
    "valid_coverage_fraction", "uncertainty", "processing_version", "provenance_id", "evidence_kind",
    "data_status", "missing_reason", "qa_status",
)
MEASURED_KINDS = ("direct_measurement", "derived_measurement")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
# Two analysis scales are "common" when within this relative tolerance.
SCALE_RELATIVE_TOLERANCE = 0.10


class EvidenceError(ValueError):
    pass


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def check_record(record):
    """Structural/invariant check of one record; raises EvidenceError."""
    if not isinstance(record, dict):
        raise EvidenceError("evidence record must be an object")
    missing = [k for k in REQUIRED_KEYS if k not in record]
    if missing:
        raise EvidenceError(f"evidence {record.get('evidence_id')!r} missing keys {missing}")
    eid = record["evidence_id"]
    if record["schema_version"] != "1.0":
        raise EvidenceError(f"{eid}: schema_version must be 1.0")
    if record["body"] not in ("Earth", "Moon", "Mars"):
        raise EvidenceError(f"{eid}: invalid body")
    geometry = record["geometry"]
    if (not isinstance(geometry, dict) or geometry.get("type") != "bbox" or not geometry.get("crs")
            or len(geometry.get("coordinates", [])) != 4):
        raise EvidenceError(f"{eid}: geometry needs bbox coordinates and explicit CRS")
    value = record["value"]
    if value is None:
        if not record.get("missing_reason"):
            raise EvidenceError(f"{eid}: null value needs missing_reason")
    elif not _finite(value):
        raise EvidenceError(f"{eid}: value must be finite or null")
    if record["evidence_kind"] == "unavailable" and value is not None:
        raise EvidenceError(f"{eid}: unavailable evidence must have null value")
    if not _HEX64.match(str(record["source_checksum"])):
        raise EvidenceError(f"{eid}: source_checksum must be lowercase sha256 hex")
    if not record["source_asset_ids"]:
        raise EvidenceError(f"{eid}: source_asset_ids required")
    cov = record["valid_coverage_fraction"]
    if not _finite(cov) or not 0 <= cov <= 1:
        raise EvidenceError(f"{eid}: valid_coverage_fraction must be in [0,1]")
    return record


def index_evidence(evidence):
    """Return {evidence_id: record}; duplicate evidence IDs are an integrity error."""
    by_id = {}
    for record in evidence or []:
        check_record(record)
        eid = record["evidence_id"]
        if eid in by_id:
            raise EvidenceError(f"duplicate evidence_id {eid}")
        by_id[eid] = record
    return by_id


def attest(observation, feature_id, location_id, body, by_id, strict):
    """Check one request observation against its evidence record.

    Returns (record_or_None, problems, warnings). Any problem means the
    observation must not be scored. Lineage mismatches are problems in every
    mode; measurement-quality shortfalls are problems only in strict mode.
    """
    problems, warnings = [], []
    record = by_id.get(observation.get("source_id"))
    if record is None:
        if strict:
            problems.append("no evidence record for source_id")
        else:
            warnings.append("unverified: no evidence record for source_id")
        return None, problems, warnings
    if record["feature_id"] != feature_id:
        problems.append(f"evidence feature {record['feature_id']} != {feature_id}")
    if record["site_id"] != location_id:
        problems.append(f"evidence site {record['site_id']} != {location_id}")
    if record["body"] != body:
        problems.append(f"evidence body {record['body']} != {body}")
    if record["unit"] != observation.get("unit"):
        problems.append(f"evidence unit {record['unit']} != request unit {observation.get('unit')}")
    if record["value"] != observation.get("value"):
        problems.append("evidence value differs from request value")
    quality = []
    if record["data_status"] != "measured":
        quality.append(f"data_status {record['data_status']}")
    if record["evidence_kind"] not in MEASURED_KINDS:
        quality.append(f"evidence_kind {record['evidence_kind']} cannot satisfy a measured feature")
    if record["qa_status"] != "ACCEPT":
        quality.append(f"qa_status {record['qa_status']}")
    if record["valid_coverage_fraction"] <= 0:
        quality.append("zero valid coverage")
    if record["spatial_resolution_m"] is None or record["analysis_scale_m"] is None:
        quality.append("missing spatial support")
    (problems if strict else warnings).extend(quality)
    return record, problems, warnings


def scales_comparable(a, b):
    sa, sb = a.get("analysis_scale_m"), b.get("analysis_scale_m")
    if sa is None or sb is None:
        return None
    return abs(sa - sb) <= SCALE_RELATIVE_TOLERANCE * max(sa, sb)


def shared_source_pairs(records_by_site):
    """Sites whose scored evidence comes from the identical bytes+feature+geometry."""
    keys = {}
    for site_id, records in records_by_site.items():
        for r in records:
            key = (r["source_checksum"], r["feature_id"], tuple(r["geometry"]["coordinates"]), r["geometry"]["crs"])
            keys.setdefault(key, set()).add(site_id)
    pairs = set()
    for sites in keys.values():
        for a in sorted(sites):
            for b in sorted(sites):
                if a < b:
                    pairs.add((a, b))
    return sorted(pairs)
