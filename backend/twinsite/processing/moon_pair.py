"""Measured Earth (SRTMGL1, verified cache) + Moon (LOLA LDEM_64 + Diviner GCP) feature pair.

    PYTHONPATH=backend python -m twinsite.processing.moon_pair [--offline]

AOIs are METRIC-matched (~33 km on a side on both bodies), unlike equal angular boxes, so extent-dependent
statistics are comparable. Both DEMs are summarised at the LOLA-defined scale (4 x 473.8 m = 1895.3 m).
Diviner temperatures are lunar context observations (thermal / temporal domains); Earth has no keyless
calibrated LST, so thermal features are not weighted in the mission. Writes
``backend/twinsite/processing/published/moon_feature_pair.json``.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from twinsite.sources import diviner, fetch
from twinsite.sources.base import AOI
from twinsite.sources.lola import LOLAGDRAdapter
from twinsite.sources.mola import _sphere_dx, _sphere_dy
from twinsite.sources.srtm import SRTMGL1Adapter, earth_dx, earth_dy

from . import export, terrain
from .g2_pair import _sample_calc, _write_immutable

DATASET = "zagora-taurus-littrow-v1"
EARTH_SITE = ("earth-zagora-draa-m1895", AOI("Earth", -5.95, 30.20, -5.65, 30.50, "EPSG:4326"),
              "Draa valley / Jbel Bani foothills near Zagora, Morocco (arid terrain), summarised at the Moon-pair scale")
MOON_SITE = ("moon-taurus-littrow", AOI("Moon", 30.25, 20.00, 31.35, 21.10, "IAU_2000:30100"),
             "Taurus-Littrow valley and massifs around the Apollo 17 landing site (20.19 N, 30.77 E)")
PUBLISHED = Path(__file__).resolve().parent / "published" / "moon_feature_pair.json"
FEATURES = ("slope_deg", "roughness_m", "local_relief_m")


def _diviner_observations(aoi: AOI, site_id: str, provenance_id: str, offline: bool, root=None):
    asset, b, lat_lo = diviner.acquire(aoi, root=root, offline=offline)
    cells = diviner.decode(asset, b, lat_lo)
    feats = diviner.features(cells)
    meta = feats.pop("_meta")
    out = []
    for fid, f in feats.items():
        rec = {
            "schema_version": "1.0", "feature_id": fid, "site_id": site_id, "body": "Moon",
            "geometry": {"type": "bbox", "coordinates": list(aoi.bbox), "crs": aoi.crs},
            "value": f["value"], "unit": "K", "source_product": diviner.PRODUCT_ID,
            "source_granule_id": asset.granule_id, "source_url": asset.source_url, "source_checksum": asset.sha256,
            "source_asset_ids": [asset.asset_id],
            "observation_period": {"start": export.iso_utc(diviner.WINDOW.start), "end": export.iso_utc(diviner.WINDOW.end)},
            "spatial_resolution_m": 15162.0, "analysis_scale_m": 15162.0,
            "quality_flags": sorted({"DIVINER_0P5DEG_BINS", "BOLOMETRIC_TEMPERATURE_FROM_7_CHANNELS",
                                     f"LOCAL_TIME_SLOT_COVERAGE={meta['mean_local_time_slot_coverage']}",
                                     f"BINS_IN_AOI={meta['bins']}"}),
            "valid_coverage_fraction": f["coverage"],
            "uncertainty": {"kind": "interval", "low": f["interval"][0], "high": f["interval"][1], "standard_deviation": None,
                            "basis": "10th-90th percentile across 0.5-deg bins in the AOI (spatial variability). Diviner "
                                     "absolute calibration ~1-2 K above 100 K (Williams et al. 2017); not propagated."},
            "processing_version": export.PROCESSING_VERSION + "; diviner-gcp/1.0 (tbol>0, fill -9999 masked, day 06-18h max, night 18-06h min, AOI median)",
            "provenance_id": provenance_id, "evidence_kind": "derived_measurement", "data_status": "measured",
            "missing_reason": f["missing_reason"], "qa_status": "ACCEPT" if f["value"] is not None else "INSUFFICIENT",
        }
        rec["evidence_id"] = f"ev-{site_id}-{fid}-{export.canonical_sha256(rec)[:16]}"
        out.append(rec)
    return asset, out, {"bins": meta["bins"], "definitions": {k: v["definition"] for k, v in feats.items()},
                        "local_time_slot_coverage": meta["mean_local_time_slot_coverage"]}


def run(offline: bool = False) -> Dict[str, Any]:
    srtm, lola = SRTMGL1Adapter(offline=True), LOLAGDRAdapter(offline=offline)   # SRTM: verified cache only
    m_id, m_aoi, m_desc = MOON_SITE
    m_gr = lola.discover(m_aoi, None)
    m_assets = lola.acquire(m_gr, byte_budget=3_000_000, aoi=m_aoi)
    m_dec = lola.decode(m_assets, m_aoi, m_gr[0])
    m_val = lola.validate(m_dec)
    m_cln = lola.clean(m_dec, ["lola_flag_interpolated"])
    scale = lola.supported_scale(m_dec, 0.65)
    m_fs = lola.features(m_cln, scale)

    e_id, e_aoi, e_desc = EARTH_SITE
    e_gr = srtm.discover(e_aoi, None)
    e_assets = srtm.acquire(e_gr, byte_budget=12_000_000)
    e_dec = srtm.decode(e_assets, e_aoi, e_gr[0])
    e_val = srtm.validate(e_dec)
    e_cln = srtm.clean(e_dec, ["srtm_void_mask"])
    e_fs = srtm.features(e_cln, scale)

    sites, manifests_all, obs_all = [], [], []
    for sid, desc, adapter, gr, assets, dec, val, fs, dxf, dyf, rules in (
        (e_id, e_desc, srtm, e_gr[0], e_assets, e_dec, e_val, e_fs, earth_dx, earth_dy, ["srtm_void_mask"]),
        (m_id, m_desc, lola, m_gr[0], m_assets, m_dec, m_val, m_fs, _sphere_dx(m_dec.body_radius_m),
         _sphere_dy(m_dec.body_radius_m), ["lola_flag_interpolated"]),
    ):
        primary = next(a for a in assets if a.role == "data")
        g = fs.decoded.grid
        c_key, c_sha = _write_immutable("cleaned", {"site_id": sid, "stage": "cleaned", "grid": g.__dict__, "unit": dec.unit,
                                                    "vertical_datum": dec.vertical_datum,
                                                    "transformations": fs.decoded.transformations,
                                                    "parent_asset_ids": sorted(a.asset_id for a in assets)})
        mid = (g.lat(0) + g.lat(g.nrows - 1)) / 2
        by_bx = terrain.choose_block(dxf(mid, g.dlon), dyf(mid, g.dlat), scale)
        manifests = [export.asset_manifest(a) for a in assets]
        prov = {
            "site_id": sid, "description": desc, "adapter": adapter.describe(),
            "granule": {"granule_id": gr.granule_id, "footprint": list(gr.footprint), "catalog_evidence": gr.catalog_evidence},
            "cleaned_object_key": c_key, "cleaned_sha256": c_sha, "transformations": fs.transformations,
            "validation": {"verdict": val.verdict, "metrics": val.metrics, "issues": [i.as_record() for i in val.issues]},
            "vertical_datum": dec.vertical_datum, "horizontal_datum": dec.horizontal_datum, "radius_model": dec.radius_model,
            "native_resolution_m": round(dec.native_resolution_m, 3), "analysis_scale_m": scale,
            "cell_size_m_used": list(fs.cell_size_m),
            "feature_definitions": {f.feature_id: f.definition for f in fs.features},
            "feature_details": {f.feature_id: f.detail for f in fs.features},
            "sample_calculation": _sample_calc(fs, dxf, dyf, by_bx),
        }
        extra_obs = []
        if dec.aoi.body == "Moon":
            d_asset, extra_obs_tmp, d_meta = None, None, None
            prov_key0, prov_sha0 = _write_immutable("derived", prov)
            pid = f"prov-{sid}-{prov_sha0[:16]}"
            d_asset, extra_obs, d_meta = _diviner_observations(dec.aoi, sid, pid, offline)
            prov["diviner"] = d_meta
            manifests.append(export.asset_manifest(d_asset))
        prov_key, prov_sha = _write_immutable("derived", prov)
        provenance_id = f"prov-{sid}-{prov_sha[:16]}"
        for o in extra_obs:
            o["provenance_id"] = provenance_id
            o.pop("evidence_id")
            o["evidence_id"] = f"ev-{sid}-{o['feature_id']}-{export.canonical_sha256(o)[:16]}"
        obs = export.observations(fs, val, sid, provenance_id, rules) + extra_obs
        obs_all.extend(obs)
        manifests_all.extend(manifests)
        sites.append({"site_id": sid, "body": dec.aoi.body, "provenance_id": provenance_id, "provenance_object_key": prov_key,
                      "quality_verdict": export.quality_verdict(primary, val, c_sha), "provenance": prov})

    snap = export.snapshot_sha256(manifests_all)
    doc = {
        "schema_note": "observations[] follow evidence_observation.schema.json; assets[] follow asset_manifest.schema.json. "
                       "REAL NASA product summaries (SRTMGL1, LOLA LDEM_64, Diviner GCP), not synthetic.",
        "dataset_id": DATASET, "data_status": "measured", "processing_version": export.PROCESSING_VERSION,
        "analysis_scale_m": scale, "source_snapshot_id": f"c1-moon-{snap[:16]}", "source_snapshot_sha256": snap,
        "comparison_pairs": [{"feature_id": fid,
                              "earth_evidence_id": next(o["evidence_id"] for o in obs_all if o["site_id"] == e_id and o["feature_id"] == fid),
                              "target_evidence_id": next(o["evidence_id"] for o in obs_all if o["site_id"] == m_id and o["feature_id"] == fid)}
                             for fid in FEATURES],
        "observations": obs_all, "assets": manifests_all, "sites": sites,
    }
    PUBLISHED.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return doc


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    doc = run(offline=ap.parse_args().offline)
    for o in doc["observations"]:
        print(f"{o['site_id']:26s} {o['feature_id']:36s} {o['value']!s:>10} {o['unit']:6s} qa={o['qa_status']}")
    print("snapshot", doc["source_snapshot_sha256"], "->", PUBLISHED)


if __name__ == "__main__":
    main()
