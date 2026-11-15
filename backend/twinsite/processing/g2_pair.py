"""G2 deliverable: one real Earth (SRTMGL1) + one real Mars (MOLA MEGDR) feature pair.

    PYTHONPATH=backend python -m twinsite.processing.g2_pair [--offline]

Both products are summarised at the SAME physical analysis scale (MOLA's native
cell, ~463 m) so the slope/roughness values are comparable; SRTM is block-
averaged to that scale, MOLA is used at native scale.  Writes:

* ``.runtime/data/cleaned/<sha>.json`` and ``derived/<sha>.json`` (immutable)
* ``backend/twinsite/processing/published/g2_feature_pair.json`` (small, committed)
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from twinsite.sources import fetch
from twinsite.sources.base import AOI, FeatureSet, Grid
from twinsite.sources.mola import MOLAMEGDRAdapter, _sphere_dx, _sphere_dy
from twinsite.sources.srtm import SRTMGL1Adapter, earth_dx, earth_dy

from . import export, terrain

EARTH_SITE = ("earth-zagora-draa", AOI("Earth", -5.95, 30.20, -5.65, 30.50, "EPSG:4326"),
              "Draa valley / Jbel Bani foothills near Zagora, Morocco (arid terrain)")
MARS_SITE = ("mars-gale-aeolis", AOI("Mars", 137.25, -4.75, 137.55, -4.45, "IAU_2000:49900"),
             "Gale crater floor (Aeolis Palus) around the MSL Bradbury landing site")
PUBLISHED = Path(__file__).resolve().parent / "published" / "g2_feature_pair.json"


def _write_immutable(stage: str, obj: Any) -> Tuple[str, str]:
    digest = export.canonical_sha256(obj)
    key = f"{stage}/{digest}.json"
    p = fetch.artifact_root() / key
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, sort_keys=True, separators=(",", ":")))
        os.chmod(p, 0o444)
    return key, digest


def _sample_calc(fs: FeatureSet, dx_fn, dy_fn, by_bx: Tuple[int, int]) -> Dict[str, Any]:
    """Re-derive one Horn slope by explicit arithmetic for reviewers."""
    g = fs.decoded.grid
    agg = terrain.aggregate(g, *by_bx)
    r, c = agg.nrows // 2, agg.ncols // 2
    w = [[agg.at(r + dr, c + dc) for dc in (-1, 0, 1)] for dr in (-1, 0, 1)]
    if any(v is None for row in w for v in row):
        return {"status": "centre window contains masked cells; no sample"}
    (a, b, cc), (d, _e, f), (gg, h, i) = w
    dx = dx_fn(agg.lat(r), agg.dlon)
    dy = dy_fn(agg.lat(r), agg.dlat)
    dzdx = ((cc + 2 * f + i) - (a + 2 * d + gg)) / (8 * dx)
    dzdy = ((a + 2 * b + cc) - (gg + 2 * h + i)) / (8 * dy)
    slope = math.degrees(math.atan(math.hypot(dzdx, dzdy)))
    mean9 = sum(v for row in w for v in row) / 9
    sd9 = math.sqrt(sum((v - mean9) ** 2 for row in w for v in row) / 9)
    return {
        "cell": {"row": r, "col": c, "lat": round(agg.lat(r), 6), "lon": round(agg.lon(c), 6)},
        "block": list(by_bx),
        "window_m": [[round(v, 3) for v in row] for row in w],
        "dx_m": round(dx, 3), "dy_m": round(dy, 3),
        "dz_dx": round(dzdx, 6), "dz_dy": round(dzdy, 6),
        "horn_slope_deg": round(slope, 4),
        "roughness_sd_m": round(sd9, 4),
        "formula": "slope = atan(hypot(((c+2f+i)-(a+2d+g))/(8dx), ((a+2b+c)-(g+2h+i))/(8dy))); rows north->south",
    }


def run(offline: bool = False) -> Dict[str, Any]:
    srtm, mola = SRTMGL1Adapter(offline=offline), MOLAMEGDRAdapter(offline=offline)

    # ---- Mars first: its native cell defines the common analysis scale
    m_id, m_aoi, m_desc = MARS_SITE
    m_gr = mola.discover(m_aoi, None)
    m_assets = mola.acquire(m_gr, byte_budget=2_000_000, aoi=m_aoi)
    m_dec = mola.decode(m_assets, m_aoi, m_gr[0])
    m_val = mola.validate(m_dec)
    m_cln = mola.clean(m_dec, ["mola_flag_interpolated"])
    scale = math.ceil(m_dec.native_resolution_m * 10) / 10
    m_fs = mola.features(m_cln, scale)

    e_id, e_aoi, e_desc = EARTH_SITE
    e_gr = srtm.discover(e_aoi, None)
    e_assets = srtm.acquire(e_gr, byte_budget=12_000_000)
    e_dec = srtm.decode(e_assets, e_aoi, e_gr[0])
    e_val = srtm.validate(e_dec)
    e_cln = srtm.clean(e_dec, ["srtm_void_mask"])
    e_fs = srtm.features(e_cln, scale)

    sites = []
    all_manifests: List[Dict[str, Any]] = []
    all_obs: List[Dict[str, Any]] = []
    for sid, desc, adapter, gr, assets, dec, val, fs, dxf, dyf in (
        (e_id, e_desc, srtm, e_gr[0], e_assets, e_dec, e_val, e_fs, earth_dx, earth_dy),
        (m_id, m_desc, mola, m_gr[0], m_assets, m_dec, m_val, m_fs,
         _sphere_dx(m_dec.body_radius_m), _sphere_dy(m_dec.body_radius_m)),
    ):
        primary = next(a for a in assets if a.role == "data")
        g = fs.decoded.grid
        cleaned_obj = {"site_id": sid, "stage": "cleaned", "grid": g.__dict__, "unit": dec.unit,
                       "vertical_datum": dec.vertical_datum, "transformations": fs.decoded.transformations,
                       "parent_asset_ids": sorted(a.asset_id for a in assets)}
        c_key, c_sha = _write_immutable("cleaned", cleaned_obj)
        mid = (g.lat(0) + g.lat(g.nrows - 1)) / 2
        by_bx = terrain.choose_block(dxf(mid, g.dlon), dyf(mid, g.dlat), scale)
        manifests = [export.asset_manifest(a) for a in assets]
        verdict = export.quality_verdict(primary, val, c_sha)
        prov = {
            "site_id": sid, "description": desc, "adapter": adapter.describe(),
            "granule": {"granule_id": gr.granule_id, "footprint": list(gr.footprint),
                        "catalog_evidence": gr.catalog_evidence},
            "transcripts": sorted({json.loads(Path(a.path).parent.joinpath("asset.json").read_text())
                                  .get("transcript", "") for a in assets}),
            "acquisition_errors_preserved": [
                e for a in assets
                for e in json.loads(Path(a.path).parent.joinpath("asset.json").read_text()).get("acquisition_errors", [])],
            "cleaned_object_key": c_key, "cleaned_sha256": c_sha,
            "transformations": fs.transformations,
            "validation": {"verdict": val.verdict, "metrics": val.metrics,
                           "issues": [i.as_record() for i in val.issues]},
            "vertical_datum": dec.vertical_datum, "horizontal_datum": dec.horizontal_datum,
            "radius_model": dec.radius_model, "native_resolution_m": round(dec.native_resolution_m, 3),
            "analysis_scale_m": scale, "cell_size_m_used": list(fs.cell_size_m),
            "feature_definitions": {f.feature_id: f.definition for f in fs.features},
            "feature_details": {f.feature_id: f.detail for f in fs.features},
            "sample_calculation": _sample_calc(fs, dxf, dyf, by_bx),
        }
        prov_key, prov_sha = _write_immutable("derived", prov)
        provenance_id = f"prov-{sid}-{prov_sha[:16]}"
        rules = ["srtm_void_mask"] if adapter is srtm else ["mola_flag_interpolated"]
        obs = export.observations(fs, val, sid, provenance_id, rules)
        all_obs.extend(obs)
        all_manifests.extend(manifests)
        sites.append({"site_id": sid, "body": dec.aoi.body, "provenance_id": provenance_id,
                      "provenance_object_key": prov_key, "quality_verdict": verdict,
                      "provenance": prov})

    snap = export.snapshot_sha256(all_manifests)
    doc = {
        "schema_note": "observations[] follow contracts/v1/evidence_observation.schema.json; "
                       "assets[] follow asset_manifest.schema.json; sites[].quality_verdict follows "
                       "quality_verdict.schema.json. Values are REAL NASA product summaries, not synthetic.",
        "data_status": "measured",
        "processing_version": export.PROCESSING_VERSION,
        "analysis_scale_m": scale,
        "source_snapshot_id": f"c1-g2-{snap[:16]}",
        "source_snapshot_sha256": snap,
        "comparison_pairs": [{"feature_id": fid,
                              "earth_evidence_id": next(o["evidence_id"] for o in all_obs
                                                        if o["site_id"] == e_id and o["feature_id"] == fid),
                              "mars_evidence_id": next(o["evidence_id"] for o in all_obs
                                                       if o["site_id"] == m_id and o["feature_id"] == fid)}
                             for fid in ("slope_deg", "roughness_m", "local_relief_m")],
        "observations": all_obs,
        "assets": all_manifests,
        "sites": sites,
    }
    PUBLISHED.parent.mkdir(parents=True, exist_ok=True)
    PUBLISHED.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="use only SHA-verified cached raw assets")
    args = ap.parse_args()
    doc = run(offline=args.offline)
    for o in doc["observations"]:
        print(f"{o['site_id']:20s} {o['feature_id']:15s} {o['value']!s:>12} {o['unit']:7s} "
              f"cov={o['valid_coverage_fraction']:.3f} qa={o['qa_status']} {o['evidence_id']}")
    print("snapshot", doc["source_snapshot_sha256"])
    print("wrote", PUBLISHED)


if __name__ == "__main__":
    main()
