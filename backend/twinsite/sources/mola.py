"""MGS MOLA MEGDR (MGS-M-MOLA-5-MEGDR-L3-V1.0) Mars topography adapter.

Product facts (read from the product's own PDS3 label at run time, never assumed):
* 128 pixel/degree simple-cylindrical tiles, 44 deg x 90 deg, IAU2000
  planetocentric latitude, east-positive longitude 0..360;
* MEGT = MEDIAN_TOPOGRAPHY, MSB int16 metres = planetary radius minus areoid
  (GMM3 / mgm1025, degree and order 50); MEGC = COUNTS_PER_BIN, uint8 shots
  per cell -- 0 means the cell value is interpolated, not observed;
* cells are area-registered (cell medians); the product has no fill value
  (empty bins are interpolated by the producer).

Access: public PDS Geosciences Node (no credential).  Only the AOI rows/columns
are fetched with HTTP Range requests; each raw asset is the exact server bytes
of the listed ranges, concatenated in order, with the ranges in the manifest.

Mars metric distances use the label's sphere radius (A_AXIS_RADIUS, 3396.0 km);
no Earth ellipsoid or EPSG code is ever applied to Mars coordinates.
"""
from __future__ import annotations

import concurrent.futures
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .base import (
    AOI,
    AcquisitionError,
    ByteBudgetExceededError,
    Candidate,
    Decoded,
    DecodeError,
    FeatureSet,
    Granule,
    Grid,
    Issue,
    OutOfFootprintError,
    RawAsset,
    SourceAdapter,
    TimeMismatchError,
    TimeWindow,
    TruncatedAssetError,
    UnapprovedRuleError,
    Validation,
    VerticalDatumError,
    parse_utc,
)
from . import fetch, pds3

BASE = "https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/mgsl_300x/meg128/"
PPD = 128
MOLA_WINDOW = TimeWindow(parse_utc("1997-09-15T19:10:00"), parse_utc("2001-06-30T11:10:40"))
LAT_BANDS = ((88, "88n"), (44, "44n"), (0, "00n"), (-44, "44s"))  # (north edge, token)


def _sphere_dx(radius_m: float):
    def dx(lat_deg: float, dlon_deg: float) -> float:
        return radius_m * math.cos(math.radians(lat_deg)) * math.radians(dlon_deg)
    return dx


def _sphere_dy(radius_m: float):
    def dy(lat_deg: float, dlat_deg: float) -> float:
        return radius_m * math.radians(dlat_deg)
    return dy


def mars_lon360(lon: float) -> float:
    return lon % 360.0


