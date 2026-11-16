"""Keyless global Earth DEM: AWS Open Data "Terrain Tiles" skadi 1 arc-second HGT (Mapzen/Tilezen).

https://registry.opendata.aws/terrain-tiles/  s3://elevation-tiles-prod/skadi/{N|S}yy/{N|S}yy{E|W}xxx.hgt.gz
Composite of SRTM (and, outside 56S..60N, other sources such as GMTED/ETOPO); voids filled by the producer.
Same HGT layout as SRTMGL1 (3601x3601 big-endian int16, -32768 void, EGM96 heights), so decoding and QA reuse
the verified SRTM code path. Flags record that this is a void-filled composite, not the LP DAAC product.
License: attribution required (see the registry page); no credential.
"""
from __future__ import annotations

import gzip
import math
from pathlib import Path
from typing import List, Optional, Sequence

from . import fetch
from .base import AOI, AcquisitionError, Candidate, Decoded, Granule, Issue, OutOfFootprintError, TimeWindow, \
    TruncatedAssetError, Validation
from .srtm import SRTM_WINDOW, TILE_POSTS, SRTMGL1Adapter, tile_name

BASE = "https://s3.amazonaws.com/elevation-tiles-prod/skadi/"


class SkadiAdapter(SRTMGL1Adapter):
    source_id = "AWS_TERRAIN_TILES_SKADI"
    product_id = "TERRAIN_TILES_SKADI_1ARCSEC"
    product_version = "skadi-v1"
    license_url = "https://github.com/tilezen/joerd/blob/master/docs/attribution.md"
    doc_url = "https://registry.opendata.aws/terrain-tiles/"

    def discover(self, aoi: AOI, time: Optional[TimeWindow], product: Optional[str] = None) -> List[Granule]:
        self.check_aoi(aoi)
        if aoi.south < -84 or aoi.north > 84:
            raise OutOfFootprintError("skadi tiles are used within 84S..84N", bbox=aoi.bbox)
        out = []
        for lat in range(math.floor(aoi.south), math.ceil(aoi.north)):
            for lon in range(math.floor(aoi.west), math.ceil(aoi.east)):
                name = tile_name(lat, lon)
                gid = f"{name}.SRTMGL1.hgt"       # granule id format reused so decode_hgt parses the tile origin
                url = f"{BASE}{name[:3]}/{name}.hgt.gz"
                out.append(Granule(self.source_id, self.product_id, self.product_version, gid, self.body,
                                   (lon, lat, lon + 1, lat + 1), SRTM_WINDOW,
                                   (Candidate(url, "data", f"{name}.hgt.gz"),), self.license_url, self.crs,
                                   "WGS84 lon/lat; 1 arc-second posts, tile origin at SW corner; EGM96 heights",
                                   {"catalog": "AWS Open Data terrain-tiles skadi", "tile": name}))
        return out

    def acquire(self, granules: Sequence[Granule], byte_budget: int, aoi: Optional[AOI] = None):
        out, spent = [], 0
        for g in granules:
            cand = g.candidates[0]
            hit = next((a for a in (fetch.asset_from_meta(m, g.observation, True)
                                    for m in fetch.find_cached(self.source_id, g.granule_id, "data", self.root))), None)
            if hit is not None:
                try:
                    fetch.verify_raw(hit)
                    out.append(hit)
                    continue
                except Exception:  # noqa: BLE001
                    pass
            if self.offline:
                raise AcquisitionError("offline and no verified cached skadi tile", url=cand.url)
            tr = fetch.Transcript(self.source_id, self.root)
            data, _ = fetch.http_get(cand.url, tr, max_bytes=40_000_000, timeout=120, retries=4)
            spent += len(data)
            if spent > byte_budget:
                raise AcquisitionError("skadi download exceeds byte budget", spent=spent, budget=byte_budget)
            if len(gzip.decompress(data)) != TILE_POSTS * TILE_POSTS * 2:
                raise TruncatedAssetError("skadi tile is not 3601x3601 int16", url=cand.url)
            meta = {"source_id": self.source_id, "product_id": self.product_id, "product_version": self.product_version,
                    "granule_id": g.granule_id, "body": "Earth", "role": "data", "source_url": cand.url,
                    "byte_size": len(data), "retrieved_at": fetch.now_utc(), "format": "gzip(HGT int16 big-endian)",
                    "crs": self.crs, "coordinate_conventions": g.coordinate_conventions, "license_url": self.license_url,
                    "byte_ranges": None, "parent_asset_ids": [], "transcript": tr.object_key,
                    "access_route": "public AWS Open Data (no credential)",
                    "observation_start": g.observation.start.isoformat(), "observation_end": g.observation.end.isoformat()}
            meta["asset_id"] = f"skadi-{g.granule_id[:7].lower()}-{fetch.sha256_bytes(data)[:12]}"
            path, key, digest = fetch.store_raw(data, filename=cand.filename, meta=meta, root=self.root)
            meta.update(path=str(path), object_key=key, sha256=digest)
            out.append(fetch.asset_from_meta(meta, g.observation, from_cache=False))
        return out

    def decode(self, assets, aoi: AOI, granule: Granule) -> Decoded:
        self.check_aoi(aoi)
        asset = assets[0]
        fetch.verify_raw(asset)
        hgt = gzip.decompress(Path(asset.path).read_bytes())
        d = self.decode_hgt(hgt, aoi, granule, (asset,), Path(asset.path).name)
        d.notes.append("AWS Terrain Tiles skadi composite (SRTM-based, producer void-filled)")
        return d

    def validate(self, decoded: Decoded) -> Validation:
        v = super().validate(decoded)
        v.issues.append(Issue("SKADI_COMPOSITE_PRODUCER_VOID_FILLED", "info",
                              ("Terrain Tiles composite; voids filled by the producer from other DEMs",)))
        if decoded.aoi.north > 60 or decoded.aoi.south < -56:
            v.issues.append(Issue("OUTSIDE_SRTM_COVERAGE_COARSER_SOURCE", "warning",
                                  ("outside SRTM latitudes the composite uses coarser sources (e.g. GMTED)",)))
        return v

    def clean(self, decoded: Decoded, approved_rules: Sequence[str]) -> Decoded:
        c = super().clean(decoded, approved_rules)
        c.quality_flags.append("SKADI_COMPOSITE_NOT_LPDAAC_SRTMGL1")
        if decoded.aoi.north > 60 or decoded.aoi.south < -56:
            c.quality_flags.append("OUTSIDE_SRTM_LATITUDES_COARSER_SOURCE")
        return c
