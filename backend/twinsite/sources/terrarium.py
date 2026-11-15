"""Keyless, bandwidth-light Earth DEM: AWS Open Data Terrain Tiles, "terrarium" PNG encoding (Tilezen/Mapzen).

https://registry.opendata.aws/terrain-tiles/   s3://elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
height_m = R*256 + G + B/256 - 32768 (Web Mercator tiles, 256 px). Zoom 11 (~76 m at the equator) keeps a
33 km AOI to ~9 tiles (~1 MB) instead of a 10 MB 1-degree HGT. Each tile is a SHA-256 verified raw asset; the
mosaic is resampled (nearest pixel centre) onto a regular lat/lon grid, which is recorded as a transformation.
Sources (producer composite): SRTM, GMTED, ETOPO1, NED and others; heights relative to mean sea level.
"""
from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path
from typing import List, Optional, Sequence

from . import fetch
from .base import AOI, AcquisitionError, Candidate, DecodeError, Decoded, Granule, Grid, Issue, OutOfFootprintError, \
    TimeWindow, Validation
from .srtm import SRTM_WINDOW, SRTMGL1Adapter, _A, earth_dx, earth_dy

BASE = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
ZOOM = 11


def lonlat_to_tile(lon, lat, z=ZOOM):
    n = 2 ** z
    x = (lon + 180.0) / 360.0 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile_to_lonlat(x, y, z=ZOOM):
    n = 2 ** z
    return x / n * 360.0 - 180.0, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))