class MOLAMEGDRAdapter(SourceAdapter):
    source_id = "MOLA_MEGDR"
    body = "Mars"
    product_id = "MGS-M-MOLA-5-MEGDR-L3-V1.0"
    product_version = "2.0"  # PRODUCT_VERSION_ID in the 128 ppd labels; re-checked at decode
    crs = "IAU_2000:49900"
    unit = "m"
    vertical_datum = "Mars areoid GMM3 (mgm1025, degree/order 50)"
    license_url = "https://pds.nasa.gov/datastandards/about/"
    doc_url = "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html"
    approved_rules = ("mola_flag_interpolated",)

    def __init__(self, root: Optional[Path] = None, offline: bool = False, workers: int = 6) -> None:
        self.root = root
        self.offline = offline
        self.workers = workers

    # ------------------------------------------------------------------ discover
    def tile_for(self, aoi: AOI) -> Tuple[str, int, int]:
        w, e = mars_lon360(aoi.west), mars_lon360(aoi.east)
        if e == 0.0 and aoi.east > aoi.west:
            e = 360.0
        if w >= e:
            raise OutOfFootprintError("AOI crosses the 0/360 meridian; split it", bbox=aoi.bbox)
        if aoi.north > 88 or aoi.south < -88:
            raise OutOfFootprintError("128 ppd MEGDR tiles cover 88S..88N only", bbox=aoi.bbox)
        band = next((b for b in LAT_BANDS if b[0] - 44 <= aoi.south and aoi.north <= b[0]), None)
        lon0 = int(w // 90) * 90
        if band is None or e > lon0 + 90:
            raise OutOfFootprintError("AOI spans more than one 44x90 degree MEGDR tile", bbox=aoi.bbox)
        return band[1], band[0], lon0

    def discover(self, aoi: AOI, time: Optional[TimeWindow], product: Optional[str] = None) -> List[Granule]:
        self.check_aoi(aoi)
        if product not in (None, self.product_id):
            raise AcquisitionError(f"adapter serves {self.product_id}, not {product}")
        if time is not None and not time.overlaps(MOLA_WINDOW):
            raise TimeMismatchError("requested window does not overlap MOLA mapping (1997-09..2001-06)",
                                    requested=f"{time.start.isoformat()}..{time.end.isoformat()}")
        tok, north, lon0 = self.tile_for(aoi)
        stem = f"meg{{kind}}{tok}{lon0:03d}hb"
        topo, count = stem.format(kind="t"), stem.format(kind="c")
        gid = topo.upper() + ".IMG"
        cands = (
            Candidate(BASE + topo + ".lbl", "label", topo + ".lbl"),
            Candidate(BASE + topo + ".img", "data", topo + ".img"),
            Candidate(BASE + count + ".lbl", "count_label", count + ".lbl"),
            Candidate(BASE + count + ".img", "count", count + ".img"),
        )
        return [Granule(self.source_id, self.product_id, self.product_version, gid, self.body,
                        (float(lon0), north - 44.0, lon0 + 90.0, float(north)), MOLA_WINDOW, cands,
                        self.license_url, self.crs,
                        "IAU2000 planetocentric lat, east-positive lon 0..360; simple cylindrical 128 ppd; "
                        "area-registered cell medians; heights above areoid",
                        {"catalog": "PDS Geosciences Node directory meg128", "tile": topo, "count_tile": count})]

    # ------------------------------------------------------------------ acquire
    def acquire(self, granules: Sequence[Granule], byte_budget: int, aoi: Optional[AOI] = None) -> List[RawAsset]:
        if aoi is None:
            raise AcquisitionError("MOLA acquisition is AOI-bounded; aoi is required")
        out: List[RawAsset] = []
        spent = 0
        for g in granules:
            tr = fetch.Transcript(self.source_id, self.root)
            labels: Dict[str, RawAsset] = {}
            for cand in g.candidates:
                if not cand.role.endswith("label"):
                    continue
                labels[cand.role] = self._get_whole(g, cand, tr, 200_000)
                spent += labels[cand.role].byte_size
            for role, lrole in (("data", "label"), ("count", "count_label")):
                cand = next(c for c in g.candidates if c.role == role)
                lab = pds3.parse_label(Path(labels[lrole].path).read_text(encoding="ascii", errors="replace"))
                ranges = self.byte_ranges(lab, aoi)
                need = sum(b - a + 1 for a, b in ranges)
                if spent + need > byte_budget:
                    raise ByteBudgetExceededError("MOLA AOI subset exceeds byte budget", need=need,
                                                  budget=byte_budget, spent=spent)
                asset = self._get_ranges(g, cand, ranges, tr, parent=labels[lrole].asset_id)
                spent += asset.byte_size
                out.append(asset)
            out.extend(labels.values())
        return out

    def _meta(self, g: Granule, cand: Candidate, size: int, fmt: str, tr, ranges=None, parent=None):
        return {
            "source_id": self.source_id, "product_id": self.product_id, "product_version": self.product_version,
            "granule_id": g.granule_id, "body": self.body, "role": cand.role, "source_url": cand.url,
            "byte_size": size, "retrieved_at": fetch.now_utc(), "format": fmt, "crs": self.crs,
            "coordinate_conventions": g.coordinate_conventions, "license_url": self.license_url,
            "byte_ranges": [list(r) for r in ranges] if ranges else None,
            "parent_asset_ids": [parent] if parent else [], "transcript": tr.object_key,
            "access_route": "public PDS Geosciences Node (no credential)",
            "observation_start": g.observation.start.isoformat(), "observation_end": g.observation.end.isoformat(),
        }

    def _cached(self, g: Granule, role: str, ranges=None) -> Optional[RawAsset]:
        for meta in fetch.find_cached(self.source_id, g.granule_id, role, self.root):
            if ranges is not None and [list(r) for r in ranges] != meta.get("byte_ranges"):
                continue
            asset = fetch.asset_from_meta(meta, g.observation, from_cache=True)
            try:
                fetch.verify_raw(asset)
            except Exception:
                continue
            return asset
        return None

    def _get_whole(self, g: Granule, cand: Candidate, tr, max_bytes: int) -> RawAsset:
        hit = self._cached(g, cand.role)
        if hit:
            tr.log(event="cache_hit", url=cand.url, sha256=hit.sha256, object_key=hit.object_key)
            return hit
        if self.offline:
            raise AcquisitionError("offline and no verified cached label", url=cand.url)
        data, _ = fetch.http_get(cand.url, tr, max_bytes=max_bytes, timeout=60, retries=4)
        meta = self._meta(g, cand, len(data), "PDS3 ODL label (ASCII)", tr)
        meta["asset_id"] = f"mola-{cand.filename.lower()}-{fetch.sha256_bytes(data)[:12]}"
        path, key, digest = fetch.store_raw(data, filename=cand.filename, meta=meta, root=self.root)
        meta.update(path=str(path), object_key=key, sha256=digest)
        return fetch.asset_from_meta(meta, g.observation, from_cache=False)

    def _get_ranges(self, g: Granule, cand: Candidate, ranges, tr, parent: str) -> RawAsset:
        hit = self._cached(g, cand.role, ranges)
        if hit:
            tr.log(event="cache_hit", url=cand.url, sha256=hit.sha256, object_key=hit.object_key)
            return hit
        if self.offline:
            raise AcquisitionError("offline and no verified cached subset", url=cand.url)

        def one(r):
            data, _ = fetch.http_get(cand.url, tr, byte_range=r, max_bytes=r[1] - r[0] + 1, timeout=60, retries=6)
            if len(data) != r[1] - r[0] + 1:
                raise TruncatedAssetError("range response length mismatch", range=r, got=len(data))
            return data

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.workers) as ex:
            parts = list(ex.map(one, ranges))
        data = b"".join(parts)
        fname = f"{cand.filename}.r{ranges[0][0]}-{ranges[-1][1]}.n{len(ranges)}.bin"
        meta = self._meta(g, cand, len(data), "concatenated HTTP byte ranges of PDS3 IMG", tr, ranges, parent)
        meta["asset_id"] = f"mola-{cand.filename.lower()}-sub-{fetch.sha256_bytes(data)[:12]}"
        path, key, digest = fetch.store_raw(data, filename=fname, meta=meta, root=self.root)
        meta.update(path=str(path), object_key=key, sha256=digest)
        return fetch.asset_from_meta(meta, g.observation, from_cache=False)

    # ------------------------------------------------------------------ layout from label
    @staticmethod
    def layout(lab: dict) -> dict:
        img = lab.get("OBJECT:IMAGE")
        proj = lab.get("OBJECT:IMAGE_MAP_PROJECTION")
        if img is None or proj is None:
            raise DecodeError("label lacks IMAGE or IMAGE_MAP_PROJECTION object")
        bits = int(img["SAMPLE_BITS"])
        st = str(img["SAMPLE_TYPE"])
        if (bits, st) == (16, "MSB_INTEGER"):
            fmt = ">h"
        elif (bits, st) == (8, "UNSIGNED_INTEGER"):
            fmt = ">B"
        else:
            raise DecodeError(f"unsupported sample type {st}/{bits}")
        if str(proj.get("MAP_PROJECTION_TYPE")) != "SIMPLE CYLINDRICAL":
            raise DecodeError("only SIMPLE CYLINDRICAL MEGDR tiles are supported")
        if str(proj.get("COORDINATE_SYSTEM_NAME")) != "PLANETOCENTRIC" or \
                str(proj.get("POSITIVE_LONGITUDE_DIRECTION")) != "EAST":
            raise DecodeError("expected planetocentric, east-positive coordinates")
        res = pds3.num(proj["MAP_RESOLUTION"])
        lines, samples = int(img["LINES"]), int(img["LINE_SAMPLES"])
        lpo, spo = pds3.num(proj["LINE_PROJECTION_OFFSET"]), pds3.num(proj["SAMPLE_PROJECTION_OFFSET"])
        clon = pds3.num(proj["CENTER_LONGITUDE"])
        # PDS simple cylindrical: lat(line) = (LPO - line)/res ; lon(sample) = CLON + (sample - SPO)/res
        lat_first = (lpo - 1) / res
        lon_first = clon + (1 - spo) / res
        maxlat, westlon = pds3.num(proj["MAXIMUM_LATITUDE"]), pds3.num(proj["WESTERNMOST_LONGITUDE"])
        if abs((lat_first + 0.5 / res) - maxlat) > 1e-6 or abs((lon_first - 0.5 / res) - westlon) > 1e-6:
            raise DecodeError("label projection offsets inconsistent with tile edges",
                              lat_first=lat_first, maxlat=maxlat, lon_first=lon_first, westlon=westlon)
        rec = int(lab["RECORD_BYTES"])
        if rec != samples * bits // 8:
            raise DecodeError("RECORD_BYTES does not match LINE_SAMPLES * SAMPLE_BITS")
        radius_km = pds3.num(proj["A_AXIS_RADIUS"])
        if abs(radius_km - pds3.num(proj["C_AXIS_RADIUS"])) > 1e-9:
            raise DecodeError("non-spherical map radius not supported")
        return {"fmt": fmt, "nbytes": bits // 8, "res": res, "lines": lines, "samples": samples,
                "lat_first": lat_first, "lon_first": lon_first, "record_bytes": rec, "radius_m": radius_km * 1000.0,
                "name": str(img.get("NAME")), "unit": str(img.get("UNIT", "")),
                "product_version": str(lab.get("PRODUCT_VERSION_ID", "")), "product_id": str(lab.get("PRODUCT_ID")),
                "data_set_id": str(lab.get("DATA_SET_ID")), "description": str(img.get("DESCRIPTION", ""))}

    def window(self, L: dict, aoi: AOI) -> Tuple[int, int, int, int]:
        """0-based inclusive line/sample window of cells whose centres lie inside the AOI."""
        res = L["res"]
        w, e = mars_lon360(aoi.west), mars_lon360(aoi.east) or 360.0
        l0 = math.ceil(L["lat_first"] * res - aoi.north * res - 1e-9)
        l1 = math.floor(L["lat_first"] * res - aoi.south * res + 1e-9)
        s0 = math.ceil((w - L["lon_first"]) * res - 1e-9)
        s1 = math.floor((e - L["lon_first"]) * res + 1e-9)
        if l0 < 0 or s0 < 0 or l1 >= L["lines"] or s1 >= L["samples"] or l1 < l0 or s1 < s0:
            raise OutOfFootprintError("AOI is outside this MEGDR tile", window=(l0, l1, s0, s1), bbox=aoi.bbox)
        return l0, l1, s0, s1

    def byte_ranges(self, lab: dict, aoi: AOI) -> List[Tuple[int, int]]:
        L = self.layout(lab)
        l0, l1, s0, s1 = self.window(L, aoi)
        nb = L["nbytes"]
        return [(ln * L["record_bytes"] + s0 * nb, ln * L["record_bytes"] + (s1 + 1) * nb - 1)
                for ln in range(l0, l1 + 1)]

    # ------------------------------------------------------------------ decode
    def decode(self, assets: Sequence[RawAsset], aoi: AOI, granule: Granule) -> Decoded:
        self.check_aoi(aoi)
        by_role = {a.role: a for a in assets}
        for need in ("data", "label", "count", "count_label"):
            if need not in by_role:
                raise DecodeError(f"missing {need} asset")
        for a in assets:
            fetch.verify_raw(a)
        Lt = self.layout(pds3.parse_label(Path(by_role["label"].path).read_text("ascii", "replace")))
        Lc = self.layout(pds3.parse_label(Path(by_role["count_label"].path).read_text("ascii", "replace")))
        if Lt["name"] != "MEDIAN_TOPOGRAPHY":
            raise VerticalDatumError(
                f"IMAGE is {Lt['name']!r}; only MEDIAN_TOPOGRAPHY (height above areoid) is accepted. "
                "PLANETARY_RADIUS / AREOID layers have a different vertical reference.",
                name=Lt["name"])
        if "areoid" not in Lt["description"].lower():
            raise VerticalDatumError("label does not state an areoid-referenced topography", name=Lt["name"])
        if Lt["unit"].upper() not in ("METER", "METERS"):
            raise DecodeError(f"unexpected unit {Lt['unit']!r}")
        if Lc["name"] != "COUNTS_PER_BIN":
            raise DecodeError("count asset is not COUNTS_PER_BIN")
        if (Lt["lines"], Lt["samples"], Lt["res"]) != (Lc["lines"], Lc["samples"], Lc["res"]):
            raise DecodeError("topography and count grids differ")
        win = self.window(Lt, aoi)
        topo = self._read_window(by_role["data"], Lt, win, aoi)
        cnt = self._read_window(by_role["count"], Lc, win, aoi)
        l0, l1, s0, s1 = win
        res = Lt["res"]
        lat0 = Lt["lat_first"] - l0 / res
        lon0 = Lt["lon_first"] + s0 / res
        nrows, ncols = l1 - l0 + 1, s1 - s0 + 1
        grid = Grid(nrows, ncols, lat0, lon0, 1 / res, 1 / res, [float(v) for v in topo], "area")
        support = Grid(nrows, ncols, lat0, lon0, 1 / res, 1 / res, [float(v) for v in cnt], "area")
        R = Lt["radius_m"]
        mid = (grid.lat(0) + grid.lat(nrows - 1)) / 2
        return Decoded(
            granule=granule, assets=tuple(assets), aoi=aoi, grid=grid, unit="m",
            vertical_datum=self.vertical_datum, horizontal_datum="IAU2000 Mars planetocentric",
            body_radius_m=R, radius_model=f"Mars sphere R={R:.0f} m (label A_AXIS_RADIUS)",
            native_resolution_m=max(_sphere_dx(R)(mid, 1 / res), _sphere_dy(R)(mid, 1 / res)),
            fill_value=None, fill_count=0, support=support,
            notes=[f"label PRODUCT_ID={Lt['product_id']} PRODUCT_VERSION_ID={Lt['product_version']}",
                   f"DATA_SET_ID={Lt['data_set_id']}"],
            transformations=[f"subset lines {l0}..{l1}, samples {s0}..{s1} of {Lt['lines']}x{Lt['samples']}",
                             "MSB int16 metres -> float metres (no scale/offset)",
                             f"AOI longitudes normalised to 0..360 east: {mars_lon360(aoi.west)}..{mars_lon360(aoi.east)}"],
        )

    def _read_window(self, asset: RawAsset, L: dict, win, aoi: AOI) -> List[int]:
        import struct

        l0, l1, s0, s1 = win
        ncols = s1 - s0 + 1
        nb = L["nbytes"]
        expected = [(ln * L["record_bytes"] + s0 * nb, ln * L["record_bytes"] + (s1 + 1) * nb - 1)
                    for ln in range(l0, l1 + 1)]
        if asset.byte_ranges is None or [tuple(r) for r in asset.byte_ranges] != expected:
            raise OutOfFootprintError("stored subset does not cover the requested AOI window",
                                      object_key=asset.object_key)
        raw = Path(asset.path).read_bytes()
        if len(raw) != ncols * nb * (l1 - l0 + 1):
            raise TruncatedAssetError("subset byte length does not match window", expected=ncols * nb * (l1 - l0 + 1),
                                      actual=len(raw))
        return list(struct.unpack(f">{ncols * (l1 - l0 + 1)}{L['fmt'][1]}", raw))

    # ------------------------------------------------------------------ validate / clean / features
    def validate(self, decoded: Decoded) -> Validation:
        if decoded.vertical_datum != self.vertical_datum:
            raise VerticalDatumError("MOLA heights must be areoid-referenced", got=decoded.vertical_datum)
        g, s = decoded.grid, decoded.support
        vals = [v for v in g.values if v is not None]
        observed = sum(1 for c in s.values if c and c > 0) if s else 0
        shot_frac = observed / g.n if g.n else 0.0
        issues = [Issue("MOLA_INTERPOLATED_CELLS", "warning" if shot_frac < 0.5 else "info",
                        (f"{g.n - observed} of {g.n} cells have zero MOLA shots (producer-interpolated); "
                         f"shot-supported fraction {shot_frac:.3f}",), "mola_flag_interpolated"),
                  Issue("GRID_SPACING_IS_NOT_SHOT_FOOTPRINT", "info",
                        ("463 m bins; along-track gaps up to ~12 km near equator (label)",))]
        bad = [v for v in vals if v < -8300 or v > 21300]
        if bad:
            issues.append(Issue("ELEVATION_OUTSIDE_PRODUCT_RANGE", "critical",
                                (f"{len(bad)} values outside label range -8208..21249 m",)))
        cov = len(vals) / g.n if g.n else 0.0
        verdict = "QUARANTINE" if bad else ("INSUFFICIENT" if cov < 0.65 else "ACCEPT")
        return Validation(verdict, issues, round(cov, 6), {
            "cells": g.n, "shot_supported_cells": observed, "shot_supported_fraction": round(shot_frac, 6),
            "min_m": min(vals) if vals else None, "max_m": max(vals) if vals else None,
            "max_shots_per_cell": max(s.values) if s else None,
        })

    def clean(self, decoded: Decoded, approved_rules: Sequence[str]) -> Decoded:
        bad = [r for r in approved_rules if r not in self.approved_rules]
        if bad:
            raise UnapprovedRuleError("cleaning rule not approved for MOLA MEGDR", rules=bad)
        tx = list(decoded.transformations)
        flags = list(decoded.quality_flags)
        if "mola_flag_interpolated" in approved_rules and decoded.support:
            observed = sum(1 for c in decoded.support.values if c > 0)
            frac = observed / decoded.support.n
            tx.append("mola_flag_interpolated: zero-shot cells retained (product values) and flagged; "
                      "no values altered")
            flags.append(f"MOLA_SHOT_SUPPORTED_FRACTION={frac:.3f}")
            flags.append("MOLA_INTERPOLATED_CELLS_RETAINED")
        return Decoded(**{**decoded.__dict__, "transformations": tx, "stage": "cleaned", "quality_flags": flags})

    def features(self, clean: Decoded, scale: float) -> FeatureSet:
        from twinsite.processing.dem_features import dem_features

        if clean.stage != "cleaned":
            raise UnapprovedRuleError("features require a cleaned product")
        R = clean.body_radius_m
        return dem_features(clean, scale, _sphere_dx(R), _sphere_dy(R),
                            "MOLA vertical precision ~1 m per shot (Smith et al. 2001); gridding/interpolation "
                            "error not propagated.")
