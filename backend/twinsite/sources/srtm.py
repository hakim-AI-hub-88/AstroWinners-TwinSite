"""SRTMGL1 v003 (NASA/USGS LP DAAC) Earth DEM adapter.

Product facts (SRTM Quick Guide; LP DAAC SRTMGL1 user guide):
* 1x1 degree tiles, 3601x3601 posts, 1 arc-second spacing, point registered:
  post (0,0) is exactly at (lat = N+1, lon = W) of tile name N..W...
* big-endian signed 16-bit integers, metres; void = -32768.
* horizontal WGS84 (EPSG:4326); heights relative to the EGM96 geoid.
* acquisition 2000-02-11 .. 2000-02-22 (STS-99); CMR temporal extent ends
  2000-02-21T23:59:59Z, which is what we record.

Access: the authoritative URL (from CMR) is LP DAAC Cloud, which requires
Earthdata Login.  Without ``EARTHDATA_TOKEN`` the adapter records the
credential gap and the server's actual redirect, then uses the documented
public mirror (ESA STEP SNAP auxdata, which redistributes the SRTMGL1 tiles
under the same file names).  Mirror bytes cannot be checked against the LP DAAC
checksum without a credential, so mirror assets carry the quality flag
``MIRROR_NOT_VERIFIED_AGAINST_LPDAAC``.
"""
from __future__ import annotations

import io
import json
import math
import os
import struct
import urllib.parse
import zipfile
from pathlib import Path
from typing import List, Optional, Sequence

