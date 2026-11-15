"""LRO LOLA GDR LDEM_64 (Moon topography) adapter.

Same PDS3 simple-cylindrical pipeline as MOLA MEGDR (byte-range AOI subsets, SHA-256 verified raw
assets, label-derived layout), with LOLA specifics:
  * LSB int16 DN; HEIGHT = DN * SCALING_FACTOR (0.5 m), relative to the 1737.4 km reference sphere
  * LINE/SAMPLE_PROJECTION_OFFSET are 0-based in LDEM labels (converted to the 1-based convention)
  * no per-cell shot-count layer at 64 ppd: the gridded surface is GMT 'surface' interpolated where
    coverage is incomplete; this is flagged, never hidden
Archive: https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/
"""
from __future__ import annotations

import copy
import math
from pathlib import Path
from typing import List, Optional, Sequence

from . import fetch, pds3
from .base import (AOI, AcquisitionError, Candidate, DecodeError, Decoded, Granule, Issue, OutOfFootprintError,
                   TimeWindow, Validation, VerticalDatumError, parse_utc)
from .mola import MOLAMEGDRAdapter, _sphere_dx, _sphere_dy, mars_lon360

BASE = "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/"
LOLA_WINDOW = TimeWindow(parse_utc("2009-07-13T17:33:17"), parse_utc("2016-11-29T05:48:19"))
REFERENCE_RADIUS_M = 1737400.0


