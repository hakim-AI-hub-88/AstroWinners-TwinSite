"""Characterize ANY site on Earth, the Moon or Mars from real public data, end to end.

    characterize(data_dir, body, lon, lat, name) -> site document (persisted, reused)

Earth: AWS Terrain Tiles terrarium DEM (slope/roughness/relief) + NASA POWER climatology (+ GIBS image on request)
Moon:  LRO LOLA LDEM_64 (slope/roughness/relief) + LRO Diviner GCP (day/night/diurnal temperatures)
Mars:  MGS MOLA MEGDR 128 ppd (slope/roughness/relief, shot-supported coverage)
All:   NSSDCA body constants.

Every site uses a METRIC-matched ~33 x 33 km area and one common 1900 m analysis scale, so sites on different
bodies are comparable. Raw assets are SHA-256 verified; observations follow evidence_observation.schema.json and
are also written to science.sqlite for the Data Explorer.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from twinsite.processing import export
from twinsite.storage.science_db import science_db

from . import diviner, gateway
from .base import AOI
from .lola import LOLAGDRAdapter
from .mola import MOLAMEGDRAdapter
from .terrarium import TerrariumAdapter

SCALE_M = 1900.0
SIDE_KM = 33.0
RADIUS_KM = {"Earth": 6371.0, "Moon": 1737.4, "Mars": 3389.5}
CRS = {"Earth": "EPSG:4326", "Moon": "IAU_2000:30100", "Mars": "IAU_2000:49900"}
DOMAIN = {"slope_deg": "topography", "roughness_m": "topography", "local_relief_m": "topography",
          "surface_temperature_day_K": "thermal", "surface_temperature_night_K": "thermal",
          "surface_temperature_diurnal_range_K": "temporal"}


def site_id(body, lon, lat):
    c = f"{lat:+.3f}{lon:+.3f}".replace("+", "p").replace("-", "m").replace(".", "_")
    return f"{body.lower()}-{c}"


def aoi_for(body, lon, lat):
    """~33 km square, shifted (not shrunk) to stay inside one product tile."""
    dlat = math.degrees(SIDE_KM / RADIUS_KM[body])
    dlon = dlat / max(0.2, math.cos(math.radians(lat)))
    s, n = lat - dlat / 2, lat + dlat / 2
    w, e = lon - dlon / 2, lon + dlon / 2
    if body == "Earth":                       # terrarium tiles mosaic freely; keep within -180..180 / 84S..84N
        s, n = max(-83.9, s), min(83.9, n)
        w, e = max(-179.999, w), min(179.999, e)
    elif body == "Moon":                      # one 10-degree Diviner band
        b = math.floor(lat / 10) * 10
        s = max(b + 0.001, min(s, b + 9.999 - dlat))
        n = s + dlat
    elif body == "Mars":                      # one 44 x 90 degree MEGDR tile
        bands = ((88, 44), (44, 0), (0, -44), (-44, -88))
        top, bot = next(((t, b) for t, b in bands if b <= lat < t), (88, 44))
        s = max(bot + 0.001, min(s, top - 0.001 - dlat))
        n = s + dlat
        lon360 = lon % 360
        t_w = math.floor(lon360 / 90) * 90
        w360 = max(t_w + 0.001, min(lon360 - dlon / 2, t_w + 89.999 - dlon))
        w = w360 - 360 if w360 > 180 else w360
        e = w + dlon
    return AOI(body, round(w, 5), round(s, 5), round(e, 5), round(n, 5), CRS[body])


def _observations(fs, val, sid, prov_id, rules):
    return export.observations(fs, val, sid, prov_id, rules)


def _raw_root():
    from twinsite.jobs.measured import source_root
    return source_root()


def _dem(body, aoi):
    root = _raw_root()   # raw bytes live where the evidence checksum gate verifies them
    if body == "Earth":
        a, rules, budget = TerrariumAdapter(root=root), ["srtm_void_mask"], 8_000_000
    elif body == "Moon":
        a, rules, budget = LOLAGDRAdapter(root=root), ["lola_flag_interpolated"], 4_000_000
    else:
        a, rules, budget = MOLAMEGDRAdapter(root=root), ["mola_flag_interpolated"], 4_000_000
    gr = a.discover(aoi, None)
    assets = a.acquire(gr, budget, aoi=aoi)
    dec = a.decode(assets, aoi, gr[0])
    val = a.validate(dec)
    cln = a.clean(dec, rules)
    fs = a.features(cln, SCALE_M)
    return a, gr[0], assets, dec, val, fs, rules


def characterize(data_dir, body, lon, lat, name=None, refresh=False):
    data_dir = Path(data_dir)
    if body not in RADIUS_KM:
        raise ValueError("body must be Earth, Moon or Mars")
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError("longitude -180..180, latitude -90..90")
    sid = site_id(body, lon, lat)
    path = data_dir / "sites" / f"{sid}.json"
    if path.exists() and not refresh:
        return json.loads(path.read_text())
    aoi = aoi_for(body, lon, lat)
    a, granule, assets, dec, val, fs, rules = _dem(body, aoi)
    prov = {"site_id": sid, "description": name or sid, "adapter": a.describe(),
            "granule": {"granule_id": granule.granule_id, "footprint": list(granule.footprint)},
            "transformations": fs.transformations,
            "validation": {"verdict": val.verdict, "metrics": val.metrics, "issues": [i.as_record() for i in val.issues]},
            "vertical_datum": dec.vertical_datum, "horizontal_datum": dec.horizontal_datum, "radius_model": dec.radius_model,
            "native_resolution_m": round(dec.native_resolution_m, 3), "analysis_scale_m": SCALE_M,
            "feature_definitions": {f.feature_id: f.definition for f in fs.features},
            "feature_details": {f.feature_id: f.detail for f in fs.features}}
    prov_id = f"prov-{sid}-{export.canonical_sha256(prov)[:16]}"
    obs = _observations(fs, val, sid, prov_id, rules)
    manifests = [export.asset_manifest(x) for x in assets]
    errors = []
    if body == "Moon":
        try:
            from twinsite.processing.moon_pair import _diviner_observations
            d_aoi = AOI("Moon", aoi.west, aoi.south, aoi.east, aoi.north, aoi.crs)
            d_asset, d_obs, d_meta = _diviner_observations(d_aoi, sid, prov_id, False, root=_raw_root())
            obs += d_obs
            manifests.append(export.asset_manifest(d_asset))
            prov["diviner"] = d_meta
        except Exception as error:  # noqa: BLE001 - recorded, never hidden
            errors.append(f"Diviner: {type(error).__name__}: {str(error)[:160]}")
    doc = {"site_id": sid, "name": name or sid, "body": body, "longitude": lon, "latitude": lat,
           "aoi": list(aoi.bbox), "crs": aoi.crs, "analysis_scale_m": SCALE_M, "data_status": "measured",
           "observations": obs, "assets": manifests, "provenance_id": prov_id, "provenance": prov,
           "acquisition_errors": errors}
    # Persist for the Data Explorer (one row per observation; raw bytes stay in managed storage).
    db = science_db(data_dir)
    gateway._register_sources(db)
    for src in (dict(source_id="aws-terrain-tiles", name="AWS Terrain Tiles (terrarium z11 / skadi), SRTM-based composite DEM",
                     provider="AWS Open Data / Tilezen", bodies=["Earth"], domains=["topography"], access="public S3",
                     auth="none", documentation_url="https://registry.opendata.aws/terrain-tiles/", status="integrated_live",
                     notes="Keyless global Earth DEM; producer void-filled composite."),
                dict(source_id="lro-lola-ldem64", name="LRO LOLA LDEM_64", provider="NASA PDS", bodies=["Moon"],
                     domains=["topography"], access="public", auth="none",
                     documentation_url="https://pds-geosciences.wustl.edu/missions/lro/lola.htm", status="integrated_live", notes=""),
                dict(source_id="lro-diviner-gcp", name="LRO Diviner Global Cumulative Product", provider="NASA PDS",
                     bodies=["Moon"], domains=["thermal", "temporal"], access="public", auth="none",
                     documentation_url="https://pds-geosciences.wustl.edu/missions/lro/diviner.htm", status="integrated_live",
                     notes="0.5-deg bins, 0.25 h local time; bolometric temperature")):
        db.upsert_source(**src)
    src_id = {"Earth": "aws-terrain-tiles", "Moon": "lro-lola-ldem64", "Mars": "pds-mola-megdr"}[body]
    for o in obs:
        db.upsert_observation(
            evidence_id=o["evidence_id"], site_id=sid, body=body, domain=DOMAIN.get(o["feature_id"], "topography"),
            quantity=o["feature_id"], value=o["value"], unit=o["unit"],
            kind="derived_measurement", statistic=f"AOI statistic at {o['analysis_scale_m']} m",
            temporal_support=f"{o['observation_period']['start'][:10]}..{o['observation_period']['end'][:10]}",
            spatial_support=f"~{SIDE_KM:.0f} km AOI; native {o['spatial_resolution_m']} m", crs=aoi.crs,
            qa_status=o["qa_status"], quality_flags=o["quality_flags"], uncertainty=o["uncertainty"],
            missing_reason=o["missing_reason"],
            source_id="lro-diviner-gcp" if o["unit"] == "K" else src_id, product_id=o["source_product"],
            asset_id=o["source_asset_ids"][0], processing=o["processing_version"],
            comparability="Common 1900 m scale and ~33 km metric AOI across bodies.")
    db.upsert_site(site_id=sid, name=name or sid, body=body, crs=aoi.crs, lon=lon, lat=lat, bbox=list(aoi.bbox))
    if body == "Earth":
        try:
            gateway.acquire_power(data_dir, sid, lon, lat, timeout=30)
        except Exception as error:  # noqa: BLE001
            errors.append(f"NASA POWER: {type(error).__name__}")
        db.upsert_site(site_id=sid, name=name or sid, body=body, crs=aoi.crs, lon=lon, lat=lat, bbox=list(aoi.bbox))
    gateway.store_constants(data_dir, [body])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, sort_keys=True))
    return doc


def load_sites(data_dir, body=None):
    out = []
    for p in sorted((Path(data_dir) / "sites").glob("*.json")):
        d = json.loads(p.read_text())
        if body is None or d["body"] == body:
            out.append(d)
    return out


def feature_vector(doc):
    return {o["feature_id"]: o["value"] for o in doc["observations"] if o["value"] is not None}


def prerank(target, candidates, weights=None):
    """Deterministic pre-ranking by normalized topographic distance (same features the engine scores)."""
    weights = weights or {"slope_deg": (0.4, 10.0), "roughness_m": (0.35, 150.0), "local_relief_m": (0.25, 1500.0)}
    t = feature_vector(target)
    ranked = []
    for c in candidates:
        v = feature_vector(c)
        num = den = 0.0
        for f, (w, tol) in weights.items():
            if f in t and f in v:
                num += w * max(0.0, 1 - abs(v[f] - t[f]) / tol)
                den += w
        ranked.append((round(num / den, 4) if den else 0.0, c))
    return sorted(ranked, key=lambda x: -x[0])