from .base import (
    ADAPTER_VERSION,
    AOI,
    AcquisitionError,
    ByteBudgetExceededError,
    Candidate,
    CredentialMissingError,
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
from . import fetch
from .credentials import earthdata_token

TILE_POSTS = 3601
VOID = -32768
# WGS84
_A = 6378137.0
_F = 1 / 298.257223563
_E2 = _F * (2 - _F)
CMR_GRANULES = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
MIRROR_BASE = "https://step.esa.int/auxdata/dem/SRTMGL1/"
# SRTM acquisition window; used only if CMR is unreachable AND a cached granule exists.
SRTM_WINDOW = TimeWindow(parse_utc("2000-02-11T00:00:00Z"), parse_utc("2000-02-21T23:59:59Z"))


def earth_dx(lat_deg: float, dlon_deg: float) -> float:
    s = math.sin(math.radians(lat_deg))
    n = _A / math.sqrt(1 - _E2 * s * s)
    return n * math.cos(math.radians(lat_deg)) * math.radians(dlon_deg)


def earth_dy(lat_deg: float, dlat_deg: float) -> float:
    s = math.sin(math.radians(lat_deg))
    m = _A * (1 - _E2) / (1 - _E2 * s * s) ** 1.5
    return m * math.radians(dlat_deg)


def tile_name(lat_floor: int, lon_floor: int) -> str:
    return f"{'N' if lat_floor >= 0 else 'S'}{abs(lat_floor):02d}{'E' if lon_floor >= 0 else 'W'}{abs(lon_floor):03d}"


class SRTMGL1Adapter(SourceAdapter):
    source_id = "SRTMGL1"
    body = "Earth"
    product_id = "SRTMGL1"
    product_version = "003"
    crs = "EPSG:4326"
    unit = "m"
    vertical_datum = "EGM96 geoid"
    horizontal_datum = "WGS84"
    license_url = "https://lpdaac.usgs.gov/data/data-citation-and-policies/"
    doc_url = "https://www.earthdata.nasa.gov/s3fs-public/2025-05/SRTM_Quick_Guide.pdf"
    approved_rules = ("srtm_void_mask",)

    def __init__(self, root: Optional[Path] = None, offline: bool = False, request_timeout: float = 120, request_retries: int = 8) -> None:
        self.root = root
        self.offline = offline
        self.request_timeout = request_timeout
        self.request_retries = request_retries

    # ------------------------------------------------------------------ discover
    def discover(self, aoi: AOI, time: Optional[TimeWindow], product: Optional[str] = None) -> List[Granule]:
        self.check_aoi(aoi)
        if product not in (None, self.product_id):
            raise AcquisitionError(f"adapter serves {self.product_id}, not {product}")
        if aoi.south < -56.0 or aoi.north > 60.0:
            raise OutOfFootprintError("SRTM covers 56S..60N only", bbox=aoi.bbox)
        if aoi.west < -180 or aoi.east > 180:
            raise OutOfFootprintError("Earth longitudes must be within -180..180", bbox=aoi.bbox)
        if time is not None and not time.overlaps(SRTM_WINDOW):
            raise TimeMismatchError("requested time window does not overlap the SRTM acquisition (Feb 2000)",
                                    requested=f"{time.start.isoformat()}..{time.end.isoformat()}")
        granules = []
        for lat in range(math.floor(aoi.south), math.ceil(aoi.north)):
            for lon in range(math.floor(aoi.west), math.ceil(aoi.east)):
                name = tile_name(lat, lon)
                granules.append(self._granule(name, lat, lon))
        return granules

    def _granule(self, name: str, lat: int, lon: int) -> Granule:
        gid = f"{name}.SRTMGL1.hgt"
        evidence = {"catalog": "NASA CMR", "query": None, "hits": None, "concept_id": None}
        observation = SRTM_WINDOW
        official = (f"https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/SRTMGL1.003/"
                    f"{gid}/{gid}.zip")
        if self.offline:
            # Reuse the catalog evidence captured when the cached bytes were acquired.
            for meta in fetch.find_cached(self.source_id, gid, "data", self.root):
                ce = meta.get("catalog_evidence") or {}
                if ce.get("concept_id"):
                    evidence = {**ce, "restored_from_cached_asset": meta["asset_id"]}
                    observation = TimeWindow(parse_utc(meta["observation_start"].replace("+00:00", "")),
                                             parse_utc(meta["observation_end"].replace("+00:00", "")))
                    break
        else:
            q = urllib.parse.urlencode({"short_name": "SRTMGL1", "version": "003", "readable_granule_name": gid,
                                        "page_size": 5})
            url = f"{CMR_GRANULES}?{q}"
            tr = fetch.Transcript(self.source_id, self.root)
            data, rec = fetch.http_get(url, tr, max_bytes=2_000_000, timeout=60, retries=2)
            doc = json.loads(data)
            evidence.update(query=url, hits=doc.get("hits"), transcript=tr.object_key, sha256=rec.get("sha256"))
            if doc.get("hits", 0) < 1:
                raise OutOfFootprintError("CMR reports no SRTMGL1 granule for tile (ocean or outside coverage)",
                                          granule=gid, query=url)
            item = doc["items"][0]
            umm = item["umm"]
            evidence.update(concept_id=item["meta"]["concept-id"],
                            collection_concept_id=item["meta"]["collection-concept-id"],
                            revision_date=item["meta"]["revision-date"],
                            size=umm.get("DataGranule", {}).get("ArchiveAndDistributionInformation"),
                            doi=[a["Values"][0] for a in umm.get("AdditionalAttributes", [])
                                 if a.get("Name") == "identifier_product_doi"],
                            bounding=umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["BoundingRectangles"])
            rng = umm["TemporalExtent"]["RangeDateTime"]
            observation = TimeWindow(parse_utc(rng["BeginningDateTime"]), parse_utc(rng["EndingDateTime"]))
            for ru in umm.get("RelatedUrls", []):
                if ru.get("Type") == "GET DATA" and ru["URL"].startswith("https://"):
                    official = ru["URL"]
        candidates = (
            Candidate(official, "data", f"{gid}.zip", requires_credential="EARTHDATA_TOKEN",
                      note="authoritative LP DAAC Cloud distribution (Earthdata Login)"),
            Candidate(f"{MIRROR_BASE}{gid}.zip", "data", f"{gid}.zip",
                      note="public mirror: ESA STEP SNAP auxdata redistribution of SRTMGL1 tiles"),
        )
        return Granule(self.source_id, self.product_id, self.product_version, gid, self.body,
                       (lon - 1 / 7200, lat - 1 / 7200, lon + 1 + 1 / 7200, lat + 1 + 1 / 7200), observation,
                       candidates, self.license_url, self.crs,
                       "WGS84 geodetic lon/lat, east-positive; point-registered 1 arc-second posts; EGM96 heights",
                       evidence)

    # ------------------------------------------------------------------ acquire
    def acquire(self, granules: Sequence[Granule], byte_budget: int, aoi: Optional[AOI] = None) -> List[RawAsset]:
        out: List[RawAsset] = []
        spent = 0
        for g in granules:
            cached = fetch.find_cached(self.source_id, g.granule_id, "data", self.root)
            for meta in cached:
                if not self.offline and earthdata_token() and urllib.parse.urlsplit(meta["source_url"]).hostname != "data.lpdaac.earthdatacloud.nasa.gov":
                    continue  # A mirror cache cannot satisfy an authenticated official acquisition.
                asset = fetch.asset_from_meta(meta, g.observation, from_cache=True)
                try:
                    fetch.verify_raw(asset)
                except Exception:
                    continue
                out.append(asset)
                break
            else:
                if self.offline:
                    raise AcquisitionError("offline and no verified cached copy", granule=g.granule_id)
                remaining = byte_budget - spent
                if remaining <= 0:
                    raise ByteBudgetExceededError("byte budget exhausted", budget=byte_budget)
                out.append(self._fetch_granule(g, remaining))
            spent += out[-1].byte_size
            if spent > byte_budget:
                raise ByteBudgetExceededError("byte budget exceeded", budget=byte_budget, spent=spent)
        return out

    def _fetch_granule(self, g: Granule, budget: int) -> RawAsset:
        tr = fetch.Transcript(self.source_id, self.root)
        errors = []
        for cand in g.candidates:
            if earthdata_token() and not cand.requires_credential:
                continue  # An authenticated acquisition must fail rather than silently use the mirror.
            secret = None
            if cand.requires_credential:
                token = earthdata_token()
                if not token:
                    err = CredentialMissingError(f"{cand.requires_credential} not set; authoritative source skipped",
                                                 url=cand.url)
                    tr.log(event="credential_missing", url=cand.url, env_var=cand.requires_credential)
                    errors.append(err.as_record())
                    # Record the server's real response without credentials as evidence.
                    try:
                        fetch.http_get(cand.url, tr, max_bytes=65536, timeout=30, retries=0, follow_redirects=False)
                    except Exception as exc:  # expected: redirect to Earthdata Login
                        errors.append(getattr(exc, "as_record", lambda: {"error": str(exc)})())
                    continue
                secret = {"Authorization": f"Bearer {token}"}
            route = "official" if cand.requires_credential else "mirror"
            staging = (self.root or fetch.artifact_root()) / "staging" / self.source_id / route / (cand.filename + ".part")
            staging.parent.mkdir(parents=True, exist_ok=True)
            try:
                data, rec = fetch.http_get(cand.url, tr, max_bytes=budget, timeout=self.request_timeout, retries=self.request_retries, dest=staging,
                                           secret_headers=secret)
            except Exception as exc:
                errors.append(getattr(exc, "as_record", lambda: {"error": str(exc)})())
                continue
            # Validate archive identity and full raster size before accepting source bytes.
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    members = [n for n in archive.namelist() if n.lower().endswith(".hgt")]
                    if len(members) != 1 or Path(members[0]).name not in (g.granule_id, g.granule_id.split(".")[0] + ".hgt") or len(archive.read(members[0])) != TILE_POSTS * TILE_POSTS * 2:
                        raise DecodeError("SRTM archive identity or decoded size mismatch")
            except zipfile.BadZipFile as exc:
                raise DecodeError("SRTM response is not a valid product archive") from exc
            meta = {
                "asset_id": f"srtmgl1-{g.granule_id.split('.')[0].lower()}-{rec['sha256'][:12]}",
                "source_id": self.source_id, "product_id": self.product_id, "product_version": self.product_version,
                "granule_id": g.granule_id, "body": self.body, "role": "data", "source_url": cand.url,
                "byte_size": len(data), "retrieved_at": fetch.now_utc(), "format": "zip(HGT int16 big-endian)",
                "crs": self.crs, "coordinate_conventions": g.coordinate_conventions,
                "license_url": self.license_url, "byte_ranges": None, "parent_asset_ids": [],
                "transcript": tr.object_key, "access_route": cand.note,
                "catalog_evidence": g.catalog_evidence, "acquisition_errors": errors,
                "observation_start": g.observation.start.isoformat(), "observation_end": g.observation.end.isoformat(),
            }
            path, key, digest = fetch.store_raw(data, filename=cand.filename, meta=meta, root=self.root)
            staging.unlink(missing_ok=True)
            meta.update(path=str(path), object_key=key, sha256=digest)
            return fetch.asset_from_meta(meta, g.observation, from_cache=False)
        raise AcquisitionError("all SRTMGL1 access routes failed", granule=g.granule_id, errors=json.dumps(errors))

    # ------------------------------------------------------------------ decode
    def decode(self, assets: Sequence[RawAsset], aoi: AOI, granule: Granule) -> Decoded:
        self.check_aoi(aoi)
        if len(assets) != 1:
            raise DecodeError("SRTM decode expects exactly one tile asset per granule", n=len(assets))
        asset = assets[0]
        fetch.verify_raw(asset)
        raw = Path(asset.path).read_bytes()
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                names = [n for n in zf.namelist() if n.lower().endswith(".hgt")]
                if len(names) != 1:
                    raise DecodeError("zip must contain exactly one .hgt", members=zf.namelist())
                hgt = zf.read(names[0])
                member = names[0]
        except zipfile.BadZipFile as exc:
            raise TruncatedAssetError(f"zip container unreadable: {exc}", object_key=asset.object_key) from exc
        except (EOFError, zipfile.LargeZipFile) as exc:
            raise TruncatedAssetError(f"zip container truncated: {exc}", object_key=asset.object_key) from exc
        return self.decode_hgt(hgt, aoi, granule, (asset,), member)

    def decode_hgt(self, hgt: bytes, aoi: AOI, granule: Granule, assets=(), member: str = "") -> Decoded:
        expected = TILE_POSTS * TILE_POSTS * 2
        if len(hgt) != expected:
            raise TruncatedAssetError("HGT size is not 3601x3601 int16 (1 arc-second)", expected=expected,
                                      actual=len(hgt))
        name = granule.granule_id[:7]
        lat_s = int(name[1:3]) * (1 if name[0] == "N" else -1)
        lon_w = int(name[4:7]) * (1 if name[3] == "E" else -1)
        step = 1.0 / (TILE_POSTS - 1)
        # posts inside the AOI (inclusive), clipped to the tile
        top = lat_s + 1
        if aoi.north < lat_s or aoi.south > lat_s + 1 or aoi.east < lon_w or aoi.west > lon_w + 1:
            raise OutOfFootprintError("AOI does not intersect tile", tile=name, bbox=aoi.bbox)
        r0 = max(0, math.ceil((top - aoi.north) / step - 1e-9))
        r1 = min(TILE_POSTS - 1, math.floor((top - aoi.south) / step + 1e-9))
        c0 = max(0, math.ceil((aoi.west - lon_w) / step - 1e-9))
        c1 = min(TILE_POSTS - 1, math.floor((aoi.east - lon_w) / step + 1e-9))
        if not (aoi.west >= lon_w and aoi.east <= lon_w + 1 and aoi.south >= lat_s and aoi.north <= lat_s + 1):
            raise OutOfFootprintError("AOI extends beyond the single tile; multi-tile mosaics are not implemented",
                                      tile=name, bbox=aoi.bbox)
        nrows, ncols = r1 - r0 + 1, c1 - c0 + 1
        vals: List[Optional[float]] = []
        fills = 0
        for r in range(r0, r1 + 1):
            row = struct.unpack_from(f">{ncols}h", hgt, (r * TILE_POSTS + c0) * 2)
            for v in row:
                if v == VOID:
                    fills += 1
                    vals.append(None)
                else:
                    vals.append(float(v))
        grid = Grid(nrows, ncols, top - r0 * step, lon_w + c0 * step, step, step, vals, "point")
        mid = (grid.lat(0) + grid.lat(nrows - 1)) / 2
        return Decoded(
            granule=granule, assets=tuple(assets), aoi=aoi, grid=grid, unit="m",
            vertical_datum=self.vertical_datum, horizontal_datum=self.horizontal_datum,
            body_radius_m=_A, radius_model="WGS84 ellipsoid (a=6378137 m, f=1/298.257223563) local radii",
            native_resolution_m=max(earth_dx(mid, step), earth_dy(mid, step)),
            fill_value=VOID, fill_count=fills,
            notes=[f"decoded member {member or granule.granule_id}", "big-endian int16, void=-32768 -> null"],
            transformations=[f"subset posts rows {r0}..{r1}, cols {c0}..{c1} of {TILE_POSTS}x{TILE_POSTS}",
                             "int16 metres -> float metres (no scale/offset)"],
        )

    # ------------------------------------------------------------------ validate / clean / features
    def validate(self, decoded: Decoded) -> Validation:
        issues: List[Issue] = []
        g = decoded.grid
        if decoded.vertical_datum != self.vertical_datum:
            raise VerticalDatumError("SRTMGL1 heights must be EGM96-geoid referenced",
                                     got=decoded.vertical_datum, expected=self.vertical_datum)
        cov = g.valid_count() / g.n if g.n else 0.0
        vals = [v for v in g.values if v is not None]
        if decoded.fill_count:
            issues.append(Issue("SRTM_VOIDS_PRESENT", "warning",
                                (f"{decoded.fill_count} of {g.n} posts are void (-32768)",), "srtm_void_mask"))
        out_of_range = [v for v in vals if v < -500 or v > 9000]
        if out_of_range:
            issues.append(Issue("ELEVATION_OUT_OF_PHYSICAL_RANGE", "critical",
                                (f"{len(out_of_range)} values outside -500..9000 m",)))
        if any(a.byte_ranges is None and a.source_url.startswith(MIRROR_BASE) for a in decoded.assets):
            issues.append(Issue("MIRROR_NOT_VERIFIED_AGAINST_LPDAAC", "warning",
                                ("bytes from public mirror; LP DAAC checksum comparison needs Earthdata Login",)))
        issues.append(Issue("SURFACE_IS_RADAR_PHASE_CENTRE", "info",
                            ("C-band SRTM heights include canopy/buildings; not bare-rock surface",)))
        if not vals:
            verdict = "INSUFFICIENT"
        elif any(i.severity == "critical" for i in issues):
            verdict = "QUARANTINE"
        elif cov < 0.65:
            verdict = "INSUFFICIENT"
        elif decoded.fill_count:
            verdict = "REPAIR_ALLOWED"
        else:
            verdict = "ACCEPT"
        return Validation(verdict, issues, round(cov, 6), {
            "posts": g.n, "voids": decoded.fill_count,
            "min_m": min(vals) if vals else None, "max_m": max(vals) if vals else None,
        })

    def clean(self, decoded: Decoded, approved_rules: Sequence[str]) -> Decoded:
        bad = [r for r in approved_rules if r not in self.approved_rules]
        if bad:
            raise UnapprovedRuleError("cleaning rule not approved for SRTMGL1", rules=bad)
        flags = []
        tx = list(decoded.transformations)
        if "srtm_void_mask" in approved_rules:
            tx.append("srtm_void_mask: void posts kept as null (no fill/interpolation)")
            if decoded.fill_count:
                flags.append(f"SRTM_VOIDS_MASKED={decoded.fill_count}")
        if any(a.source_url.startswith(MIRROR_BASE) for a in decoded.assets):
            flags.append("MIRROR_NOT_VERIFIED_AGAINST_LPDAAC")
        flags.append("SRTM_C_BAND_SURFACE_INCLUDES_CANOPY_AND_STRUCTURES")
        return Decoded(**{**decoded.__dict__, "transformations": tx, "stage": "cleaned",
                          "quality_flags": list(decoded.quality_flags) + flags})

    def features(self, clean: Decoded, scale: float) -> FeatureSet:
        from twinsite.processing.dem_features import dem_features

        if clean.stage != "cleaned":
            raise UnapprovedRuleError("features require a cleaned product")
        return dem_features(clean, scale, earth_dx, earth_dy,
                            "SRTM product spec: absolute vertical error < 16 m (90%); not propagated.")
