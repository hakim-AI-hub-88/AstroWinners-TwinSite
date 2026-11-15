"""LRO Diviner Global Cumulative Product (GCP) adapter: lunar surface (bolometric) temperatures.

Product: LRO-L-DLRE-5-GCP-V1.0, GLOBAL_CUMUL_AVG_CYL_<band>_002.TAB (Williams et al. 2017, Icarus 283).
Fixed-width ASCII, 113-byte records (record 1 is a header naming the columns); 0.5 deg lat/lon bins x 0.25 h
local time; row order = longitude (720) -> latitude (20 per 10-deg band) -> local time (96).
Columns: clon, clat, ltim, t3..t9 (channel brightness temperatures), tbol (bolometric temperature, K).
-9999 marks bins with no observations; non-positive values are below channel sensitivity and are rejected.

Pipeline: AOI -> exact byte ranges (one contiguous block per longitude bin) -> SHA-256 stored raw asset ->
parse + verify every row's clon/clat/ltim against the expected bin (catches any offset error) ->
per-bin daytime maximum and night (18h-06h) minimum of tbol -> AOI median with p10-p90 spatial interval.
"""
from __future__ import annotations

import math
import statistics
from typing import Dict, List, Tuple

from . import fetch
from .base import AOI, AcquisitionError, DecodeError, TimeWindow, TruncatedAssetError, parse_utc

BASE = "https://pds-geosciences.wustl.edu/lro/urn-nasa-pds-lro_diviner_derived1/data_derived_gcp/"
SOURCE_ID, PRODUCT_ID, VERSION = "DIVINER_GCP", "LRO-L-DLRE-5-GCP-V1.0", "002"
WINDOW = TimeWindow(parse_utc("2009-07-05T16:50:26"), parse_utc("2015-04-01T00:00:00"))
REC, NLON, NLAT, NT, BIN = 113, 720, 20, 96, 0.5
HEADER = "clon,clat,ltim,t3,t4,t5,t6,t7,t8,t9,tbol"
CRS = "IAU_2000:30100"
DOC = "https://pds-geosciences.wustl.edu/missions/lro/diviner.htm"


def files_for(aoi: AOI) -> Tuple[str, float]:
    lo = math.floor(aoi.south / 10) * 10
    if aoi.north > lo + 10 + 1e-9:
        raise AcquisitionError("AOI spans more than one 10-degree Diviner GCP band; split it", bbox=aoi.bbox)
    # PDS naming: northern bands south->north (00n10n), southern bands as e.g. 10s00s, 90s80s.
    name = f"{lo:02d}n{lo + 10:02d}n" if lo >= 0 else f"{abs(lo):02d}s{abs(lo + 10):02d}s"
    return f"global_cumul_avg_cyl_{name}_002.tab", float(lo)


def bins(aoi: AOI, lat_lo: float):
    """Inclusive (ilon0, ilon1, ilat0, ilat1) of bins whose centres fall inside the AOI (lon -180..180 east)."""
    ilon0 = math.ceil((aoi.west + 180) / BIN - 0.5 - 1e-9)
    ilon1 = math.floor((aoi.east + 180) / BIN - 0.5 + 1e-9)
    ilat0 = math.ceil((aoi.south - lat_lo) / BIN - 0.5 - 1e-9)
    ilat1 = math.floor((aoi.north - lat_lo) / BIN - 0.5 + 1e-9)
    if ilon0 < 0 or ilon1 >= NLON or ilat0 < 0 or ilat1 >= NLAT or ilon1 < ilon0 or ilat1 < ilat0:
        raise AcquisitionError("AOI contains no complete Diviner 0.5-degree bin centre", bbox=aoi.bbox)
    return ilon0, ilon1, ilat0, ilat1


def byte_ranges(b) -> List[Tuple[int, int]]:
    ilon0, ilon1, ilat0, ilat1 = b
    out = []
    for ilon in range(ilon0, ilon1 + 1):
        first = (ilon * NLAT + ilat0) * NT          # 0-based data row
        last = (ilon * NLAT + ilat1) * NT + NT - 1
        out.append(((first + 1) * REC, (last + 2) * REC - 1))   # +1: header record
    return out