class LOLAGDRAdapter(MOLAMEGDRAdapter):
    source_id = "LOLA_GDR"
    body = "Moon"
    product_id = "LRO-L-LOLA-4-GDR-V1.0:LDEM_64"
    product_version = "V3.1"
    crs = "IAU_2000:30100"
    unit = "m"
    vertical_datum = "Moon reference sphere R=1737.4 km (LOLA LDEM HEIGHT = DN x 0.5 m)"
    doc_url = "https://pds-geosciences.wustl.edu/missions/lro/lola.htm"
    approved_rules = ("lola_flag_interpolated",)
    asset_prefix = "lola"

    # ------------------------------------------------------------------ discover
    def discover(self, aoi: AOI, time: Optional[TimeWindow], product: Optional[str] = None) -> List[Granule]:
        self.check_aoi(aoi)
        if aoi.north > 90 or aoi.south < -90:
            raise OutOfFootprintError("latitude outside -90..90", bbox=aoi.bbox)
        w, e = mars_lon360(aoi.west), mars_lon360(aoi.east) or 360.0
        if w >= e:
            raise OutOfFootprintError("AOI crosses the 0/360 meridian; split it", bbox=aoi.bbox)
        cands = (Candidate(BASE + "ldem_64.lbl", "label", "ldem_64.lbl"),
                 Candidate(BASE + "ldem_64.img", "data", "ldem_64.img"))
        return [Granule(self.source_id, self.product_id, self.product_version, "LDEM_64.IMG", self.body,
                        (0.0, -90.0, 360.0, 90.0), LOLA_WINDOW, cands, self.license_url, self.crs,
                        "IAU2000 planetocentric lat, east-positive lon 0..360; simple cylindrical 64 ppd; "
                        "pixel-registered heights relative to 1737.4 km sphere",
                        {"catalog": "PDS Geosciences Node lola_gdr/cylindrical/img", "tile": "ldem_64"})]

    # ------------------------------------------------------------------ acquire (label whole, image by byte ranges)
    def acquire(self, granules: Sequence[Granule], byte_budget: int, aoi: Optional[AOI] = None):
        if aoi is None:
            raise AcquisitionError("LOLA acquisition is AOI-bounded; aoi is required")
        out = []
        for g in granules:
            tr = fetch.Transcript(self.source_id, self.root)
            label = self._get_whole(g, next(c for c in g.candidates if c.role == "label"), tr, 300_000)
            lab = self.normalize(pds3.parse_label(Path(label.path).read_text(encoding="ascii", errors="replace")))
            ranges = self.byte_ranges(lab, aoi)
            need = sum(b - a + 1 for a, b in ranges)
            if label.byte_size + need > byte_budget:
                raise AcquisitionError("LOLA AOI subset exceeds byte budget", need=need, budget=byte_budget)
            out.append(self._get_ranges(g, next(c for c in g.candidates if c.role == "data"), ranges, tr,
                                        parent=label.asset_id))
            out.append(label)
        return out

    @staticmethod
    def normalize(lab: dict) -> dict:
        """Flatten UNCOMPRESSED_FILE and convert 0-based projection offsets to the 1-based convention."""
        lab = copy.deepcopy(lab)
        uf = lab.get("OBJECT:UNCOMPRESSED_FILE")
        if uf:
            lab.setdefault("RECORD_BYTES", uf.get("RECORD_BYTES"))
            lab.setdefault("OBJECT:IMAGE", uf.get("OBJECT:IMAGE"))
        proj = lab.get("OBJECT:IMAGE_MAP_PROJECTION") or {}
        name = str(proj.get("COORDINATE_SYSTEM_NAME", ""))
        if name not in ("PLANETOCENTRIC", "MEAN EARTH/POLAR AXIS OF DE421"):
            raise DecodeError(f"unexpected LOLA coordinate system {name!r}")
        # LOLA's ME/DE421 body-fixed frame uses planetocentric latitude and east longitude (label DSMAP).
        proj["ORIGINAL_COORDINATE_SYSTEM_NAME"] = name
        proj["COORDINATE_SYSTEM_NAME"] = "PLANETOCENTRIC"
        for k in ("LINE_PROJECTION_OFFSET", "SAMPLE_PROJECTION_OFFSET"):
            proj[k] = pds3.num(proj[k]) + 1.0
        return lab

    def layout(self, lab: dict) -> dict:  # type: ignore[override]
        if "OBJECT:UNCOMPRESSED_FILE" in lab and "OBJECT:IMAGE" not in lab:
            lab = self.normalize(lab)
        L = MOLAMEGDRAdapter.layout(lab)
        img = lab["OBJECT:IMAGE"]
        L["scale"] = pds3.num(img.get("SCALING_FACTOR", 1.0))
        L["offset"] = pds3.num(img.get("OFFSET", 0.0))
        L["dn_min"], L["dn_max"] = pds3.num(img.get("MINIMUM")), pds3.num(img.get("MAXIMUM"))
        return L

    def byte_ranges(self, lab: dict, aoi: AOI):
        return super().byte_ranges(lab if "OBJECT:IMAGE" in lab else self.normalize(lab), aoi)

    # ------------------------------------------------------------------ decode
    def decode(self, assets, aoi: AOI, granule: Granule) -> Decoded:
        self.check_aoi(aoi)
        by_role = {a.role: a for a in assets}
        for need in ("data", "label"):
            if need not in by_role:
                raise DecodeError(f"missing {need} asset")
        for a in assets:
            fetch.verify_raw(a)
        L = self.layout(self.normalize(pds3.parse_label(Path(by_role["label"].path).read_text("ascii", "replace"))))
        if L["name"] != "HEIGHT":
            raise VerticalDatumError(f"IMAGE is {L['name']!r}; only HEIGHT (relative to reference sphere) is accepted")
        if abs(L["offset"] - REFERENCE_RADIUS_M) > 1 or abs(L["scale"] - 0.5) > 1e-9:
            raise DecodeError("unexpected LDEM scale/offset", scale=L["scale"], offset=L["offset"])
        if L["unit"].upper() not in ("METER", "METERS"):
            raise DecodeError(f"unexpected unit {L['unit']!r}")
        win = self.window(L, aoi)
        dn = self._read_window(by_role["data"], L, win, aoi)
        l0, l1, s0, s1 = win
        res = L["res"]
        from .base import Grid
        grid = Grid(l1 - l0 + 1, s1 - s0 + 1, L["lat_first"] - l0 / res, L["lon_first"] + s0 / res, 1 / res, 1 / res,
                    [v * L["scale"] for v in dn], "area")
        R = L["radius_m"]
        mid = (grid.lat(0) + grid.lat(grid.nrows - 1)) / 2
        return Decoded(
            granule=granule, assets=tuple(assets), aoi=aoi, grid=grid, unit="m", vertical_datum=self.vertical_datum,
            horizontal_datum="IAU2000 Moon planetocentric (mean Earth/polar axis)", body_radius_m=R,
            radius_model=f"Moon sphere R={R:.0f} m (label A_AXIS_RADIUS)",
            native_resolution_m=max(_sphere_dx(R)(mid, 1 / res), _sphere_dy(R)(mid, 1 / res)),
            fill_value=None, fill_count=0, support=None,
            notes=["frame: Mean Earth/Polar Axis of DE421 (planetocentric lat, east lon)",
                   f"label PRODUCT_ID={L['product_id']} PRODUCT_VERSION_ID={L['product_version']}",
                   f"DATA_SET_ID={L['data_set_id']}"],
            transformations=[f"subset lines {l0}..{l1}, samples {s0}..{s1} of {L['lines']}x{L['samples']}",
                             "LSB int16 DN -> metres: HEIGHT = DN x 0.5 (label SCALING_FACTOR)",
                             f"AOI longitudes normalised to 0..360 east: {mars_lon360(aoi.west)}..{mars_lon360(aoi.east)}"])

    # ------------------------------------------------------------------ validate / clean / features
    def validate(self, decoded: Decoded) -> Validation:
        if decoded.vertical_datum != self.vertical_datum:
            raise VerticalDatumError("LOLA heights must be sphere-referenced", got=decoded.vertical_datum)
        g = decoded.grid
        vals = [v for v in g.values if v is not None]
        bad = [v for v in vals if v < -9200 or v > 10800]
        issues = [Issue("LOLA_GRIDDED_SURFACE_INTERPOLATION", "info",
                        ("LDEM_64 is a GMT 'surface' gridding of LOLA shots; cells without shots are interpolated "
                         "and no per-cell count exists at 64 ppd (label)",), "lola_flag_interpolated"),
                  Issue("LATITUDE_BAND_EDGE_ARTIFACTS_POSSIBLE", "info",
                        ("grids built in 45-degree latitude bands; edge artifacts possible (label)",))]
        if bad:
            issues.append(Issue("ELEVATION_OUTSIDE_PRODUCT_RANGE", "critical",
                                (f"{len(bad)} values outside label range -9125.5..10773 m",)))
        cov = len(vals) / g.n if g.n else 0.0
        verdict = "QUARANTINE" if bad else ("INSUFFICIENT" if cov < 0.65 else "ACCEPT")
        return Validation(verdict, issues, round(cov, 6), {"cells": g.n, "min_m": min(vals) if vals else None,
                                                           "max_m": max(vals) if vals else None})

    def clean(self, decoded: Decoded, approved_rules: Sequence[str]) -> Decoded:
        from .base import UnapprovedRuleError
        bad = [r for r in approved_rules if r not in self.approved_rules]
        if bad:
            raise UnapprovedRuleError("cleaning rule not approved for LOLA GDR", rules=bad)
        tx, flags = list(decoded.transformations), list(decoded.quality_flags)
        if "lola_flag_interpolated" in approved_rules:
            tx.append("lola_flag_interpolated: gridded values retained unchanged and flagged as partly interpolated")
            flags.append("LOLA_GRIDDED_SURFACE_PARTLY_INTERPOLATED")
        return Decoded(**{**decoded.__dict__, "transformations": tx, "stage": "cleaned", "quality_flags": flags})

    def features(self, clean: Decoded, scale: float):
        from twinsite.processing.dem_features import dem_features
        from .base import UnapprovedRuleError
        if clean.stage != "cleaned":
            raise UnapprovedRuleError("features require a cleaned product")
        R = clean.body_radius_m
        return dem_features(clean, scale, _sphere_dx(R), _sphere_dy(R),
                            "LOLA ranging precision ~10 cm, radial accuracy ~1 m (Smith et al. 2010/2017); gridding "
                            "interpolation error not propagated.")

    def supported_scale(self, decoded: Decoded, minimum: float, max_block: int = 6) -> float:
        """No shot-count layer: use 4 native cells (~1.9 km), matching the MOLA/SRTM analysis scale family."""
        return math.ceil(4 * decoded.native_resolution_m * 10) / 10