def decode_png(data: bytes):
    """Minimal PNG decoder (8-bit RGB/RGBA, non-interlaced) -> (width, height, rows of RGB tuples)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise DecodeError("not a PNG")
    pos, idat, ihdr = 8, [], None
    while pos < len(data):
        (length,), ctype = struct.unpack(">I", data[pos:pos + 4]), data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + length]
        if zlib.crc32(ctype + chunk) & 0xffffffff != struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])[0]:
            raise DecodeError("PNG chunk CRC mismatch")
        if ctype == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", chunk)
        elif ctype == b"IDAT":
            idat.append(chunk)
        elif ctype == b"IEND":
            break
        pos += 12 + length
    if ihdr is None:
        raise DecodeError("PNG without IHDR")
    w, h, depth, color, _, _, interlace = ihdr
    if depth != 8 or color not in (2, 6) or interlace:
        raise DecodeError("unsupported PNG format", depth=depth, color=color, interlace=interlace)
    bpp = 3 if color == 2 else 4
    raw = zlib.decompress(b"".join(idat))
    stride = w * bpp
    prev = bytearray(stride)
    rows = []
    for r in range(h):
        f = raw[r * (stride + 1)]
        line = bytearray(raw[r * (stride + 1) + 1:(r + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if f == 1:
                line[i] = (line[i] + a) & 255
            elif f == 2:
                line[i] = (line[i] + b) & 255
            elif f == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
            elif f != 0:
                raise DecodeError("bad PNG filter", filter=f)
        rows.append(bytes(line))
        prev = line
    return w, h, bpp, rows


class TerrariumAdapter(SRTMGL1Adapter):
    source_id = "AWS_TERRAIN_TILES_TERRARIUM"
    product_id = "TERRAIN_TILES_TERRARIUM_Z11"
    product_version = "terrarium-v1"
    license_url = "https://github.com/tilezen/joerd/blob/master/docs/attribution.md"
    doc_url = "https://registry.opendata.aws/terrain-tiles/"

    def discover(self, aoi: AOI, time: Optional[TimeWindow], product: Optional[str] = None) -> List[Granule]:
        self.check_aoi(aoi)
        if abs(aoi.south) > 84 or abs(aoi.north) > 84:
            raise OutOfFootprintError("terrarium tiles used within 84S..84N", bbox=aoi.bbox)
        x0, y0 = lonlat_to_tile(aoi.west, aoi.north)
        x1, y1 = lonlat_to_tile(aoi.east, aoi.south)
        tiles = [(x, y) for y in range(int(y0), int(y1) + 1) for x in range(int(x0), int(x1) + 1)]
        if len(tiles) > 25:
            raise AcquisitionError("AOI needs too many terrarium tiles", n=len(tiles))
        cands = tuple(Candidate(f"{BASE}{ZOOM}/{x}/{y}.png", f"tile:{x}:{y}", f"z{ZOOM}_{x}_{y}.png") for x, y in tiles)
        gid = f"terrarium-z{ZOOM}-{int(x0)}-{int(y0)}-{int(x1)}-{int(y1)}"
        return [Granule(self.source_id, self.product_id, self.product_version, gid, self.body, aoi.bbox, SRTM_WINDOW,
                        cands, self.license_url, self.crs,
                        "Web Mercator z11 256 px tiles; terrarium RGB encoding; heights above mean sea level",
                        {"catalog": "AWS Open Data terrain-tiles terrarium", "tiles": len(tiles)})]

    def acquire(self, granules: Sequence[Granule], byte_budget: int, aoi: Optional[AOI] = None):
        out, spent = [], 0
        g = granules[0]
        tr = fetch.Transcript(self.source_id, self.root)
        for cand in g.candidates:
            hit = None
            for meta in fetch.find_cached(self.source_id, cand.filename, "data", self.root):
                try:
                    hit = fetch.asset_from_meta(meta, g.observation, True)
                    fetch.verify_raw(hit)
                    break
                except Exception:  # noqa: BLE001
                    hit = None
            if hit:
                out.append(hit)
                continue
            if self.offline:
                raise AcquisitionError("offline and no verified cached terrarium tile", url=cand.url)
            data, _ = fetch.http_get(cand.url, tr, max_bytes=2_000_000, timeout=60, retries=4)
            spent += len(data)
            if spent > byte_budget:
                raise AcquisitionError("terrarium download exceeds byte budget", spent=spent)
            meta = {"source_id": self.source_id, "product_id": self.product_id, "product_version": self.product_version,
                    "granule_id": cand.filename, "body": "Earth", "role": "data", "source_url": cand.url, "byte_size": len(data),
                    "retrieved_at": fetch.now_utc(), "format": "PNG terrarium (RGB-encoded heights)", "crs": "EPSG:3857 tile",
                    "coordinate_conventions": g.coordinate_conventions, "license_url": self.license_url, "byte_ranges": None,
                    "parent_asset_ids": [], "transcript": tr.object_key, "access_route": "public AWS Open Data (no credential)",
                    "observation_start": g.observation.start.isoformat(), "observation_end": g.observation.end.isoformat()}
            meta["asset_id"] = f"terrarium-z{ZOOM}-{cand.filename[4:-4]}-{fetch.sha256_bytes(data)[:12]}"
            path, key, digest = fetch.store_raw(data, filename=cand.filename, meta=meta, root=self.root)
            meta.update(path=str(path), object_key=key, sha256=digest)
            out.append(fetch.asset_from_meta(meta, g.observation, from_cache=False))
        return out

    def decode(self, assets, aoi: AOI, granule: Granule) -> Decoded:
        self.check_aoi(aoi)
        tiles = {}
        for a in assets:
            fetch.verify_raw(a)
            _, x, y = Path(a.path).name.split(".")[0].split("_")[:3] if Path(a.path).name.startswith("z") else (None, None, None)
            name = a.granule_id[:-4]          # z11_x_y
            _, x, y = name.split("_")
            w, h, bpp, rows = decode_png(Path(a.path).read_bytes())
            if (w, h) != (256, 256):
                raise DecodeError("terrarium tile is not 256x256")
            tiles[(int(x), int(y))] = (rows, bpp)
        step = 1 / 3600 * 2                    # 2 arc-seconds (~60 m) regular output grid, finer than the source (~76 m)
        nrows = int((aoi.north - aoi.south) / step) + 1
        ncols = int((aoi.east - aoi.west) / step) + 1
        vals, missing = [], 0
        for r in range(nrows):
            lat = aoi.north - r * step
            for c in range(ncols):
                lon = aoi.west + c * step
                fx, fy = lonlat_to_tile(lon, lat)
                t = tiles.get((int(fx), int(fy)))
                if t is None:
                    vals.append(None)
                    missing += 1
                    continue
                rows, bpp = t
                px, py = min(255, int((fx % 1) * 256)), min(255, int((fy % 1) * 256))
                R, G, B = rows[py][px * bpp:px * bpp + 3]
                vals.append(R * 256 + G + B / 256 - 32768)
        grid = Grid(nrows, ncols, aoi.north, aoi.west, step, step, vals, "point")
        mid = (aoi.north + aoi.south) / 2
        return Decoded(
            granule=granule, assets=tuple(assets), aoi=aoi, grid=grid, unit="m", vertical_datum=self.vertical_datum,
            horizontal_datum="WGS84", body_radius_m=_A, radius_model="WGS84 ellipsoid local radii",
            native_resolution_m=max(earth_dx(mid, 360 / 2 ** ZOOM / 256), earth_dy(mid, 360 / 2 ** ZOOM / 256 * math.cos(math.radians(mid)))),
            fill_value=None, fill_count=missing,
            notes=["AWS Terrain Tiles terrarium composite (SRTM/GMTED/ETOPO/NED); heights ~ mean sea level"],
            transformations=[f"mosaic {len(tiles)} z{ZOOM} Web Mercator tiles",
                             "terrarium decode: h = R*256 + G + B/256 - 32768 m",
                             "resample: nearest source pixel to a regular 2 arc-second lat/lon grid (no smoothing)"])

    def validate(self, decoded: Decoded) -> Validation:
        v = super().validate(decoded)
        v.issues.append(Issue("TERRARIUM_COMPOSITE_RESAMPLED", "info",
                              ("producer composite of several DEMs, Web Mercator z11 (~76 m at equator), "
                               "nearest-pixel resampled to 2 arc-seconds",)))
        return v

    def clean(self, decoded: Decoded, approved_rules: Sequence[str]) -> Decoded:
        c = super().clean(decoded, approved_rules)
        c.quality_flags.append("TERRARIUM_COMPOSITE_NOT_LPDAAC_SRTMGL1")
        return c