def acquire(aoi: AOI, root=None, offline=False):
    if aoi.body != "Moon":
        raise AcquisitionError("Diviner serves the Moon only", body=aoi.body)
    fname, lat_lo = files_for(aoi)
    b = bins(aoi, lat_lo)
    ranges = byte_ranges(b)
    url = BASE + fname
    gid = fname.upper()
    for meta in fetch.find_cached(SOURCE_ID, gid, "data", root):
        if meta.get("byte_ranges") == [list(r) for r in ranges]:
            asset = fetch.asset_from_meta(meta, WINDOW, from_cache=True)
            try:
                fetch.verify_raw(asset)
                return asset, b, lat_lo
            except Exception:  # noqa: BLE001 - re-download a corrupt cache entry
                pass
    if offline:
        raise AcquisitionError("offline and no verified cached Diviner subset", url=url)
    tr = fetch.Transcript(SOURCE_ID, root)
    head, _ = fetch.http_get(url, tr, byte_range=(0, REC - 1), max_bytes=REC, timeout=60, retries=4)
    if head.decode("ascii").replace(" ", "").strip() != HEADER:
        raise DecodeError("Diviner GCP header does not match the expected column layout", header=head[:120])
    parts = []
    for r in ranges:
        data, _ = fetch.http_get(url, tr, byte_range=r, max_bytes=r[1] - r[0] + 1, timeout=60, retries=6)
        if len(data) != r[1] - r[0] + 1:
            raise TruncatedAssetError("range response length mismatch", range=r, got=len(data))
        parts.append(data)
    data = b"".join(parts)
    meta = {"source_id": SOURCE_ID, "product_id": PRODUCT_ID, "product_version": VERSION, "granule_id": gid,
            "body": "Moon", "role": "data", "source_url": url, "byte_size": len(data),
            "retrieved_at": fetch.now_utc(), "format": "fixed-width ASCII table rows (113 B) from PDS3 GCP TAB",
            "crs": CRS, "coordinate_conventions": "planetocentric lat, east lon -180..180; 0.5 deg bins; local time hours",
            "license_url": "https://pds.nasa.gov/datastandards/about/", "byte_ranges": [list(r) for r in ranges],
            "parent_asset_ids": [], "transcript": tr.object_key, "access_route": "public PDS Geosciences Node",
            "observation_start": WINDOW.start.isoformat(), "observation_end": WINDOW.end.isoformat()}
    meta["asset_id"] = f"diviner-{gid.lower()}-sub-{fetch.sha256_bytes(data)[:12]}"
    path, key, digest = fetch.store_raw(data, filename=f"{fname}.sub.bin", meta=meta, root=root)
    meta.update(path=str(path), object_key=key, sha256=digest)
    return fetch.asset_from_meta(meta, WINDOW, from_cache=False), b, lat_lo


def decode(asset, b, lat_lo) -> Dict[Tuple[int, int], List[Tuple[float, float]]]:
    """{(ilon, ilat): [(ltim, tbol_K), ...]} with every row's coordinates verified."""
    fetch.verify_raw(asset)
    raw = open(asset.path, "rb").read()
    ilon0, ilon1, ilat0, ilat1 = b
    expected_rows = (ilon1 - ilon0 + 1) * (ilat1 - ilat0 + 1) * NT
    if len(raw) != expected_rows * REC:
        raise TruncatedAssetError("Diviner subset length mismatch", expected=expected_rows * REC, got=len(raw))
    out: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
    i = 0
    for ilon in range(ilon0, ilon1 + 1):
        for ilat in range(ilat0, ilat1 + 1):
            for it in range(NT):
                row = raw[i * REC:(i + 1) * REC].decode("ascii").split(",")
                i += 1
                clon, clat, ltim, tbol = float(row[0]), float(row[1]), float(row[2]), float(row[10])
                if abs(clon - (-180 + (ilon + 0.5) * BIN)) > 1e-6 or abs(clat - (lat_lo + (ilat + 0.5) * BIN)) > 1e-6 \
                        or abs(ltim - (it + 0.5) * 0.25) > 0.011:
                    raise DecodeError("Diviner row does not match the expected bin (layout/offset error)",
                                      ilon=ilon, ilat=ilat, it=it, got=(clon, clat, ltim))
                out.setdefault((ilon, ilat), []).append((ltim, tbol))
    return out


def _pct(vals, q):
    s = sorted(vals)
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)


def features(cells):
    """Per bin: day max and night (18-06 h) min of valid tbol; AOI medians. Returns dict feature -> detail."""
    day, night, amp, slot_cov = [], [], [], []
    for samples in cells.values():
        valid = [(t, v) for t, v in samples if v != -9999 and v > 0]
        slot_cov.append(len(valid) / NT)
        d = [v for t, v in valid if 6 <= t < 18]
        n = [v for t, v in valid if t >= 18 or t < 6]
        if d:
            day.append(max(d))
        if n:
            night.append(min(n))
        if d and n:
            amp.append(max(d) - min(n))
    ncell = len(cells)
    out = {}
    for fid, vals, defn in (
        ("surface_temperature_day_K", day, "AOI median of per-bin maximum daytime (06-18 h) Diviner bolometric temperature"),
        ("surface_temperature_night_K", night, "AOI median of per-bin minimum night (18-06 h) Diviner bolometric temperature"),
        ("surface_temperature_diurnal_range_K", amp, "AOI median of per-bin (day max - night min) bolometric temperature"),
    ):
        cov = len(vals) / ncell if ncell else 0.0
        ok = cov >= 0.65 and len(vals) >= 3
        out[fid] = {"value": round(statistics.median(vals), 3) if ok else None, "unit": "K",
                    "coverage": round(cov, 4), "n_bins": len(vals), "definition": defn,
                    "interval": [round(_pct(vals, 0.1), 3), round(_pct(vals, 0.9), 3)] if ok else [None, None],
                    "missing_reason": None if ok else f"only {len(vals)}/{ncell} bins have valid samples"}
    out["_meta"] = {"bins": ncell, "mean_local_time_slot_coverage": round(sum(slot_cov) / len(slot_cov), 4) if slot_cov else 0}
    return out
